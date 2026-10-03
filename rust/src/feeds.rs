use crate::{
    Result,
    text::{clean, collapse, normalize_url},
};
use roxmltree::Node;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeedSource {
    pub url: String,
    pub title: String,
    pub kind: String,
    pub added_at: String,
    pub last_fetched_at: String,
    pub status: String,
    pub health_score: f64,
    pub error_kind: String,
    pub last_item_count: i64,
}
impl FeedSource {
    pub fn pending(url: String) -> Self {
        Self {
            url,
            title: String::new(),
            kind: String::new(),
            added_at: String::new(),
            last_fetched_at: String::new(),
            status: "pending".into(),
            health_score: 0.0,
            error_kind: String::new(),
            last_item_count: 0,
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeedItem {
    pub source_url: String,
    pub url: String,
    pub title: String,
    pub summary: String,
    pub source_title: String,
    pub published_at: Option<String>,
    pub fetched_at: String,
}
#[derive(Debug, Serialize)]
pub struct ParsedFeed {
    pub source: FeedSource,
    pub items: Vec<FeedItem>,
}
fn child<'a, 'b>(node: Node<'a, 'b>, name: &str) -> Option<Node<'a, 'b>> {
    node.children()
        .find(|n| n.is_element() && n.tag_name().name() == name)
}
fn children<'a, 'b>(node: Node<'a, 'b>, name: &str) -> impl Iterator<Item = Node<'a, 'b>> {
    node.children()
        .filter(move |n| n.is_element() && n.tag_name().name() == name)
}
fn content(node: Node<'_, '_>) -> String {
    collapse(
        &node
            .descendants()
            .filter(|n| n.is_text())
            .filter_map(|n| n.text())
            .collect::<String>(),
    )
}
fn text(node: Node<'_, '_>, name: &str) -> String {
    child(node, name).map(content).unwrap_or_default()
}
fn first_nonempty(values: impl IntoIterator<Item = String>) -> String {
    values
        .into_iter()
        .find(|s| !s.is_empty())
        .unwrap_or_default()
}
fn item_url(source: &str, value: &str) -> String {
    let value = collapse(value);
    if value.is_empty() {
        return value;
    }
    let value = if !value.contains("://") && !value.starts_with("//") {
        crate::urls::join(source, &value)
    } else {
        value
    };
    normalize_url(&value)
}
fn url_like(value: &str) -> bool {
    value.contains("://") || value.starts_with('/')
}
fn date(value: Option<&str>) -> Option<String> {
    let value = collapse(value.unwrap_or(""));
    if value.is_empty() {
        return None;
    }
    if let Ok(dt) = chrono::DateTime::parse_from_rfc2822(&value) {
        return Some(if value.ends_with("-0000") {
            dt.naive_local().format("%Y-%m-%dT%H:%M:%S").to_string()
        } else {
            dt.to_rfc3339_opts(chrono::SecondsFormat::Secs, false)
        });
    }
    for format in ["%a, %d %b %Y %H:%M:%S", "%d %b %Y %H:%M:%S"] {
        if let Ok(dt) = chrono::NaiveDateTime::parse_from_str(&value, format) {
            return Some(dt.format("%Y-%m-%dT%H:%M:%S").to_string());
        }
    }
    Some(value)
}
fn val(row: &serde_json::Value, key: &str) -> String {
    row[key].as_str().unwrap_or("").to_string()
}
pub fn parse(text_value: &str, source_url: &str, fetched_at: &str) -> Result<ParsedFeed> {
    let stripped = text_value.trim_start_matches('\u{feff}').trim_start();
    let mut source = FeedSource::pending(source_url.to_string());
    source.last_fetched_at = fetched_at.to_string();
    source.status = "ok".into();
    source.health_score = 1.0;
    let mut items = Vec::new();
    if stripped.starts_with('{') {
        let payload: serde_json::Value =
            serde_json::from_str(stripped).map_err(|e| format!("invalid JSON feed: {e}"))?;
        if !payload.is_object() {
            return Err("invalid JSON feed: root must be an object".into());
        }
        source.kind = "json".into();
        source.title = collapse(&first_nonempty([
            val(&payload, "title"),
            source_url.to_string(),
        ]));
        for row in payload["items"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|r| r.is_object())
        {
            let url = item_url(
                source_url,
                &first_nonempty([val(row, "url"), val(row, "external_url")]),
            );
            if url.is_empty() {
                continue;
            }
            items.push(FeedItem {
                source_url: source_url.into(),
                title: collapse(&first_nonempty([val(row, "title"), url.clone()])),
                url,
                summary: clean(&first_nonempty([
                    val(row, "summary"),
                    val(row, "content_text"),
                    val(row, "content_html"),
                ])),
                source_title: source.title.clone(),
                published_at: date(Some(&first_nonempty([
                    val(row, "date_published"),
                    val(row, "date_modified"),
                ]))),
                fetched_at: fetched_at.into(),
            });
        }
    } else {
        let doc =
            roxmltree::Document::parse(stripped).map_err(|e| format!("invalid feed XML: {e}"))?;
        let root = doc.root_element();
        let atom = root.tag_name().name().eq_ignore_ascii_case("feed");
        if !atom
            && !["rss", "rdf"].contains(&root.tag_name().name().to_lowercase().as_str())
            && child(root, "channel").is_none()
            && children(root, "item").next().is_none()
        {
            return Err(format!("unsupported feed XML root: {}", root.tag_name().name()).into());
        }
        let channel = if atom {
            root
        } else {
            child(root, "channel").unwrap_or(root)
        };
        source.kind = if atom { "atom" } else { "rss" }.into();
        source.title = first_nonempty([text(channel, "title"), source_url.to_string()]);
        let mut nodes: Vec<_> = children(root, if atom { "entry" } else { "item" }).collect();
        if !atom && channel != root {
            nodes.extend(children(channel, "item"));
        }
        for node in nodes {
            let value = if atom {
                let links: Vec<_> = children(node, "link")
                    .filter_map(|n| {
                        n.attribute("href")
                            .filter(|s| !s.is_empty())
                            .map(|s| (n.attribute("rel").unwrap_or("alternate"), s))
                    })
                    .collect();
                links
                    .iter()
                    .find(|(rel, _)| *rel == "alternate")
                    .or_else(|| links.first())
                    .map(|(_, u)| u.to_string())
                    .unwrap_or_else(|| {
                        let id = text(node, "id");
                        if url_like(&id) { id } else { String::new() }
                    })
            } else {
                let link = text(node, "link");
                if !link.is_empty() {
                    link
                } else {
                    child(node, "guid")
                        .filter(|n| {
                            !n.attribute("isPermaLink")
                                .unwrap_or("true")
                                .trim()
                                .eq_ignore_ascii_case("false")
                        })
                        .map(content)
                        .filter(|s| url_like(s))
                        .unwrap_or_default()
                }
            };
            let url = item_url(source_url, &value);
            if url.is_empty() {
                continue;
            }
            let summary = if atom {
                first_nonempty([text(node, "summary"), text(node, "content")])
            } else {
                first_nonempty([
                    text(node, "description"),
                    text(node, "encoded"),
                    text(node, "summary"),
                ])
            };
            let published = if atom {
                first_nonempty([text(node, "published"), text(node, "updated")])
            } else {
                first_nonempty([text(node, "pubDate"), text(node, "date")])
            };
            items.push(FeedItem {
                source_url: source_url.into(),
                title: first_nonempty([text(node, "title"), url.clone()]),
                url,
                summary: clean(&summary),
                source_title: source.title.clone(),
                published_at: date(Some(&published)),
                fetched_at: fetched_at.into(),
            });
        }
    }
    source.last_item_count = items.len() as i64;
    Ok(ParsedFeed { source, items })
}

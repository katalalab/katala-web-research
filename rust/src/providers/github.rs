//! Native GitHub code response/request contract; repo fallback is still pending.
use super::{Context, ProviderError, ProviderResult, Request, SearchProvider, Transport};
use crate::search::SearchResult;
use serde_json::{Map, Value};
use std::collections::BTreeMap;

pub struct GitHubCode {
    token: String,
}
fn failure(kind: &'static str, message: &str) -> ProviderError {
    ProviderError {
        kind,
        message: message.into(),
    }
}
fn strip(value: &str) -> &str {
    value.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
}
fn object(value: &Value) -> ProviderResult<&Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| failure("AttributeError", "GitHub result must be an object"))
}
fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(v) => *v,
        Value::Number(n) => n.as_f64().is_some_and(|v| v != 0.0),
        Value::String(v) => !v.is_empty(),
        Value::Array(v) => !v.is_empty(),
        Value::Object(v) => !v.is_empty(),
    }
}
fn value<'a>(item: &'a Map<String, Value>, names: &[&str]) -> Option<&'a Value> {
    names
        .iter()
        .find_map(|name| item.get(*name).filter(|v| truthy(v)))
}
fn text(value: Option<&Value>) -> ProviderResult<String> {
    match value {
        None | Some(Value::Null) => Ok(String::new()),
        Some(Value::String(s)) => Ok(s.clone()),
        Some(_) => Err(failure(
            "TypeError",
            "GitHub text field has an unsupported type",
        )),
    }
}
fn scalar(value: Option<&Value>) -> ProviderResult<String> {
    match value {
        Some(Value::Bool(true)) => Ok("True".into()),
        Some(Value::Bool(false)) => Ok("False".into()),
        Some(Value::Number(n)) => Ok(n.to_string()),
        _ => text(value),
    }
}
fn fragment(value: Option<&Value>) -> ProviderResult<String> {
    let Some(Value::Array(matches)) = value else {
        return Ok(String::new());
    };
    let mut fragments = Vec::new();
    for m in matches {
        let Some(m) = m.as_object() else {
            continue;
        };
        if m.get("object_type") != Some(&Value::String("FileContent".into()))
            || m.get("property") != Some(&Value::String("content".into()))
        {
            continue;
        }
        let text = crate::text::collapse(&scalar(value_or_none(m, "fragment"))?);
        if !text.is_empty() {
            fragments.push(text);
        }
    }
    Ok(fragments
        .into_iter()
        .take(3)
        .collect::<Vec<_>>()
        .join(" ... "))
}
fn value_or_none<'a>(item: &'a Map<String, Value>, key: &str) -> Option<&'a Value> {
    value(item, &[key])
}
impl GitHubCode {
    pub fn with_token(token: String) -> Self {
        Self { token }
    }
    pub fn from_env() -> ProviderResult<Self> {
        match std::env::var("GITHUB_TOKEN") {
            Ok(token) => Ok(Self { token }),
            Err(std::env::VarError::NotPresent) => Ok(Self {
                token: String::new(),
            }),
            Err(_) => Err(failure("FetchError", "GITHUB_TOKEN must be UTF-8")),
        }
    }
}
impl SearchProvider for GitHubCode {
    fn name(&self) -> &'static str {
        "github_code"
    }
    fn search(
        &self,
        query: &str,
        limit: i64,
        transport: &mut dyn Transport,
        context: &Context<'_>,
    ) -> ProviderResult<Vec<SearchResult>> {
        let token = strip(&self.token);
        if token.is_empty() {
            return Err(failure(
                "FetchError",
                "GITHUB_TOKEN is required for GitHub code search",
            ));
        }
        let requested = limit.max(0);
        if requested == 0 {
            return Ok(Vec::new());
        }
        let pages = ((requested - 1) / 100 + 1).min(10);
        let mut found = Vec::new();
        for page in 1..=pages {
            let mut form = url::form_urlencoded::Serializer::new(String::new());
            form.extend_pairs([
                ("q", query.to_string()),
                ("sort", "indexed".into()),
                ("per_page", "100".into()),
                ("page", page.to_string()),
            ]);
            let request = Request {
                url: format!(
                    "https://api.github.com/search/code?{}",
                    form.finish().replace('*', "%2A").replace("%7E", "~")
                ),
                headers: [
                    (
                        "Accept".into(),
                        "application/vnd.github.text-match+json".into(),
                    ),
                    ("Authorization".into(), format!("Bearer {token}")),
                    ("X-GitHub-Api-Version".into(), "2022-11-28".into()),
                ]
                .into(),
            };
            let response = match transport.get(&request) {
                Ok(response) => response,
                Err(error) if error.has_http_status(422) => return Ok(Vec::new()),
                Err(error) => return Err(error),
            };
            let payload: Value = serde_json::from_str(&response.text())
                .map_err(|_| failure("FetchError", "non-JSON response from GitHub code search"))?;
            let payload = object(&payload)?;
            let entries = match payload.get("items") {
                None => &[][..],
                Some(v) if !truthy(v) => &[],
                Some(Value::Array(v)) => v.as_slice(),
                Some(_) => return Err(failure("TypeError", "GitHub items must be a list")),
            };
            if entries.is_empty() {
                break;
            }
            for item in entries {
                if found.len() as i64 >= requested {
                    break;
                }
                let item = object(item)?;
                let empty = Map::new();
                let repo = match value_or_none(item, "repository") {
                    Some(v) => object(v)?,
                    None => &empty,
                };
                let path = scalar(value(item, &["path", "name"]))?;
                let repo_name = scalar(value_or_none(repo, "full_name"))?;
                let url = text(value_or_none(item, "html_url"))?;
                let title = if !repo_name.is_empty() && !path.is_empty() {
                    format!("{repo_name} - {path}")
                } else if !path.is_empty() {
                    path.clone()
                } else {
                    url.clone()
                };
                let fragment = fragment(item.get("text_matches"))?;
                let mut snippets = Vec::new();
                if let Some(value) = value_or_none(repo, "description") {
                    snippets.push(scalar(Some(value))?);
                }
                if !path.is_empty() {
                    snippets.push(format!("path={path}"));
                }
                if let Some(value) = value_or_none(repo, "language") {
                    snippets.push(format!("language={}", scalar(Some(value))?));
                }
                if !fragment.is_empty() {
                    snippets.push(crate::text::truncate(&fragment, 420));
                }
                let metadata: BTreeMap<String, Value> = [
                    ("repository".into(), Value::String(repo_name)),
                    (
                        "repository_url".into(),
                        value_or_none(repo, "html_url")
                            .cloned()
                            .unwrap_or(Value::String(String::new())),
                    ),
                    ("path".into(), Value::String(path)),
                    (
                        "file_name".into(),
                        value_or_none(item, "name")
                            .cloned()
                            .unwrap_or(Value::String(String::new())),
                    ),
                    ("fragment".into(), Value::String(fragment)),
                ]
                .into();
                found.push(SearchResult {
                    title,
                    url,
                    snippet: snippets.join(" | "),
                    source: self.name().into(),
                    published_at: None,
                    rank: found.len() as i64 + 1,
                    score: 0.0,
                    metadata,
                });
            }
            if found.len() as i64 >= requested {
                break;
            }
        }
        Ok(crate::search::rank(
            query,
            found,
            context.registry,
            context.year,
        ))
    }
}

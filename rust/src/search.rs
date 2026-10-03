//! Reference lexical scoring, gates, and source/host diversity for local feed retrieval.
use crate::{
    Result,
    archive::Archive,
    registry::Registry,
    text::{tokens, truncate},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
};
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub title: String,
    pub url: String,
    pub snippet: String,
    pub source: String,
    pub published_at: Option<String>,
    pub rank: i64,
    pub score: f64,
    pub metadata: BTreeMap<String, Value>,
}
fn host(url: &str) -> String {
    let h = crate::urls::parse(url).authority.to_lowercase();
    h.strip_prefix("www.").unwrap_or(&h).into()
}
pub fn classify(registry: &Registry, url: &str) -> (String, i64) {
    if let Some(e) = registry.match_url(url) {
        return (e.source_type.clone(), e.trust_score);
    }
    let host = host(url);
    let (kind, score) = if [
        "docs.github.com",
        "developers.openai.com",
        "platform.openai.com",
        "docs.anthropic.com",
        "docs.python.org",
        "ai.google.dev",
        "cloud.google.com",
        "learn.microsoft.com",
        "developer.mozilla.org",
    ]
    .contains(&host.as_str())
    {
        ("official-docs", 100)
    } else if ["github.com", "gitlab.com", "sourceforge.net"].contains(&host.as_str()) {
        ("primary-code", 85)
    } else if [
        "aclanthology.org",
        "arxiv.org",
        "doi.org",
        "openreview.net",
        "pubmed.ncbi.nlm.nih.gov",
        "semanticscholar.org",
    ]
    .contains(&host.as_str())
    {
        ("primary-research", 85)
    } else if host.ends_with(".edu") || host.ends_with(".gov") {
        ("institutional", 75)
    } else if host.contains("docs") || host.contains("developer") {
        ("vendor-docs", 70)
    } else {
        ("web", 50)
    };
    (kind.to_string(), score)
}
fn round(value: f64) -> f64 {
    format!("{value:.3}").parse().unwrap()
}
pub fn rank(
    query: &str,
    results: Vec<SearchResult>,
    registry: &Registry,
    year: i32,
) -> Vec<SearchResult> {
    let tokens = tokens(query);
    let mut seen = BTreeSet::new();
    let mut ranked = Vec::new();
    for mut result in results {
        let parts = crate::urls::parse(&result.url);
        if parts.authority.is_empty() {
            continue;
        }
        let path = parts.path_without_params().trim_end_matches('/');
        let key = format!(
            "{}://{}{}",
            parts.scheme,
            parts.authority.to_lowercase(),
            if path.is_empty() { "/" } else { path }
        );
        if result.url.is_empty()
            || result.title.is_empty()
            || result.snippet.to_lowercase().contains("retracted=true")
            || !seen.insert(key)
        {
            continue;
        }
        if result.rank != 0 {
            result
                .metadata
                .entry("provider_rank".into())
                .or_insert(json!(result.rank));
        }
        let (_, quality) = classify(registry, &result.url);
        let hay = crate::text::tokens(&format!("{} {}", result.title, result.snippet));
        let title = crate::text::tokens(&result.title);
        let overlap = tokens.intersection(&hay).count() as f64 / tokens.len().max(1) as f64;
        let fresh = result
            .published_at
            .as_deref()
            .filter(|s| s.len() >= 4)
            .and_then(|s| s.get(..4))
            .filter(|s| s.bytes().all(|b| b.is_ascii_digit()))
            .and_then(|s| s.parse::<i32>().ok())
            .map_or(0.0, |y| {
                if year - y == 0 {
                    0.3
                } else if year - y == 1 {
                    0.15
                } else {
                    0.0
                }
            });
        let qualityscore = round(
            quality as f64 / 100.0
                + overlap
                + if quality >= 85 { 0.4 } else { 0.0 }
                + if tokens.intersection(&title).next().is_some() {
                    0.2
                } else {
                    0.0
                }
                + fresh,
        );
        let weight = if ["github", "jina"].contains(&result.source.as_str()) {
            0.25
        } else {
            0.0
        };
        let fusion = (result
            .metadata
            .get("rrf_score")
            .and_then(Value::as_f64)
            .unwrap_or(0.0)
            * 20.0)
            .min(0.75);
        let count = result
            .metadata
            .get("source_count")
            .and_then(Value::as_i64)
            .unwrap_or(1);
        result.score = round(
            qualityscore
                + weight
                + fusion
                + ((count - 1).max(0) as f64 * 0.2).min(0.6)
                + (20 - result.rank).max(0) as f64 / 100.0,
        );
        ranked.push(result);
    }
    ranked.sort_by(|a, b| {
        b.score
            .total_cmp(&a.score)
            .then(a.rank.cmp(&b.rank))
            .then(a.url.cmp(&b.url))
    });
    if ranked.len() > 2 {
        let hostcap = (ranked.len() as f64 * 0.4).ceil() as usize;
        let typecap = (ranked.len() as f64 * 0.55).ceil() as usize;
        let mut hosts = BTreeMap::<String, usize>::new();
        let mut types = BTreeMap::<String, usize>::new();
        ranked.retain(|r| {
            let h = host(&r.url);
            let (t, _) = classify(registry, &r.url);
            if hosts.get(&h).copied().unwrap_or(0) >= hostcap
                || types.get(&t).copied().unwrap_or(0) >= typecap
            {
                return false;
            }
            *hosts.entry(h).or_default() += 1;
            *types.entry(t).or_default() += 1;
            true
        });
    }
    for (i, r) in ranked.iter_mut().enumerate() {
        r.rank = i as i64 + 1;
    }
    ranked
}
pub fn feed(
    query: &str,
    archive: &Path,
    limit: i64,
    registry: &Registry,
) -> Result<Vec<SearchResult>> {
    let hits = Archive::open(archive)?.query("feeds", query, limit, "", "")?;
    let results = hits
        .into_iter()
        .enumerate()
        .map(|(i, r)| SearchResult {
            title: r["title"].as_str().unwrap_or("").into(),
            url: r["url"].as_str().unwrap_or("").into(),
            snippet: r["snippet"].as_str().unwrap_or("").into(),
            source: "feed".into(),
            published_at: r["published_at"].as_str().map(str::to_string),
            rank: i as i64 + 1,
            score: 0.0,
            metadata: [
                ("source_url".into(), r["source_url"].clone()),
                ("source_title".into(), r["source_title"].clone()),
                ("fetched_at".into(), r["fetched_at"].clone()),
                ("archive_rank".into(), r["rank"].clone()),
            ]
            .into(),
        })
        .collect();
    use chrono::Datelike;
    Ok(rank(query, results, registry, chrono::Local::now().year()))
}
pub fn slice(mut results: Vec<SearchResult>, limit: i64) -> Vec<SearchResult> {
    let count = if limit < 0 {
        (results.len() as i64 + limit).max(0)
    } else {
        limit
    };
    results.truncate(count as usize);
    results
}
pub fn highlight(query: &str, content: &str) -> String {
    let tokens = tokens(query);
    if tokens.is_empty() {
        return String::new();
    }
    let mut sentences = Vec::new();
    let mut start = 0;
    let mut prev = None;
    for (i, c) in content.char_indices() {
        if c == '\n' || (c.is_whitespace() && prev.is_some_and(|p| ".!?。！？".contains(p))) {
            sentences.push(&content[start..i]);
            start = i + c.len_utf8();
        }
        prev = Some(c);
    }
    sentences.push(&content[start..]);
    let mut candidates: Vec<_> = sentences
        .into_iter()
        .enumerate()
        .filter_map(|(i, s)| {
            let s = crate::words(s).collect::<Vec<_>>().join(" ");
            let lowered = s.to_lowercase();
            let score = tokens
                .iter()
                .filter(|t| lowered.contains(t.as_str()))
                .count();
            if s.chars().count() < 20 || score == 0 {
                None
            } else {
                Some((score, i, s))
            }
        })
        .collect();
    candidates.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)));
    candidates.truncate(4);
    candidates.sort_by_key(|c| c.1);
    truncate(
        &candidates
            .into_iter()
            .map(|c| c.2)
            .collect::<Vec<_>>()
            .join(" "),
        700,
    )
    .trim()
    .into()
}

#[derive(Debug)]
pub struct BuiltQuery {
    pub query: String,
    pub domains: BTreeMap<String, String>,
    pub pdf: bool,
}
pub fn build_query(
    query: &str,
    categories: &[String],
    includes: &[String],
    excludes: &[String],
) -> BuiltQuery {
    let mut domains = BTreeMap::new();
    let mut filters = Vec::new();
    let mut pdf = false;
    for category in categories {
        match category.trim().to_lowercase().as_str() {
            "github" => {
                filters.push("site:github.com".into());
                domains.insert("github.com".into(), "github".into());
            }
            "pdf" => {
                filters.push("filetype:pdf".into());
                pdf = true;
            }
            "research" => {
                let mut f = Vec::new();
                for d in [
                    "arxiv.org",
                    "pubmed.ncbi.nlm.nih.gov",
                    "nature.com",
                    "science.org",
                    "ieee.org",
                    "acm.org",
                    "springer.com",
                    "wiley.com",
                    "sciencedirect.com",
                    "plos.org",
                    "biorxiv.org",
                    "medrxiv.org",
                ] {
                    f.push(format!("site:{d}"));
                    domains.insert(d.into(), "research".into());
                }
                filters.push(format!("({})", f.join(" OR ")));
            }
            _ => {}
        }
    }
    let inc = clean_domains(includes);
    if inc.len() == 1 {
        filters.push(format!("site:{}", inc[0]));
    } else if !inc.is_empty() {
        filters.push(format!(
            "({})",
            inc.iter()
                .map(|d| format!("site:{d}"))
                .collect::<Vec<_>>()
                .join(" OR ")
        ));
    }
    for d in clean_domains(excludes) {
        filters.push(format!("-site:{d}"));
    }
    BuiltQuery {
        query: if filters.is_empty() {
            query.into()
        } else {
            format!("{} {}", query.trim(), filters.join(" "))
                .trim()
                .into()
        },
        domains,
        pdf,
    }
}
fn clean_domains(values: &[String]) -> Vec<String> {
    let mut result = Vec::new();
    for value in values {
        let mut domain = value.trim().to_lowercase();
        if domain.contains("://") {
            domain = crate::urls::parse(&domain).authority;
        }
        domain = domain
            .strip_prefix("www.")
            .unwrap_or(&domain)
            .trim_matches('/')
            .to_string();
        if !domain.is_empty() && !result.contains(&domain) {
            result.push(domain);
        }
    }
    result
}
pub fn category(url: &str, built: &BuiltQuery) -> Option<String> {
    let parts = crate::urls::parse(url);
    let h = parts.authority.to_lowercase();
    let h = h.strip_prefix("www.").unwrap_or(&h);
    if h.is_empty() {
        return None;
    }
    if built.pdf && parts.path_without_params().to_lowercase().ends_with(".pdf") {
        return Some("pdf".into());
    }
    if h == "github.com" || h.ends_with(".github.com") {
        return Some("github".into());
    }
    built
        .domains
        .iter()
        .find(|(d, _)| h == d.as_str() || h.ends_with(&format!(".{d}")))
        .map(|(_, c)| c.clone())
}

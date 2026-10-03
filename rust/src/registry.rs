use crate::Result;
use serde::{Deserialize, Serialize};
use std::{fs, path::Path};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Entry {
    pub name: String,
    pub domain: String,
    pub source_type: String,
    #[serde(default)]
    pub query_types: Vec<String>,
    pub url: String,
    #[serde(default)]
    pub hosts: Vec<String>,
    #[serde(default)]
    pub url_prefixes: Vec<String>,
    #[serde(default)]
    pub best_for: String,
    #[serde(default)]
    pub freshness: String,
    #[serde(default = "trust_default")]
    pub trust_score: i64,
    #[serde(default)]
    pub bias_caveat: String,
    #[serde(default)]
    pub update_cadence: String,
    #[serde(default)]
    pub avoid_for: Vec<String>,
}
fn trust_default() -> i64 {
    50
}
#[derive(Deserialize)]
pub struct Registry {
    #[serde(default)]
    pub sources: Vec<Entry>,
}
fn host(value: &str) -> String {
    let lower = value.to_lowercase();
    lower.strip_prefix("www.").unwrap_or(&lower).to_string()
}
// Registry matching preserves the reference's netloc and path literally. URL
// canonicalizers strip explicit default ports and resolve dot segments, changing trust matches.
fn parse(value: &str) -> Option<(String, String)> {
    let has_scheme = value.split_once(':').is_some_and(|(s, _)| {
        !s.is_empty()
            && s.chars().next().is_some_and(|c| c.is_ascii_alphabetic())
            && s.chars()
                .all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c))
    });
    let normalized = if has_scheme {
        value.to_string()
    } else {
        format!("https://{value}")
    };
    let (_, rest) = normalized.split_once("://")?;
    let end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
    let authority = &rest[..end];
    if authority.is_empty() {
        return None;
    }
    let suffix = &rest[end..];
    let path = if suffix.starts_with('/') {
        suffix.split(['?', '#']).next().unwrap_or("")
    } else {
        ""
    };
    Some((host(authority), path.to_string()))
}
impl Registry {
    pub fn load(overlay: Option<&Path>) -> Result<Self> {
        let mut registry: Self = serde_json::from_str(include_str!(
            "../../src/katala_web_research/data/source_registry.json"
        ))?;
        if let Some(path) = overlay {
            let extra: Self = serde_json::from_str(&fs::read_to_string(path)?)?;
            for entry in extra.sources {
                if let Some(i) = registry.sources.iter().position(|s| {
                    (s.domain.as_str(), s.source_type.as_str(), s.name.as_str())
                        == (
                            entry.domain.as_str(),
                            entry.source_type.as_str(),
                            entry.name.as_str(),
                        )
                }) {
                    registry.sources[i] = entry;
                } else {
                    registry.sources.push(entry);
                }
            }
        }
        for entry in &mut registry.sources {
            entry.hosts = entry.hosts.iter().map(|s| host(s)).collect();
        }
        Ok(registry)
    }
    pub fn recommend(
        &self,
        domain: Option<&str>,
        query_type: Option<&str>,
        limit: i64,
    ) -> Vec<&Entry> {
        let mut sources: Vec<_> = self
            .sources
            .iter()
            .filter(|s| {
                domain
                    .filter(|d| !d.is_empty())
                    .is_none_or(|d| s.domain == d)
                    && query_type
                        .filter(|q| !q.is_empty())
                        .is_none_or(|q| s.query_types.iter().any(|t| t == q))
            })
            .collect();
        sources.sort_by(|a, b| {
            b.trust_score
                .cmp(&a.trust_score)
                .then(a.domain.cmp(&b.domain))
                .then(a.name.cmp(&b.name))
        });
        sources.truncate(limit.max(0) as usize);
        sources
    }
    pub fn match_url(&self, value: &str) -> Option<&Entry> {
        let (h, url_path) = parse(value)?;
        let matches = |s: &&Entry| {
            s.url_prefixes.iter().any(|prefix| {
                let Some((ph, prefix_path)) = parse(prefix) else {
                    return false;
                };
                let pp = prefix_path.trim_end_matches('/');
                let path = url_path.trim_end_matches('/');
                ph == h && (pp.is_empty() || path == pp || path.starts_with(&format!("{pp}/")))
            })
        };
        let mut chosen: Vec<_> = self.sources.iter().filter(matches).collect();
        if chosen.is_empty() {
            chosen = self
                .sources
                .iter()
                .filter(|s| {
                    s.hosts.contains(&h)
                        && (s.url_prefixes.is_empty()
                            || s.url_prefixes.iter().any(|p| {
                                parse(p).is_some_and(|(_, path)| path == "/" || path.is_empty())
                            }))
                })
                .collect();
        }
        chosen.sort_by(|a, b| b.trust_score.cmp(&a.trust_score).then(a.name.cmp(&b.name)));
        chosen.first().copied()
    }
}

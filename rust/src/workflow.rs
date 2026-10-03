//! Sequential search enrichment; reading does not persist pages.
use crate::{
    providers::{Context, Transport},
    reader,
    search::{self, SearchResult},
};
use serde_json::json;

pub fn enrich(
    query: &str,
    mut results: Vec<SearchResult>,
    read_top: i64,
    mode: &str,
    transport: &mut impl Transport,
    context: &Context<'_>,
    mut clock: impl FnMut() -> String,
) -> Vec<SearchResult> {
    if read_top <= 0 || results.is_empty() {
        return results;
    }
    for result in results.iter_mut().take(read_top as usize) {
        match reader::read_with(&result.url, mode, transport, &mut clock) {
            Ok(page) => {
                result.metadata.insert("read_status".into(), json!("ok"));
                result
                    .metadata
                    .insert("read_source".into(), json!(page.source));
                result
                    .metadata
                    .insert("read_status_code".into(), json!(page.status_code));
                if result.title.is_empty() {
                    result.title = page.title;
                }
                // Python str.split includes the four ASCII information separators.
                // Page content is plain text; HTML entities remain literal here.
                let snippet: String = page
                    .content
                    .split(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
                    .filter(|part| !part.is_empty())
                    .collect::<Vec<_>>()
                    .join(" ")
                    .chars()
                    .take(700)
                    .collect();
                if !snippet.is_empty() {
                    result.snippet = snippet;
                }
            }
            Err(error) => {
                result.metadata.insert("read_status".into(), json!("error"));
                result
                    .metadata
                    .insert("read_error_kind".into(), json!(error.kind));
            }
        }
    }
    search::rank(query, results, context.registry, context.year)
}

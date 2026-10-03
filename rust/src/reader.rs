//! Direct reader preview; auto/Jina and final lifecycle gates remain pending.
use crate::providers::{ProviderError, ProviderResult, Request, Transport};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, sync::LazyLock};

#[derive(Debug, Serialize, Deserialize)]
pub struct PageSnapshot {
    pub url: String,
    pub title: String,
    pub content: String,
    pub source: String,
    pub fetched_at: String,
    pub status_code: Option<u16>,
    pub content_type: Option<String>,
}

pub fn direct_with(
    url: &str,
    transport: &mut impl Transport,
    clock: impl FnOnce() -> String,
) -> ProviderResult<PageSnapshot> {
    let parsed = crate::urls::parse(url);
    if !["http", "https"].contains(&parsed.scheme.as_str()) || parsed.authority.is_empty() {
        return Err(ProviderError::invalid_value(
            "only http and https URLs are supported",
        ));
    }
    let response = transport.get(&Request {
        url: url.into(),
        headers: BTreeMap::from([(
            "Accept".into(),
            "text/html, text/plain;q=0.9, */*;q=0.5".into(),
        )]),
    })?;
    let content_type = response
        .headers
        .get("content-type")
        .cloned()
        .unwrap_or_default();
    let mut text = response.text();
    if !content_type.to_lowercase().contains("charset=") {
        static META: LazyLock<regex::bytes::Regex> = LazyLock::new(|| {
            regex::bytes::Regex::new(r#"(?i-u)<meta[^>]+charset=["']?\s*([a-zA-Z0-9_-]+)"#).unwrap()
        });
        if let Some(captures) = META.captures(&response.body[..response.body.len().min(4096)]) {
            let charset = std::str::from_utf8(&captures[1]).unwrap();
            if known_charset(charset) {
                text = crate::http::decode(&response.body, charset);
            }
        }
    }
    let html = content_type.to_lowercase().contains("html")
        || text
            .chars()
            .take(500)
            .collect::<String>()
            .to_lowercase()
            .contains("<html");
    let (title, content) = if html {
        let extracted = crate::text::html_text(&text);
        (
            if extracted.title.is_empty() {
                url.into()
            } else {
                extracted.title
            },
            extracted.content,
        )
    } else {
        (
            url.into(),
            text.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
                .into(),
        )
    };
    Ok(PageSnapshot {
        url: response.url,
        title,
        content,
        source: "direct".into(),
        fetched_at: clock(),
        status_code: Some(response.status),
        content_type: Some(content_type),
    })
}
fn known_charset(label: &str) -> bool {
    let alias = label.to_lowercase().replace(['-', '_', ' '], "");
    [
        "utf8sig", "utf", "u8", "latin", "l1", "isoir100", "cp819", "ibm819", "646",
    ]
    .contains(&alias.as_str())
        || encoding_rs::Encoding::for_label(label.as_bytes()).is_some()
}

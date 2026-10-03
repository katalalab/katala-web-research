//! Native reader preview; malformed, target-policy and final lifecycle gates remain pending.
use crate::providers::{ProviderError, ProviderResult, Request, Transport};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, sync::LazyLock};

pub const MAX_READER_OUTPUT_BYTES: usize = 8 * 1024 * 1024;
pub struct CappedOutput {
    bytes: Vec<u8>,
}
impl CappedOutput {
    pub fn as_slice(&self) -> &[u8] {
        &self.bytes
    }
}
impl Default for CappedOutput {
    fn default() -> Self {
        Self {
            bytes: Vec::with_capacity(MAX_READER_OUTPUT_BYTES),
        }
    }
}
impl std::io::Write for CappedOutput {
    fn write(&mut self, input: &[u8]) -> std::io::Result<usize> {
        if input.len() > MAX_READER_OUTPUT_BYTES - self.bytes.len() {
            return Err(std::io::Error::other("reader output exceeds 8 MiB"));
        }
        self.bytes.extend_from_slice(input);
        Ok(input.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

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

pub fn read_with(
    url: &str,
    reader: &str,
    transport: &mut impl Transport,
    clock: impl FnOnce() -> String,
) -> ProviderResult<PageSnapshot> {
    let parsed = crate::urls::parse(url);
    if !["http", "https"].contains(&parsed.scheme.as_str()) || parsed.authority.is_empty() {
        return Err(ProviderError::invalid_value(
            "only http and https URLs are supported",
        ));
    }
    if !["auto", "jina", "direct"].contains(&reader) {
        return Err(ProviderError::invalid_value(
            "reader must be one of: auto, jina, direct",
        ));
    }
    if reader == "direct" {
        return direct_with(url, transport, clock);
    }
    match jina_response(url, transport) {
        Ok(mut page) => {
            page.fetched_at = clock();
            Ok(page)
        }
        Err(error) if reader == "auto" && error.kind == "FetchError" => {
            direct_with(url, transport, clock)
        }
        Err(error) => Err(error),
    }
}
fn jina_response(url: &str, transport: &mut impl Transport) -> ProviderResult<PageSnapshot> {
    let mut quoted = String::new();
    for byte in url.bytes() {
        if byte.is_ascii_alphanumeric() || b"-._~".contains(&byte) {
            quoted.push(char::from(byte));
        } else {
            use std::fmt::Write;
            write!(quoted, "%{byte:02X}").unwrap();
        }
    }
    let response = transport
        .get(&Request {
            url: format!("https://r.jina.ai/{quoted}"),
            headers: BTreeMap::from([("Accept".into(), "text/plain".into())]),
        })
        .map_err(|error| ProviderError::reader_transport_error(error.kind))?;
    let text = response.text();
    let content =
        text.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c));
    if error_payload(content) {
        return Err(ProviderError::reader_payload_error());
    }
    let title = content
        .split([
            '\n', '\r', '\u{b}', '\u{c}', '\u{1c}', '\u{1d}', '\u{1e}', '\u{85}', '\u{2028}',
            '\u{2029}',
        ])
        .map(|line| {
            line.trim_matches(['#', ' '])
                .trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
        })
        .find(|line| !line.is_empty())
        .map(|line| line.chars().take(160).collect())
        .unwrap_or_else(|| url.into());
    Ok(PageSnapshot {
        url: url.into(),
        title,
        content: content.into(),
        source: "jina-reader".into(),
        fetched_at: String::new(),
        status_code: Some(response.status),
        content_type: response.headers.get("content-type").cloned(),
    })
}
fn error_payload(content: &str) -> bool {
    use serde_json::value::RawValue;
    let Ok(fields) =
        serde_json::from_str::<BTreeMap<String, Box<RawValue>>>(&python_constants(content))
    else {
        return false;
    };
    let integer_failure = ["status", "code"].iter().any(|name| {
        fields.get(*name).is_some_and(|value| {
            let digits = value.get();
            digits.bytes().all(|byte| byte.is_ascii_digit())
                && (digits.len() > 3 || (digits.len() == 3 && digits >= "400"))
        })
    });
    let identity = fields
        .get("name")
        .is_some_and(|v| json_string_identity(v.get()));
    integer_failure
        && identity
        && (fields.contains_key("message") || fields.contains_key("readableMessage"))
}

// Python JSON permits nonfinite constants. Replacing only unquoted constants with
// null preserves error classification (not integer status/name, message presence).
fn python_constants(content: &str) -> String {
    let bytes = content.as_bytes();
    let mut result = Vec::with_capacity(bytes.len());
    let (mut index, mut quoted, mut escaped) = (0, false, false);
    while index < bytes.len() {
        let byte = bytes[index];
        if quoted {
            result.push(byte);
            index += 1;
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                quoted = false;
            }
        } else if byte == b'"' {
            quoted = true;
            result.push(byte);
            index += 1;
        } else if let Some(token) = [b"-Infinity".as_slice(), b"Infinity", b"NaN"]
            .into_iter()
            .find(|token| bytes[index..].starts_with(token))
        {
            result.extend_from_slice(b"null");
            index += token.len();
        } else {
            result.push(byte);
            index += 1;
        }
    }
    String::from_utf8(result).unwrap()
}
// Only the ASCII identity predicate is needed; replacement of surrogate scalars
// cannot create/remove an ASCII Error substring across a Unicode boundary.
fn json_string_identity(raw: &str) -> bool {
    if !raw.starts_with('"') {
        return false;
    }
    let mut chars = raw[1..raw.len() - 1].chars();
    let mut decoded = String::new();
    while let Some(c) = chars.next() {
        if c != '\\' {
            decoded.push(c);
            continue;
        }
        match chars.next() {
            Some('u') => {
                let hex: String = chars.by_ref().take(4).collect();
                let value = u32::from_str_radix(&hex, 16).unwrap();
                decoded.push(char::from_u32(value).unwrap_or('�'));
            }
            Some('n') => decoded.push('\n'),
            Some('r') => decoded.push('\r'),
            Some('t') => decoded.push('\t'),
            Some('b') => decoded.push('\u{8}'),
            Some('f') => decoded.push('\u{c}'),
            Some(c) => decoded.push(c),
            None => unreachable!(),
        }
    }
    decoded.contains("Error")
}

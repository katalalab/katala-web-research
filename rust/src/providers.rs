//! Provider boundary; strict offline adapters never fall through to network.
pub mod github;
pub mod github_repo;
pub mod json;
pub mod meta;
pub mod openalex;
use crate::{
    http::{HttpResponse, Settings},
    registry::Registry,
    search::SearchResult,
};
use std::{
    collections::{BTreeMap, VecDeque},
    fmt,
};

pub const NETWORK_PROVIDERS: [&str; 8] = [
    "ddg",
    "github",
    "github_code",
    "jina",
    "searxng",
    "brave",
    "openalex",
    "meta",
];
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Request {
    pub url: String,
    pub headers: BTreeMap<String, String>,
}
#[derive(Debug)]
pub struct ProviderError {
    pub kind: &'static str,
    message: String,
}
impl ProviderError {
    pub fn synthetic(kind: &'static str) -> Self {
        Self {
            kind,
            message: format!("synthetic provider failure ({kind})"),
        }
    }
    pub fn synthetic_http_status(status: u16) -> Self {
        Self {
            kind: "FetchError",
            message: format!("HTTP {status} synthetic provider failure"),
        }
    }
    pub fn has_http_status(&self, status: u16) -> bool {
        self.kind == "FetchError" && self.message.starts_with(&format!("HTTP {status} "))
    }
    pub(crate) fn invalid_value(message: &'static str) -> Self {
        Self {
            kind: "ValueError",
            message: message.into(),
        }
    }
    fn unexpected() -> Self {
        Self {
            kind: "FixtureError",
            message: "unscripted or mismatched provider request".into(),
        }
    }
}
impl fmt::Display for ProviderError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for ProviderError {}
pub type ProviderResult<T> = std::result::Result<T, ProviderError>;
pub trait Transport {
    fn get(&mut self, request: &Request) -> ProviderResult<HttpResponse>;
}
pub struct NativeTransport {
    pub settings: Settings,
}
#[derive(Default)]
pub struct EnvTransport {
    native: Option<NativeTransport>,
}
impl Transport for EnvTransport {
    fn get(&mut self, request: &Request) -> ProviderResult<HttpResponse> {
        if self.native.is_none() {
            let settings = Settings::from_env().map_err(|e| ProviderError {
                kind: e.kind,
                message: e.to_string(),
            })?;
            self.native = Some(NativeTransport { settings });
        }
        self.native.as_mut().unwrap().get(request)
    }
}
impl Transport for NativeTransport {
    fn get(&mut self, request: &Request) -> ProviderResult<HttpResponse> {
        let headers = request
            .headers
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_str()))
            .collect::<Vec<_>>();
        crate::http::fetch_url(&request.url, &headers, &self.settings).map_err(|e| ProviderError {
            kind: e.kind,
            message: e.to_string(),
        })
    }
}
pub struct Step {
    pub request: Request,
    pub outcome: ProviderResult<HttpResponse>,
}
pub struct OfflineTransport {
    steps: VecDeque<Step>,
    pub calls: usize,
    failed: bool,
}
impl OfflineTransport {
    pub fn new(steps: Vec<Step>) -> Self {
        Self {
            steps: steps.into(),
            calls: 0,
            failed: false,
        }
    }
    pub fn finish(self) -> ProviderResult<()> {
        if self.steps.is_empty() && !self.failed {
            Ok(())
        } else {
            Err(ProviderError::unexpected())
        }
    }
}
impl Transport for OfflineTransport {
    fn get(&mut self, request: &Request) -> ProviderResult<HttpResponse> {
        self.calls += 1;
        let Some(step) = self.steps.pop_front() else {
            self.failed = true;
            return Err(ProviderError::unexpected());
        };
        if step.request != *request {
            self.failed = true;
            return Err(ProviderError::unexpected());
        }
        step.outcome
    }
}
pub struct Context<'a> {
    pub registry: &'a Registry,
    pub year: i32,
}
pub trait SearchProvider {
    fn name(&self) -> &'static str;
    fn search(
        &self,
        query: &str,
        limit: i64,
        transport: &mut dyn Transport,
        context: &Context<'_>,
    ) -> ProviderResult<Vec<SearchResult>>;
}
pub struct DuckDuckGo;
pub fn ddg_request(query: &str) -> Request {
    let query = url::form_urlencoded::Serializer::new(String::new())
        .append_pair("q", query)
        .finish()
        .replace('*', "%2A")
        .replace("%7E", "~");
    Request {
        url: format!("https://html.duckduckgo.com/html/?{query}"),
        headers: [("Accept".into(), "text/html".into())].into(),
    }
}
impl SearchProvider for DuckDuckGo {
    fn name(&self) -> &'static str {
        "ddg"
    }
    fn search(
        &self,
        query: &str,
        limit: i64,
        transport: &mut dyn Transport,
        context: &Context<'_>,
    ) -> ProviderResult<Vec<SearchResult>> {
        let response = transport.get(&ddg_request(query))?;
        let mut results = crate::search::slice(parse_ddg(&response.text()), limit);
        for (index, result) in results.iter_mut().enumerate() {
            result.rank = index as i64 + 1;
        }
        Ok(crate::search::rank(
            query,
            results,
            context.registry,
            context.year,
        ))
    }
}

#[derive(Default)]
struct DdgParser {
    results: Vec<SearchResult>,
    in_title: bool,
    in_snippet: bool,
    snippet_tag: String,
    title: Vec<String>,
    url: String,
    snippet: Vec<String>,
}
impl DdgParser {
    fn flush(&mut self) {
        let title = crate::text::collapse(&self.title.join(" "));
        if !title.is_empty() && !self.url.is_empty() {
            self.results.push(SearchResult {
                title,
                url: self.url.clone(),
                snippet: crate::text::collapse(&self.snippet.join(" ")),
                source: "ddg".into(),
                published_at: None,
                rank: 0,
                score: 0.0,
                metadata: BTreeMap::new(),
            });
        }
        self.title.clear();
        self.url.clear();
        self.snippet.clear();
    }
    fn start(&mut self, name: &str, attrs: BTreeMap<String, String>) {
        let classes = attrs
            .get("class")
            .map(String::as_str)
            .unwrap_or("")
            .split_whitespace()
            .collect::<Vec<_>>();
        if name == "a" && classes.contains(&"result__a") {
            self.flush();
            self.in_title = true;
            self.url =
                crate::text::normalize_url(attrs.get("href").map(String::as_str).unwrap_or(""));
        } else if classes.contains(&"result__snippet") {
            self.in_snippet = true;
            self.snippet_tag = name.into();
        }
    }
    fn end(&mut self, name: &str) {
        if name == "a" && self.in_title {
            self.in_title = false;
        }
        if self.in_snippet && name == self.snippet_tag {
            self.in_snippet = false;
        }
    }
    fn data(&mut self, value: &str, raw: bool) {
        let value = if raw {
            value.into()
        } else {
            crate::text::unescape(value)
        };
        if self.in_title {
            self.title.push(value);
        } else if self.in_snippet {
            self.snippet.push(value);
        }
    }
}
pub fn parse_ddg(html: &str) -> Vec<SearchResult> {
    use std::sync::LazyLock;
    static ATTR: LazyLock<regex::Regex> = LazyLock::new(|| {
        regex::Regex::new(r#"([^\s/=>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?"#).unwrap()
    });
    let mut parser = DdgParser::default();
    let mut offset = 0;
    let mut raw_mode: Option<String> = None;
    while offset < html.len() {
        if let Some(name) = &raw_mode {
            let closing = format!("</{name}");
            let bytes = &html.as_bytes()[offset..];
            let found = bytes
                .windows(closing.len())
                .enumerate()
                .find(|(index, w)| {
                    w.eq_ignore_ascii_case(closing.as_bytes())
                        && bytes
                            .get(index + closing.len())
                            .is_some_and(|c| c.is_ascii_whitespace() || *c == b'>')
                })
                .map(|(index, _)| index);
            let Some(index) = found else {
                parser.data(&html[offset..], true);
                break;
            };
            parser.data(&html[offset..offset + index], true);
            offset += index;
            raw_mode = None;
        }
        let rest = &html[offset..];
        let Some(open) = rest.find('<') else {
            parser.data(rest, false);
            break;
        };
        parser.data(&rest[..open], false);
        offset += open;
        if html[offset..].starts_with("<!--") {
            offset += html[offset..]
                .find("-->")
                .map_or(html.len() - offset, |n| n + 3);
            continue;
        }
        let mut quote = None;
        let mut close = None;
        for (index, c) in html[offset + 1..].char_indices() {
            if let Some(q) = quote {
                if c == q {
                    quote = None;
                }
            } else if c == '\'' || c == '"' {
                quote = Some(c);
            } else if c == '>' {
                close = Some(offset + 1 + index);
                break;
            }
        }
        let Some(end) = close else {
            break;
        };
        let raw = &html[offset + 1..end];
        let start = offset;
        offset = end + 1;
        if raw.starts_with(['!', '?']) {
            continue;
        }
        if raw.chars().next().is_some_and(char::is_whitespace) {
            parser.data(&html[start..offset], false);
            continue;
        }
        let ending = raw.starts_with('/');
        let raw = raw.trim_start_matches('/');
        let name = raw
            .split(|c: char| c.is_whitespace() || c == '/')
            .next()
            .unwrap_or("");
        if !name.chars().next().is_some_and(|c| c.is_ascii_alphabetic()) {
            parser.data(&html[start..offset], false);
            continue;
        }
        let lowered = name.to_ascii_lowercase();
        if ending {
            parser.end(&lowered);
            continue;
        }
        let mut attrs = BTreeMap::new();
        let tail = &raw[name.len()..];
        let mut attribute_end = 0;
        for caps in ATTR.captures_iter(tail) {
            attribute_end = caps.get(0).unwrap().end();
            let value = (2..=4)
                .find_map(|i| caps.get(i).map(|m| m.as_str()))
                .unwrap_or("");
            attrs.insert(caps[1].to_ascii_lowercase(), crate::text::unescape(value));
        }
        parser.start(&lowered, attrs);
        // A slash consumed by an unquoted attribute belongs to that value.
        // Only a remaining slash is the HTMLParser self-closing delimiter.
        if tail[attribute_end..].trim() == "/" {
            parser.end(&lowered);
        } else if ["script", "style"].contains(&lowered.as_str()) {
            raw_mode = Some(lowered);
        }
    }
    parser.flush();
    parser.results
}

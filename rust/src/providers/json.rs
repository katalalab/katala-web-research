//! Normal JSON response adapters. Credential/config values are never diagnostic text.
use super::{Context, ProviderError, ProviderResult, Request, SearchProvider, Transport};
use crate::search::SearchResult;
use serde_json::{Map, Value};
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Searxng,
    Brave,
    Jina,
}
impl Kind {
    pub fn named(name: &str) -> Option<Self> {
        match name {
            "searxng" => Some(Self::Searxng),
            "brave" => Some(Self::Brave),
            "jina" => Some(Self::Jina),
            _ => None,
        }
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::Searxng => "searxng",
            Self::Brave => "brave",
            Self::Jina => "jina",
        }
    }
}
pub struct Config {
    values: BTreeMap<String, String>,
}
impl Config {
    pub fn from_values(values: BTreeMap<String, String>) -> Self {
        Self { values }
    }
    pub fn from_env(kind: Kind) -> ProviderResult<Self> {
        let names: &[&str] = match kind {
            Kind::Searxng => &[
                "KWR_SEARXNG_URL",
                "KWR_SEARXNG_CATEGORIES",
                "KWR_SEARXNG_ENGINES",
                "KWR_SEARXNG_LANGUAGE",
                "KWR_SEARXNG_TIME_RANGE",
                "KWR_SEARXNG_SAFESEARCH",
            ],
            Kind::Brave => &[
                "BRAVE_SEARCH_API_KEY",
                "BRAVE_SEARCH_COUNTRY",
                "BRAVE_SEARCH_LANG",
                "BRAVE_UI_LANG",
                "BRAVE_FRESHNESS",
                "BRAVE_SAFESEARCH",
            ],
            Kind::Jina => &["JINA_API_KEY"],
        };
        let mut values = BTreeMap::new();
        for name in names {
            match std::env::var(name) {
                Ok(value) => {
                    values.insert((*name).into(), value);
                }
                Err(std::env::VarError::NotPresent) => {}
                Err(_) => return Err(failure("FetchError", format!("{name} must be UTF-8"))),
            }
        }
        Ok(Self { values })
    }
    fn get(&self, key: &str) -> &str {
        self.values.get(key).map(String::as_str).unwrap_or("")
    }
}
pub struct JsonSearch {
    pub kind: Kind,
    pub config: Config,
}
fn failure(kind: &'static str, message: impl Into<String>) -> ProviderError {
    ProviderError {
        kind,
        message: message.into(),
    }
}
fn stripped(value: &str) -> &str {
    value.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
}
fn request(base: &str, params: Vec<(&str, String)>, headers: BTreeMap<String, String>) -> Request {
    let mut form = url::form_urlencoded::Serializer::new(String::new());
    form.extend_pairs(params);
    Request {
        url: format!(
            "{base}?{}",
            form.finish().replace('*', "%2A").replace("%7E", "~")
        ),
        headers,
    }
}
fn date_range(value: &str) -> bool {
    let Some((start, end)) = value.split_once("to") else {
        return false;
    };
    [start, end].into_iter().all(|s| {
        let chars = s.chars().collect::<Vec<_>>();
        chars.len() == 10
            && chars[4] == '-'
            && chars[7] == '-'
            && chars.iter().any(|c| crate::python_digits::is_digit(*c))
            && chars
                .iter()
                .all(|c| *c == '-' || crate::python_digits::is_digit(*c))
    })
}
fn brave_freshness(raw: &str) -> ProviderResult<String> {
    let raw = stripped(raw);
    let value = match raw.to_lowercase().as_str() {
        "day" | "past_day" => "pd",
        "week" | "past_week" => "pw",
        "month" | "past_month" => "pm",
        "year" | "past_year" => "py",
        _ => raw,
    };
    if value.is_empty() || ["pd", "pw", "pm", "py"].contains(&value) || date_range(value) {
        Ok(value.into())
    } else {
        Err(failure(
            "FetchError",
            "BRAVE_FRESHNESS must be day/week/month/year, pd/pw/pm/py, or YYYY-MM-DDtoYYYY-MM-DD",
        ))
    }
}
impl JsonSearch {
    fn page_request(&self, query: &str, page: i64) -> ProviderResult<Request> {
        let mut params = vec![("q", query.into())];
        let mut headers: BTreeMap<String, String> =
            [("Accept".into(), "application/json".into())].into();
        let base = match self.kind {
            Kind::Searxng => {
                params.push(("format", "json".into()));
                if page > 1 {
                    params.push(("pageno", page.to_string()));
                }
                for (name, key) in [
                    ("KWR_SEARXNG_CATEGORIES", "categories"),
                    ("KWR_SEARXNG_ENGINES", "engines"),
                    ("KWR_SEARXNG_LANGUAGE", "language"),
                    ("KWR_SEARXNG_TIME_RANGE", "time_range"),
                    ("KWR_SEARXNG_SAFESEARCH", "safesearch"),
                ] {
                    let value = stripped(self.config.get(name));
                    if value.is_empty() {
                        continue;
                    }
                    if key == "time_range" && !["day", "week", "month", "year"].contains(&value) {
                        return Err(failure(
                            "FetchError",
                            format!("{name} must be one of: day, week, month, year"),
                        ));
                    }
                    if key == "safesearch" {
                        if !value.chars().all(crate::python_digits::is_digit) {
                            return Err(failure(
                                "FetchError",
                                format!("{name} must be an integer from 0 to 2"),
                            ));
                        }
                        let mut level = 0u32;
                        for c in value.chars() {
                            let digit = crate::python_digits::decimal(c).ok_or_else(|| {
                                failure(
                                    "ValueError",
                                    "safesearch digits cannot be converted to an integer",
                                )
                            })?;
                            level = (level * 10 + digit).min(3);
                        }
                        if level > 2 {
                            return Err(failure(
                                "FetchError",
                                format!("{name} must be an integer from 0 to 2"),
                            ));
                        }
                    }
                    params.push((key, value.into()));
                }
                format!(
                    "{}/search",
                    self.config.get("KWR_SEARXNG_URL").trim_end_matches('/')
                )
            }
            Kind::Brave => {
                params.push(("count", "20".into()));
                if page > 1 {
                    params.push(("offset", (page - 1).to_string()));
                }
                for (name, key) in [
                    ("BRAVE_SEARCH_COUNTRY", "country"),
                    ("BRAVE_SEARCH_LANG", "search_lang"),
                    ("BRAVE_UI_LANG", "ui_lang"),
                ] {
                    let value = stripped(self.config.get(name));
                    if !value.is_empty() {
                        params.push((key, value.into()));
                    }
                }
                let freshness = brave_freshness(self.config.get("BRAVE_FRESHNESS"))?;
                if !freshness.is_empty() {
                    params.push(("freshness", freshness));
                }
                let safe = stripped(self.config.get("BRAVE_SAFESEARCH")).to_lowercase();
                if !safe.is_empty() {
                    if !["off", "moderate", "strict"].contains(&safe.as_str()) {
                        return Err(failure(
                            "FetchError",
                            "BRAVE_SAFESEARCH must be off, moderate, or strict",
                        ));
                    }
                    params.push(("safesearch", safe));
                }
                headers.insert(
                    "X-Subscription-Token".into(),
                    self.config.get("BRAVE_SEARCH_API_KEY").into(),
                );
                "https://api.search.brave.com/res/v1/web/search".into()
            }
            Kind::Jina => {
                headers.insert(
                    "Authorization".into(),
                    format!("Bearer {}", self.config.get("JINA_API_KEY")),
                );
                "https://s.jina.ai/".into()
            }
        };
        Ok(request(&base, params, headers))
    }
}
fn object(value: &Value) -> ProviderResult<&Map<String, Value>> {
    value
        .as_object()
        .ok_or_else(|| failure("AttributeError", "provider response must be an object"))
}
fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(v) => *v,
        Value::Number(n) => n.as_f64().is_some_and(|n| n != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(v) => !v.is_empty(),
        Value::Object(v) => !v.is_empty(),
    }
}
fn results(value: Option<&Value>, jina: bool) -> ProviderResult<&[Value]> {
    match value {
        None => Ok(&[]),
        Some(Value::Array(v)) => Ok(v),
        Some(v) if !jina && !truthy(v) => Ok(&[]),
        Some(Value::String(s)) if s.is_empty() => Ok(&[]),
        Some(Value::String(_)) => Err(failure(
            "AttributeError",
            "provider result items must be objects",
        )),
        Some(Value::Object(_)) if !jina => Err(failure(
            "AttributeError",
            "provider result items must be objects",
        )),
        Some(_) => Err(failure("TypeError", "provider results must be a list")),
    }
}
fn field(item: &Map<String, Value>, names: &[&str]) -> ProviderResult<String> {
    for name in names {
        if let Some(value) = item.get(*name)
            && truthy(value)
        {
            return value.as_str().map(str::to_string).ok_or_else(|| {
                failure("TypeError", format!("provider field {name} must be text"))
            });
        }
    }
    Ok(String::new())
}
fn published(item: &Map<String, Value>, names: &[&str]) -> ProviderResult<Option<String>> {
    for (index, name) in names.iter().enumerate() {
        if let Some(value) = item.get(*name) {
            if value.is_null() || (index + 1 < names.len() && !truthy(value)) {
                continue;
            }
            let text = value.as_str().ok_or_else(|| {
                failure(
                    "TypeError",
                    "provider publication field must be text or null",
                )
            })?;
            let prefix = text.chars().take(4).collect::<String>();
            if prefix.chars().count() == 4
                && prefix.chars().all(crate::python_digits::is_digit)
                && crate::python_digits::decimal_int(&prefix).is_none()
            {
                return Err(failure(
                    "ValueError",
                    "publication digits cannot be converted to a year",
                ));
            }
            return Ok(Some(text.into()));
        }
    }
    Ok(None)
}
impl SearchProvider for JsonSearch {
    fn name(&self) -> &'static str {
        self.kind.name()
    }
    fn search(
        &self,
        query: &str,
        limit: i64,
        transport: &mut dyn Transport,
        context: &Context<'_>,
    ) -> ProviderResult<Vec<SearchResult>> {
        let (required, label) = match self.kind {
            Kind::Searxng => ("KWR_SEARXNG_URL", "SearXNG"),
            Kind::Brave => ("BRAVE_SEARCH_API_KEY", "Brave"),
            Kind::Jina => ("JINA_API_KEY", "Jina"),
        };
        let configured = if self.kind == Kind::Searxng {
            self.config.get(required).trim_end_matches('/')
        } else {
            self.config.get(required)
        };
        if configured.is_empty() {
            return Err(failure(
                "FetchError",
                format!("{required} is required for {label} search"),
            ));
        }
        let requested = limit.max(0);
        if requested == 0 && self.kind != Kind::Jina {
            return Ok(vec![]);
        }
        let pages = match self.kind {
            Kind::Searxng => (requested - 1) / 20 + 1,
            Kind::Brave => ((requested - 1) / 20 + 1).min(10),
            Kind::Jina => 1,
        };
        let mut found = Vec::new();
        for page in 1..=pages {
            let request = self.page_request(query, page)?;
            let response = transport.get(&request)?;
            let payload: Value = serde_json::from_str(&response.text()).map_err(|_| {
                failure(
                    "FetchError",
                    format!(
                        "non-JSON response from {}",
                        crate::http::redact_url(&request.url)
                    ),
                )
            })?;
            let payload = object(&payload)?;
            let entries = match self.kind {
                Kind::Searxng => results(payload.get("results"), false)?,
                Kind::Brave => match payload.get("web").filter(|v| truthy(v)) {
                    Some(web) => results(object(web)?.get("results"), false)?,
                    None => &[],
                },
                Kind::Jina => results(payload.get("data"), true)?,
            };
            if entries.is_empty() {
                break;
            }
            let end = if self.kind == Kind::Jina {
                if limit >= 0 {
                    entries.len().min(limit as usize)
                } else {
                    entries
                        .len()
                        .saturating_sub(limit.unsigned_abs().min(usize::MAX as u64) as usize)
                }
            } else {
                entries.len()
            };
            for value in &entries[..end] {
                if self.kind != Kind::Jina && found.len() as i64 >= requested {
                    break;
                }
                let item = object(value)?;
                let snippet = match self.kind {
                    Kind::Searxng => field(item, &["content"]),
                    Kind::Brave => field(item, &["description"]),
                    Kind::Jina => field(item, &["description", "content"]),
                }?;
                let dates = match self.kind {
                    Kind::Searxng => &["publishedDate"][..],
                    Kind::Brave => &["age"][..],
                    Kind::Jina => &["publishedTime", "published_at"][..],
                };
                found.push(SearchResult {
                    title: field(item, &["title", "url"])?,
                    url: field(item, &["url"])?,
                    snippet,
                    source: self.name().into(),
                    published_at: published(item, dates)?,
                    rank: found.len() as i64 + 1,
                    score: 0.0,
                    metadata: BTreeMap::new(),
                });
            }
            if self.kind != Kind::Jina && found.len() as i64 >= requested {
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

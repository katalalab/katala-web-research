//! Native OpenAlex search/normalization; citation graph/cache remain separate.
use super::{Context, ProviderError, ProviderResult, Request, SearchProvider, Transport};
use crate::{
    process::{NativeRunner, OUTPUT_LIMIT, ProcessRequest, ProcessRunner},
    search::SearchResult,
};
use serde_json::{Map, Value};
use std::collections::BTreeMap;

pub const SELECT: &str = "id,doi,title,display_name,publication_year,publication_date,type,cited_by_count,is_retracted,open_access,primary_location,best_oa_location,content_urls,abstract_inverted_index";
pub struct OpenAlex {
    values: Option<BTreeMap<String, String>>,
}
fn failure(kind: &'static str) -> ProviderError {
    ProviderError::synthetic(kind)
}
fn strip(s: &str) -> &str {
    s.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
}
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(v) => *v,
        Value::Number(v) => v.as_f64().is_some_and(|n| n != 0.0),
        Value::String(v) => !v.is_empty(),
        Value::Array(v) => !v.is_empty(),
        Value::Object(v) => !v.is_empty(),
    }
}
fn get<'a>(m: &'a Map<String, Value>, key: &str) -> Option<&'a Value> {
    m.get(key).filter(|v| truthy(v))
}
fn object(v: &Value) -> ProviderResult<&Map<String, Value>> {
    v.as_object().ok_or_else(|| failure("AttributeError"))
}
fn text(v: Option<&Value>) -> ProviderResult<String> {
    match v {
        None | Some(Value::Null) => Ok(String::new()),
        Some(Value::String(s)) => Ok(s.clone()),
        _ => Err(failure("TypeError")),
    }
}
fn scalar(v: &Value) -> ProviderResult<String> {
    match v {
        Value::String(s) => Ok(s.clone()),
        Value::Number(n) => Ok(n.to_string()),
        Value::Bool(true) => Ok("True".into()),
        Value::Bool(false) => Ok("False".into()),
        Value::Null => Ok("None".into()),
        _ => Err(failure("TypeError")),
    }
}
fn nonempty(v: &Value) -> bool {
    !v.is_null() && v != &Value::String(String::new())
}

/// Preserve the reference spelling rules; search metadata does not use this helper.
pub fn work_id(seed: &str) -> ProviderResult<String> {
    let seed = strip(seed);
    if seed.is_empty() {
        return Err(failure("ValueError"));
    }
    if seed.starts_with("https://openalex.org/")
        || seed.starts_with("https://api.openalex.org/works/")
    {
        return Ok(seed.rsplit('/').next().unwrap().into());
    }
    if seed.starts_with("https://doi.org/") || seed.starts_with("http://doi.org/") {
        return Ok(seed.into());
    }
    if seed.starts_with("10.") {
        return Ok(format!("https://doi.org/{seed}"));
    }
    Ok(seed.into())
}
pub fn abstract_from_index(value: Option<&Value>) -> String {
    let Some(Value::Object(m)) = value else {
        return String::new();
    };
    let mut positions = Vec::new();
    for (word, indexes) in m {
        let Some(indexes) = indexes.as_array() else {
            continue;
        };
        for index in indexes {
            let position = match index {
                Value::Bool(v) => Some(i128::from(*v)),
                Value::Number(n) => n
                    .as_i64()
                    .map(i128::from)
                    .or_else(|| n.as_u64().map(i128::from)),
                _ => None,
            };
            if let Some(position) = position {
                positions.push((position, word.as_str()));
            }
        }
    }
    positions.sort_unstable();
    positions
        .into_iter()
        .map(|(_, word)| word)
        .collect::<Vec<_>>()
        .join(" ")
}
fn nested<'a>(
    m: &'a Map<String, Value>,
    key: &str,
    empty: &'a Map<String, Value>,
) -> ProviderResult<&'a Map<String, Value>> {
    match get(m, key) {
        Some(v) => object(v),
        None => Ok(empty),
    }
}
fn metadata(m: &Map<String, Value>) -> BTreeMap<String, Value> {
    let mut out = BTreeMap::new();
    for (to, from) in [
        ("openalex_id", "id"),
        ("doi", "doi"),
        ("work_type", "type"),
        ("publication_year", "publication_year"),
        ("cited_by_count", "cited_by_count"),
    ] {
        if let Some(v) = m.get(from).filter(|v| nonempty(v)) {
            out.insert(to.into(), v.clone());
        }
    }
    if let Some(Value::Object(content)) = m.get("content_urls")
        && let Some(v) = get(content, "pdf")
    {
        out.insert("content_url".into(), v.clone());
    }
    for (prefix, key) in [
        ("primary", "primary_location"),
        ("best_oa", "best_oa_location"),
    ] {
        if let Some(Value::Object(location)) = m.get(key) {
            for field in ["landing_page_url", "pdf_url", "is_oa", "license", "version"] {
                if let Some(v) = location.get(field).filter(|v| nonempty(v)) {
                    out.insert(format!("{prefix}_{field}"), v.clone());
                }
            }
            if let Some(Value::Object(source)) = location.get("source") {
                for field in ["id", "display_name", "type"] {
                    if let Some(v) = source.get(field).filter(|v| nonempty(v)) {
                        out.insert(format!("{prefix}_source_{field}"), v.clone());
                    }
                }
            }
        }
    }
    if let Some(Value::Object(oa)) = m.get("open_access") {
        for key in ["is_oa", "oa_status"] {
            if let Some(v) = oa.get(key).filter(|v| nonempty(v)) {
                out.insert(format!("open_access_{key}"), v.clone());
            }
        }
    }
    out
}
fn result(item: &Value, index: usize) -> ProviderResult<SearchResult> {
    let m = object(item)?;
    let empty = Map::new();
    let primary = nested(m, "primary_location", &empty)?;
    let location_url = if let Some(primary_url) = get(primary, "landing_page_url") {
        Some(primary_url)
    } else {
        get(nested(m, "best_oa_location", &empty)?, "landing_page_url")
    };
    let url = location_url
        .or_else(|| get(m, "doi"))
        .or_else(|| get(m, "id"))
        .map(scalar)
        .transpose()?
        .unwrap_or_default();
    let title = text(
        get(m, "display_name")
            .or_else(|| get(m, "title"))
            .or_else(|| get(m, "id")),
    )?;
    let published_at = if let Some(v) = get(m, "publication_date") {
        Some(text(Some(v))?)
    } else {
        match m.get("publication_year") {
            Some(Value::Bool(v)) => Some(format!("{}-01-01", if *v { "True" } else { "False" })),
            Some(Value::Number(n)) if n.is_i64() || n.is_u64() => Some(format!("{n}-01-01")),
            _ => None,
        }
    };
    let mut parts = Vec::new();
    let abstract_text = abstract_from_index(m.get("abstract_inverted_index"));
    if !abstract_text.is_empty() {
        parts.push(crate::text::truncate(&abstract_text, 420));
    }
    if let Some(v) = get(m, "publication_year") {
        parts.push(format!("year={}", scalar(v)?));
    }
    if let Some(v) = get(m, "type") {
        parts.push(format!("type={}", scalar(v)?));
    }
    if let Some(v) = m.get("cited_by_count").filter(|v| !v.is_null()) {
        parts.push(format!("citations={}", scalar(v)?));
    }
    if get(m, "is_retracted").is_some() {
        parts.push("retracted=true".into());
    }
    let oa = nested(m, "open_access", &empty)?;
    if let Some(v) = oa.get("is_oa").filter(|v| !v.is_null()) {
        parts.push(format!("oa={}", scalar(v)?.to_lowercase()));
    }
    let source = nested(primary, "source", &empty)?;
    if let Some(v) = get(source, "display_name") {
        parts.push(format!("source={}", scalar(v)?));
    }
    Ok(SearchResult {
        title,
        url,
        snippet: parts.join(" | "),
        source: "openalex".into(),
        published_at,
        rank: index as i64,
        score: 0.0,
        metadata: metadata(m),
    })
}
fn params_url(params: Vec<(&str, String)>) -> String {
    let mut form = url::form_urlencoded::Serializer::new(String::new());
    form.extend_pairs(params);
    format!(
        "https://api.openalex.org/works?{}",
        form.finish().replace('*', "%2A").replace("%7E", "~")
    )
}
impl OpenAlex {
    pub fn from_env() -> Self {
        Self { values: None }
    }
    pub fn with_values(values: BTreeMap<String, String>) -> Self {
        Self {
            values: Some(values),
        }
    }
    fn value(&self, key: &str) -> ProviderResult<String> {
        if let Some(values) = &self.values {
            return Ok(values.get(key).cloned().unwrap_or_default());
        }
        match std::env::var(key) {
            Ok(v) => Ok(v),
            Err(std::env::VarError::NotPresent) => Ok(String::new()),
            Err(_) => Err(failure("FetchError")),
        }
    }
    fn credentials(
        &self,
        runner: &mut dyn ProcessRunner,
    ) -> ProviderResult<Vec<(&'static str, String)>> {
        let raw = self.value("OPENALEX_API_KEY")?;
        let token = if raw.starts_with("op://") {
            if !runner.available("op")? {
                String::new()
            } else {
                let request = ProcessRequest {
                    program: "op".into(),
                    args: vec!["read".into(), raw],
                    timeout_ms: 10_000,
                    output_limit: OUTPUT_LIMIT,
                };
                match runner.run(&request) {
                    Err(e) if e.kind == "TimeoutExpired" => String::new(),
                    Err(e) => return Err(e),
                    Ok(output) => {
                        let stdout = std::str::from_utf8(&output.stdout)
                            .map_err(|_| failure("UnicodeDecodeError"))?;
                        std::str::from_utf8(&output.stderr)
                            .map_err(|_| failure("UnicodeDecodeError"))?;
                        if output.return_code == 0 {
                            stdout.replace("\r\n", "\n").replace('\r', "\n")
                        } else {
                            String::new()
                        }
                    }
                }
            }
        } else {
            raw
        };
        let mut params = Vec::new();
        if !strip(&token).is_empty() {
            params.push(("api_key", strip(&token).into()));
        }
        let mailto = self.value("OPENALEX_MAILTO")?;
        if !strip(&mailto).is_empty() {
            params.push(("mailto", strip(&mailto).into()));
        }
        Ok(params)
    }
    fn params(
        &self,
        query: &str,
        limit: i64,
        cursor: &str,
        runner: &mut dyn ProcessRunner,
    ) -> ProviderResult<Vec<(&'static str, String)>> {
        let mut params = vec![
            ("search", query.into()),
            ("per_page", limit.min(100).to_string()),
            ("cursor", cursor.into()),
            ("sort", "relevance_score:desc".into()),
            ("select", SELECT.into()),
        ];
        params.extend(self.credentials(runner)?);
        let mut filters = Vec::new();
        let language = self.value("OPENALEX_LANGUAGE")?;
        let language = strip(&language);
        if !language.is_empty() && language.to_lowercase() != "all" {
            let iso2 = language
                .split('-')
                .next()
                .unwrap()
                .split('_')
                .next()
                .unwrap()
                .to_lowercase();
            if iso2.chars().count() == 2 && iso2.chars().all(crate::python_alpha::is_alpha) {
                filters.push(format!("language:{iso2}"));
            }
        }
        let year = self.value("OPENALEX_YEAR")?;
        let year = strip(&year);
        if year.chars().count() == 4 && year.chars().all(crate::python_digits::is_digit) {
            filters.push(format!("publication_year:{year}"));
        }
        for (name, key) in [
            ("from_publication_date", "OPENALEX_FROM_DATE"),
            ("to_publication_date", "OPENALEX_TO_DATE"),
        ] {
            let value = self.value(key)?;
            let date = strip(&value);
            if date.is_empty() {
                continue;
            }
            let chars = date.chars().collect::<Vec<_>>();
            if chars.len() != 10
                || chars[4] != '-'
                || chars[7] != '-'
                || !chars
                    .iter()
                    .filter(|c| **c != '-')
                    .all(|c| crate::python_digits::is_digit(*c))
                || !chars.iter().any(|c| *c != '-')
            {
                return Err(failure("FetchError"));
            }
            filters.push(format!("{name}:{date}"));
        }
        for (name, key) in [
            ("has_content.pdf", "OPENALEX_HAS_PDF"),
            ("has_abstract", "OPENALEX_HAS_ABSTRACT"),
        ] {
            let value = self.value(key)?;
            let value = strip(&value).to_lowercase();
            let boolean = match value.as_str() {
                "" => continue,
                "1" | "true" | "yes" | "on" => "true",
                "0" | "false" | "no" | "off" => "false",
                _ => return Err(failure("FetchError")),
            };
            filters.push(format!("{name}:{boolean}"));
        }
        if !filters.is_empty() {
            params.push(("filter", filters.join(",")));
        }
        Ok(params)
    }
    pub fn search_with_runner(
        &self,
        query: &str,
        limit: i64,
        transport: &mut dyn Transport,
        runner: &mut dyn ProcessRunner,
        context: &Context<'_>,
    ) -> ProviderResult<Vec<SearchResult>> {
        let requested = limit.max(0);
        if requested == 0 {
            return Ok(Vec::new());
        }
        let mut found = Vec::new();
        let mut cursor = "*".to_string();
        while (found.len() as i64) < requested {
            let request = Request {
                url: params_url(self.params(
                    query,
                    (requested - found.len() as i64).min(100),
                    &cursor,
                    runner,
                )?),
                headers: [("Accept".into(), "application/json".into())].into(),
            };
            let response = transport.get(&request)?;
            let payload: Value =
                serde_json::from_str(&response.text()).map_err(|_| failure("FetchError"))?;
            let payload = object(&payload)?;
            let missing = Value::Array(Vec::new());
            let items = payload.get("results").unwrap_or(&missing);
            if !truthy(items) {
                break;
            }
            let items = match items {
                Value::Array(items) => items,
                Value::String(_) | Value::Object(_) => return Err(failure("AttributeError")),
                _ => return Err(failure("TypeError")),
            };
            for item in items {
                if found.len() as i64 >= requested {
                    break;
                }
                found.push(result(item, found.len() + 1)?);
            }
            cursor = match payload.get("meta") {
                Some(Value::Object(meta)) => get(meta, "next_cursor")
                    .map(scalar)
                    .transpose()?
                    .unwrap_or_default(),
                _ => String::new(),
            };
            if cursor.is_empty() {
                break;
            }
        }
        crate::search::rank_with_validation(
            query,
            found,
            context.registry,
            context.year,
            |result| {
                if let Some(date) = &result.published_at {
                    let year = date.chars().take(4).collect::<String>();
                    if year.chars().count() == 4
                        && year.chars().all(crate::python_digits::is_digit)
                        && crate::python_digits::decimal_int(&year).is_none()
                    {
                        return Err(failure("ValueError"));
                    }
                }
                Ok(())
            },
        )
    }
}
impl SearchProvider for OpenAlex {
    fn name(&self) -> &'static str {
        "openalex"
    }
    fn search(
        &self,
        query: &str,
        limit: i64,
        transport: &mut dyn Transport,
        context: &Context<'_>,
    ) -> ProviderResult<Vec<SearchResult>> {
        self.search_with_runner(query, limit, transport, &mut NativeRunner, context)
    }
}

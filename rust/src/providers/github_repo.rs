//! Native GitHub repository gh-to-REST fallback. No Python runtime.
use super::{Context, ProviderError, ProviderResult, Request, SearchProvider, Transport};
use crate::{
    process::{NativeRunner, OUTPUT_LIMIT, ProcessRequest, ProcessRunner},
    search::SearchResult,
};
use serde_json::{Map, Value};
use std::collections::BTreeMap;
pub struct GitHubRepo {
    token: Option<String>,
}
fn failure(kind: &'static str) -> ProviderError {
    ProviderError::synthetic(kind)
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
fn object(v: &Value) -> ProviderResult<&Map<String, Value>> {
    v.as_object().ok_or_else(|| failure("AttributeError"))
}
fn get<'a>(m: &'a Map<String, Value>, k: &str) -> Option<&'a Value> {
    m.get(k).filter(|v| truthy(v))
}
fn text(v: Option<&Value>) -> ProviderResult<String> {
    match v {
        None | Some(Value::Null) => Ok(String::new()),
        Some(Value::String(v)) => Ok(v.clone()),
        _ => Err(failure("TypeError")),
    }
}
fn scalar(v: &Value) -> ProviderResult<String> {
    match v {
        Value::Bool(true) => Ok("True".into()),
        Value::Bool(false) => Ok("False".into()),
        Value::Number(v) => Ok(v.to_string()),
        Value::String(v) => Ok(v.clone()),
        Value::Null => Ok("None".into()),
        _ => Err(failure("TypeError")),
    }
}
fn strip(v: &str) -> &str {
    v.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
}
fn topics(v: Option<&Value>) -> ProviderResult<Vec<Value>> {
    match v {
        None => Ok(Vec::new()),
        Some(Value::Array(v)) => Ok(v.clone()),
        Some(Value::String(v)) => Ok(v.chars().map(|c| Value::String(c.to_string())).collect()),
        _ => Err(failure("TypeError")),
    }
}
fn license(m: &Map<String, Value>) -> ProviderResult<(String, String)> {
    let Some(Value::Object(v)) = m.get("license") else {
        return Ok((String::new(), String::new()));
    };
    let name = get(v, "name")
        .or_else(|| get(v, "spdx_id"))
        .map(scalar)
        .transpose()?
        .unwrap_or_default();
    let id = get(v, "spdx_id")
        .map(scalar)
        .transpose()?
        .unwrap_or_default();
    let id = strip(&id);
    let url = if id.is_empty() || id.to_uppercase() == "NOASSERTION" {
        String::new()
    } else {
        format!("https://spdx.org/licenses/{id}.html")
    };
    Ok((strip(&name).into(), url))
}
fn normalize(item: &Map<String, Value>, rest: bool) -> ProviderResult<Map<String, Value>> {
    if !rest {
        return Ok(item.clone());
    }
    let mut out = Map::new();
    for (to, from) in [
        ("name", "name"),
        ("description", "description"),
        ("stargazersCount", "stargazers_count"),
        ("updatedAt", "updated_at"),
        ("isFork", "fork"),
        ("language", "language"),
        ("topics", "topics"),
        ("license", "license"),
        ("homepage", "homepage"),
        ("cloneUrl", "clone_url"),
    ] {
        out.insert(to.into(), item.get(from).cloned().unwrap_or(Value::Null));
    }
    if let Some(owner) = get(item, "owner") {
        out.insert(
            "ownerLogin".into(),
            object(owner)?.get("login").cloned().unwrap_or(Value::Null),
        );
    }
    Ok(out)
}
fn result(item: &Value, index: usize, rest: bool) -> ProviderResult<Option<SearchResult>> {
    let item = object(item)?;
    let url_key = if rest { "html_url" } else { "url" };
    if !rest && get(item, url_key).is_none() {
        return Ok(None);
    }
    let title_key = if rest { "full_name" } else { "fullName" };
    let title = text(get(item, title_key).or_else(|| get(item, url_key)))?;
    let url = text(get(item, url_key))?;
    let published_at = match item.get(if rest { "updated_at" } else { "updatedAt" }) {
        None | Some(Value::Null) => None,
        Some(Value::String(s)) => Some(s.clone()),
        _ => return Err(failure("TypeError")),
    };
    let m = normalize(item, rest)?;
    let mut parts = Vec::new();
    if let Some(v) = get(&m, "language") {
        parts.push(format!("language={}", scalar(v)?));
    }
    if let Some(v) = get(&m, "description") {
        parts.push(scalar(v)?);
    }
    if let Some(v) = m.get("stargazersCount").filter(|v| !v.is_null()) {
        parts.push(format!("stars={}", scalar(v)?));
    }
    if let Some(v) = get(&m, "updatedAt") {
        parts.push(format!("updated={}", scalar(v)?));
    }
    let (name, license_url) = license(&m)?;
    if !name.is_empty() {
        parts.push(format!("license={name}"));
    }
    let topics = topics(get(&m, "topics"))?;
    if !topics.is_empty() {
        parts.push(format!(
            "topics={}",
            topics
                .iter()
                .take(6)
                .map(scalar)
                .collect::<ProviderResult<Vec<_>>>()?
                .join(",")
        ));
    }
    if get(&m, "isFork").is_some() {
        parts.push("fork=true".into());
    }
    let mut metadata = BTreeMap::new();
    for (to, from) in [
        ("package_name", "name"),
        ("maintainer", "ownerLogin"),
        ("language", "language"),
        ("homepage", "homepage"),
        ("source_code_url", "cloneUrl"),
    ] {
        if let Some(v) = get(&m, from) {
            metadata.insert(to.into(), v.clone());
        }
    }
    if let Some(v) = m.get("stargazersCount").filter(|v| !v.is_null()) {
        metadata.insert("stars".into(), v.clone());
    }
    if !topics.is_empty() {
        metadata.insert("topics".into(), Value::Array(topics));
    }
    if !name.is_empty() {
        metadata.insert("license_name".into(), Value::String(name));
    }
    if !license_url.is_empty() {
        metadata.insert("license_url".into(), Value::String(license_url));
    }
    Ok(Some(SearchResult {
        title,
        url,
        snippet: parts.join(" | "),
        source: "github".into(),
        published_at,
        rank: index as i64,
        score: 0.0,
        metadata,
    }))
}
fn entries(v: &Value) -> ProviderResult<&[Value]> {
    match v {
        Value::Array(v) => Ok(v),
        Value::Object(v) if v.is_empty() => Ok(&[]),
        Value::String(v) if v.is_empty() => Ok(&[]),
        Value::Object(_) | Value::String(_) => Err(failure("AttributeError")),
        _ => Err(failure("TypeError")),
    }
}
fn ranked(
    query: &str,
    results: Vec<SearchResult>,
    context: &Context<'_>,
) -> ProviderResult<Vec<SearchResult>> {
    crate::search::rank_with_validation(query, results, context.registry, context.year, |r| {
        if let Some(date) = &r.published_at {
            let year = date.chars().take(4).collect::<String>();
            if year.chars().count() == 4
                && year.chars().all(crate::python_digits::is_digit)
                && crate::python_digits::decimal_int(&year).is_none()
            {
                return Err(failure("ValueError"));
            }
        }
        Ok(())
    })
}
impl GitHubRepo {
    pub fn from_env() -> Self {
        Self { token: None }
    }
    pub fn with_token(token: String) -> Self {
        Self { token: Some(token) }
    }
    pub fn search_with_runner(
        &self,
        query: &str,
        limit: i64,
        transport: &mut dyn Transport,
        runner: &mut dyn ProcessRunner,
        context: &Context<'_>,
    ) -> ProviderResult<Vec<SearchResult>> {
        if runner.available("gh")? {
            let request = ProcessRequest {
                program: "gh".into(),
                args: vec![
                    "search".into(),
                    "repos".into(),
                    query.into(),
                    "--limit".into(),
                    limit.to_string(),
                    "--json".into(),
                    "fullName,description,url,stargazersCount,updatedAt,isFork".into(),
                ],
                timeout_ms: 30_000,
                output_limit: OUTPUT_LIMIT,
            };
            let output = match runner.run(&request) {
                Ok(output) => Some(output),
                Err(e) if e.kind == "TimeoutExpired" => None,
                Err(e) => return Err(e),
            };
            if let Some(output) = output {
                // Python text=True decodes both streams, including failed processes.
                let text = std::str::from_utf8(&output.stdout)
                    .map_err(|_| failure("UnicodeDecodeError"))?;
                std::str::from_utf8(&output.stderr).map_err(|_| failure("UnicodeDecodeError"))?;
                if output.return_code == 0 {
                    let payload: Value =
                        serde_json::from_str(if text.is_empty() { "[]" } else { text })
                            .map_err(|_| failure("JSONDecodeError"))?;
                    let found = entries(&payload)?
                        .iter()
                        .enumerate()
                        .map(|(i, item)| result(item, i + 1, false))
                        .collect::<ProviderResult<Vec<_>>>()?
                        .into_iter()
                        .flatten()
                        .collect::<Vec<_>>();
                    if !found.is_empty() {
                        return ranked(query, found, context);
                    }
                }
            }
        }
        let token = match &self.token {
            Some(v) => v.clone(),
            None => match std::env::var("GITHUB_TOKEN") {
                Ok(v) => v,
                Err(std::env::VarError::NotPresent) => String::new(),
                Err(_) => return Err(failure("FetchError")),
            },
        };
        let mut headers: BTreeMap<String, String> = [
            ("Accept".into(), "application/vnd.github+json".into()),
            ("X-GitHub-Api-Version".into(), "2022-11-28".into()),
        ]
        .into();
        if !token.is_empty() {
            headers.insert("Authorization".into(), format!("Bearer {token}"));
        }
        let mut form = url::form_urlencoded::Serializer::new(String::new());
        form.extend_pairs([
            ("q", query.to_string()),
            ("sort", "stars".into()),
            ("order", "desc".into()),
            ("per_page", limit.min(30).to_string()),
        ]);
        let request = Request {
            url: format!(
                "https://api.github.com/search/repositories?{}",
                form.finish().replace('*', "%2A").replace("%7E", "~")
            ),
            headers,
        };
        let response = transport.get(&request)?;
        let payload: Value =
            serde_json::from_str(&response.text()).map_err(|_| failure("FetchError"))?;
        let payload = object(&payload)?;
        let missing = Value::Array(Vec::new());
        let found = entries(payload.get("items").unwrap_or(&missing))?
            .iter()
            .enumerate()
            .map(|(i, item)| result(item, i + 1, true))
            .collect::<ProviderResult<Vec<_>>>()?
            .into_iter()
            .flatten()
            .collect();
        ranked(query, found, context)
    }
}
impl SearchProvider for GitHubRepo {
    fn name(&self) -> &'static str {
        "github"
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

//! Native HTTP GET transport. See the migration ledger for remaining boundaries.
use reqwest::{blocking::Client, redirect::Policy};
use std::{
    collections::BTreeMap,
    fmt,
    io::Read,
    time::{Duration, Instant},
};

pub const USER_AGENT: &str = "katala-web-research/0.1 (+local research tool)";
pub const DEFAULT_TIMEOUT: f64 = 20.0;
pub const MAX_RESPONSE_BYTES: usize = 8 * 1024 * 1024;
pub const MAX_REDIRECTS: usize = 10;
pub const FEED_ACCEPT: &str = "application/rss+xml, application/atom+xml, application/feed+json, application/json, text/xml, */*";

#[derive(Debug)]
pub struct HttpError {
    pub kind: &'static str,
    message: String,
}
impl fmt::Display for HttpError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for HttpError {}
fn error(kind: &'static str, message: impl Into<String>) -> HttpError {
    HttpError {
        kind,
        message: message.into(),
    }
}

#[derive(Debug, Default, Clone)]
pub struct Proxies {
    pub http: Option<String>,
    pub https: Option<String>,
    pub no_proxy: Option<String>,
}
impl Proxies {
    pub fn from_values(values: &BTreeMap<String, String>) -> Self {
        let mut chosen = BTreeMap::new();
        for (key, value) in values {
            if let Some(scheme) = key.to_lowercase().strip_suffix("_proxy")
                && !value.is_empty()
            {
                chosen.insert(scheme.to_string(), value.clone());
            }
        }
        if values.contains_key("REQUEST_METHOD") {
            chosen.remove("http");
        }
        for (key, value) in values {
            if let Some(scheme) = key.strip_suffix("_proxy") {
                if value.is_empty() {
                    chosen.remove(&scheme.to_lowercase());
                } else {
                    chosen.insert(scheme.to_lowercase(), value.clone());
                }
            }
        }
        Self {
            http: chosen.remove("http"),
            https: chosen.remove("https"),
            no_proxy: chosen.remove("no"),
        }
    }
    pub fn bypass(&self, host: &str, port: Option<u16>) -> bool {
        let Some(no_proxy) = &self.no_proxy else {
            return false;
        };
        if no_proxy == "*" {
            return true;
        }
        let host = host.to_lowercase();
        let authority = port.map_or_else(|| host.clone(), |p| format!("{host}:{p}"));
        no_proxy
            .split(',')
            .map(|s| s.trim().trim_start_matches('.').to_lowercase())
            .filter(|s| !s.is_empty())
            .any(|name| {
                host == name
                    || authority == name
                    || host.ends_with(&format!(".{name}"))
                    || authority.ends_with(&format!(".{name}"))
            })
    }
    fn selected(&self, url: &url::Url, raw: &str) -> Option<&str> {
        let literal_port = crate::urls::parse(raw)
            .authority
            .rsplit_once(':')
            .and_then(|(_, p)| p.parse().ok());
        if self.bypass(url.host_str().unwrap_or(""), literal_port.or(url.port())) {
            return None;
        }
        match url.scheme() {
            "http" => self.http.as_deref(),
            "https" => self.https.as_deref(),
            _ => None,
        }
    }
}

#[derive(Clone)]
pub struct Settings {
    pub timeout: Duration,
    pub proxies: Proxies,
    pub body_limit: Option<usize>,
    pub root_certificates: Vec<reqwest::Certificate>,
}
impl Default for Settings {
    fn default() -> Self {
        Self {
            timeout: Duration::from_secs(20),
            proxies: Proxies::default(),
            body_limit: Some(MAX_RESPONSE_BYTES),
            root_certificates: Vec::new(),
        }
    }
}
impl Settings {
    pub fn from_env() -> Result<Self, HttpError> {
        let raw = match std::env::var("KWR_HTTP_TIMEOUT_SECONDS") {
            Ok(value) => value,
            Err(std::env::VarError::NotPresent) => String::new(),
            Err(_) => {
                return Err(error(
                    "FetchError",
                    "HTTP timeout environment must be UTF-8",
                ));
            }
        };
        let timeout = resolve_timeout(&raw)?;
        let mut values = BTreeMap::new();
        for (key, value) in std::env::vars_os() {
            let Some(key) = key.to_str() else {
                continue;
            };
            if key.to_lowercase().ends_with("_proxy") || key == "REQUEST_METHOD" {
                let value = value
                    .to_str()
                    .ok_or_else(|| error("FetchError", "proxy environment must be UTF-8"))?;
                values.insert(key.to_string(), value.to_string());
            }
        }
        Ok(Self {
            timeout,
            proxies: Proxies::from_values(&values),
            ..Self::default()
        })
    }
}
pub fn resolve_timeout(raw: &str) -> Result<Duration, HttpError> {
    if raw.trim().is_empty() {
        return Ok(Duration::from_secs_f64(DEFAULT_TIMEOUT));
    }
    let value = raw.trim().parse::<f64>().map_err(|_| {
        error(
            "FetchError",
            "KWR_HTTP_TIMEOUT_SECONDS must be a number greater than 0",
        )
    })?;
    if !value.is_finite() || value <= 0.0 {
        return Err(error(
            "FetchError",
            "KWR_HTTP_TIMEOUT_SECONDS must be a finite number greater than 0",
        ));
    }
    let duration = Duration::try_from_secs_f64(value)
        .map_err(|_| error("FetchError", "HTTP timeout is out of range"))?;
    if duration.is_zero() {
        return Err(error(
            "FetchError",
            "HTTP timeout is below clock resolution",
        ));
    }
    Ok(duration)
}

pub struct HttpResponse {
    pub url: String,
    pub status: u16,
    pub headers: BTreeMap<String, String>,
    pub body: Vec<u8>,
}
impl HttpResponse {
    pub fn text(&self) -> String {
        let content_type = self
            .headers
            .get("content-type")
            .map(String::as_str)
            .unwrap_or("");
        let charset = content_type
            .split_once("charset=")
            .map(|(_, rest)| rest.split(';').next().unwrap_or("").trim())
            .filter(|s| !s.is_empty())
            .unwrap_or("utf-8");
        decode(&self.body, charset)
    }
}
pub fn decode(bytes: &[u8], charset: &str) -> String {
    let alias = charset.to_lowercase().replace(['-', '_', ' '], "");
    if alias == "utf8sig" {
        return String::from_utf8_lossy(bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(bytes))
            .into_owned();
    }
    if ["utf8", "utf", "u8"].contains(&alias.as_str()) {
        return String::from_utf8_lossy(bytes).into_owned();
    }
    if [
        "latin1", "latin", "l1", "iso88591", "isoir100", "cp819", "ibm819",
    ]
    .contains(&alias.as_str())
    {
        return bytes.iter().map(|b| char::from(*b)).collect();
    }
    if ["ascii", "usascii", "646"].contains(&alias.as_str()) {
        return bytes
            .iter()
            .map(|b| if b.is_ascii() { char::from(*b) } else { '�' })
            .collect();
    }
    if alias == "utf16le" {
        return encoding_rs::UTF_16LE
            .decode_without_bom_handling(bytes)
            .0
            .into_owned();
    }
    if alias == "utf16be" {
        return encoding_rs::UTF_16BE
            .decode_without_bom_handling(bytes)
            .0
            .into_owned();
    }
    if alias == "utf16" {
        return encoding_rs::UTF_16LE.decode(bytes).0.into_owned();
    }
    match encoding_rs::Encoding::for_label(charset.as_bytes()) {
        Some(encoding) => {
            if encoding == encoding_rs::WINDOWS_1252 {
                return encoding
                    .decode_without_bom_handling(bytes)
                    .0
                    .chars()
                    .map(|c| {
                        if ['\u{81}', '\u{8d}', '\u{8f}', '\u{90}', '\u{9d}'].contains(&c) {
                            '�'
                        } else {
                            c
                        }
                    })
                    .collect();
            }
            if alias == "utf16" {
                encoding.decode(bytes).0.into_owned()
            } else {
                encoding.decode_without_bom_handling(bytes).0.into_owned()
            }
        }
        None => String::from_utf8_lossy(bytes).into_owned(),
    }
}
pub fn redact_url(raw: &str) -> String {
    let mut parts = crate::urls::parse(raw);
    if let Some((_, host)) = parts.authority.rsplit_once('@') {
        parts.authority = format!("REDACTED@{host}");
    }
    let pairs = url::form_urlencoded::parse(parts.query.as_bytes())
        .map(|(k, v)| {
            let secret = [
                "access_token",
                "api_key",
                "apikey",
                "auth",
                "key",
                "subscription_token",
                "token",
            ]
            .contains(&k.to_lowercase().as_str());
            (
                k.into_owned(),
                if secret {
                    "REDACTED".into()
                } else {
                    v.into_owned()
                },
            )
        })
        .collect::<Vec<_>>();
    let mut encoded = url::form_urlencoded::Serializer::new(String::new());
    encoded.extend_pairs(pairs);
    parts.query = encoded.finish().replace('*', "%2A").replace("%7E", "~");
    // Fragments never reach HTTP, and may themselves contain credentials.
    parts.fragment.clear();
    parts.serialize()
}
fn diagnostic(url: &str, detail: &str) -> String {
    format!("fetch failed for {}: {detail}", redact_url(url))
}

pub fn fetch_url(
    url: &str,
    headers: &[(&str, &str)],
    settings: &Settings,
) -> Result<HttpResponse, HttpError> {
    let mut current = url.to_string();
    let started = Instant::now();
    let mut forwarded_headers = headers.to_vec();
    let mut visited = BTreeMap::<String, usize>::new();
    for hop in 0..=MAX_REDIRECTS {
        let parsed =
            url::Url::parse(&current).map_err(|_| error("FetchError", "invalid HTTP URL"))?;
        if !["http", "https"].contains(&parsed.scheme()) {
            return Err(error(
                "FetchError",
                "HTTP transport supports http/https only",
            ));
        }
        if !parsed.username().is_empty() || parsed.password().is_some() {
            return Err(error(
                "FetchError",
                diagnostic(url, "URL userinfo is unsupported"),
            ));
        }
        let remaining = settings
            .timeout
            .checked_sub(started.elapsed())
            .filter(|d| !d.is_zero())
            .ok_or_else(|| error("TimeoutError", diagnostic(url, "total deadline exceeded")))?;
        let mut builder = Client::builder()
            .no_proxy()
            .redirect(Policy::none())
            .timeout(remaining)
            .connect_timeout(remaining)
            .user_agent(USER_AGENT);
        if let Some(proxy) = settings.proxies.selected(&parsed, &current) {
            let proxy = reqwest::Proxy::all(proxy)
                .map_err(|_| error("FetchError", "invalid configured HTTP proxy"))?;
            builder = builder.proxy(proxy);
        }
        for cert in &settings.root_certificates {
            builder = builder.add_root_certificate(cert.clone());
        }
        let client = builder
            .build()
            .map_err(|_| error("FetchError", "HTTP client initialization failed"))?;
        let mut request = client
            .get(&current)
            .header("Accept-Encoding", "identity")
            .header("Connection", "close");
        for (key, value) in &forwarded_headers {
            request = request.header(*key, *value);
        }
        let remaining = settings
            .timeout
            .checked_sub(started.elapsed())
            .filter(|d| !d.is_zero())
            .ok_or_else(|| error("TimeoutError", diagnostic(url, "total deadline exceeded")))?;
        // Request-level timeout also travels into reqwest's asynchronous body
        // reader, so small chunks cannot reset the total deadline.
        request = request.timeout(remaining);
        let mut response = request.send().map_err(|e| {
            error(
                if e.is_timeout() && !e.is_connect() {
                    "TimeoutError"
                } else {
                    "FetchError"
                },
                diagnostic(
                    url,
                    if e.is_timeout() {
                        "timeout"
                    } else {
                        "transport or TLS failure"
                    },
                ),
            )
        })?;
        let status = response.status().as_u16();
        if [301, 302, 303, 307, 308].contains(&status)
            && let Some(location) = response
                .headers()
                .get("location")
                .or_else(|| response.headers().get("uri"))
        {
            let location = location
                .to_str()
                .map_err(|_| error("FetchError", diagnostic(url, "invalid redirect")))?;
            let next = crate::urls::join(&current, location);
            let next_parsed = url::Url::parse(&next)
                .map_err(|_| error("FetchError", diagnostic(url, "invalid redirect")))?;
            if parsed.scheme() == "https" && next_parsed.scheme() == "http" {
                return Err(error(
                    "FetchError",
                    diagnostic(url, "HTTPS downgrade rejected"),
                ));
            }
            if parsed.origin() != next_parsed.origin() {
                forwarded_headers.retain(|(key, _)| {
                    !["authorization", "cookie", "proxy-authorization"]
                        .contains(&key.to_ascii_lowercase().as_str())
                });
            }
            let distinct = visited.len();
            let count = visited.entry(next.clone()).or_default();
            if hop >= MAX_REDIRECTS || distinct >= 10 || *count >= 4 {
                return Err(error(
                    "FetchError",
                    diagnostic(url, "redirect limit exceeded"),
                ));
            }
            *count += 1;
            current = next;
            continue;
        }
        if !(200..300).contains(&status) {
            return Err(error(
                "FetchError",
                format!("HTTP {status} for {}", redact_url(url)),
            ));
        }
        let headers = response
            .headers()
            .iter()
            .filter_map(|(k, v)| {
                v.to_str()
                    .ok()
                    .map(|v| (k.as_str().to_lowercase(), v.to_string()))
            })
            .collect();
        if settings
            .body_limit
            .is_some_and(|limit| response.content_length().is_some_and(|n| n > limit as u64))
        {
            return Err(error(
                "FetchError",
                diagnostic(url, "response body exceeds limit"),
            ));
        }
        let mut body = Vec::new();
        let read = match settings.body_limit {
            Some(limit) => response
                .by_ref()
                .take((limit as u64).saturating_add(1))
                .read_to_end(&mut body),
            None => response.read_to_end(&mut body),
        };
        read.map_err(|e| {
            let timeout = e.kind() == std::io::ErrorKind::TimedOut
                || e.get_ref()
                    .and_then(|e| e.downcast_ref::<reqwest::Error>())
                    .is_some_and(reqwest::Error::is_timeout);
            error(
                if timeout {
                    "TimeoutError"
                } else {
                    "IncompleteRead"
                },
                diagnostic(
                    url,
                    if timeout {
                        "body timeout"
                    } else {
                        "incomplete response body"
                    },
                ),
            )
        })?;
        if settings.body_limit.is_some_and(|limit| body.len() > limit) {
            return Err(error(
                "FetchError",
                diagnostic(url, "response body exceeds limit"),
            ));
        }
        return Ok(HttpResponse {
            url: current,
            status,
            headers,
            body,
        });
    }
    Err(error(
        "FetchError",
        diagnostic(url, "redirect limit exceeded"),
    ))
}

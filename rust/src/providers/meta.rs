//! Meta profile, health and reciprocal-rank fusion contracts.
//! Native fan-out and ledger integration are gated separately before CLI enablement.
use super::{Context, ProviderError, ProviderResult};
use crate::search::SearchResult;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

fn strip(value: &str) -> &str {
    value.trim_matches(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
}
pub fn profile(value: &str) -> String {
    let value = strip(value).to_lowercase();
    if [
        "broad",
        "docs",
        "scholarly",
        "code",
        "fresh",
        "local",
        "monitoring",
    ]
    .contains(&value.as_str())
    {
        value
    } else {
        "broad".into()
    }
}
pub fn provider_names(profile: &str, explicit: &str) -> Vec<String> {
    let explicit = strip(explicit);
    let names: Vec<&str> = if !explicit.is_empty() {
        explicit.split(',').map(strip).collect()
    } else {
        match profile {
            "docs" => vec!["ddg", "searxng", "github", "jina"],
            "scholarly" => vec!["openalex", "searxng", "ddg"],
            "code" => vec!["github_code", "github", "searxng", "ddg"],
            "fresh" => vec!["ddg", "searxng", "brave"],
            "local" | "monitoring" => vec!["feed", "ddg", "github"],
            _ => vec!["ddg", "github", "openalex", "searxng"],
        }
    };
    names
        .into_iter()
        .filter(|name| {
            [
                "brave",
                "ddg",
                "feed",
                "github",
                "github_code",
                "openalex",
                "jina",
                "searxng",
            ]
            .contains(name)
        })
        .map(str::to_string)
        .collect()
}
pub fn rewrite_query(query: &str, provider: &str, profile: &str) -> String {
    let suffix = match (provider, profile) {
        ("openalex", "scholarly") => " paper benchmark evaluation",
        ("openalex", "broad") => " scholarly research",
        ("github", "code") => " implementation library",
        ("ddg" | "searxng", "docs") => " official documentation",
        ("ddg" | "searxng" | "brave", "fresh") => " latest",
        _ => "",
    };
    format!("{query}{suffix}")
}
// Formatting rounds the original binary float (multiplication can manufacture ties).
fn round(value: f64, places: usize) -> f64 {
    format!("{value:.places$}").parse().unwrap()
}
pub fn health_score(status: &str, result_count: usize, latency_ms: i64, requested: i64) -> f64 {
    match status {
        "error" => 0.0,
        "empty" => 0.35,
        _ => {
            let ratio = (result_count as f64 / requested.max(1) as f64).min(1.0);
            let penalty = if latency_ms >= 5000 {
                0.25
            } else if latency_ms >= 2000 {
                0.15
            } else if latency_ms >= 1000 {
                0.05
            } else {
                0.0
            };
            round((0.75 + 0.25 * ratio - penalty).clamp(0.1, 1.0), 3)
        }
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineRun {
    pub provider: String,
    pub status: String,
    pub latency_ms: i64,
    pub result_count: usize,
    pub health_score: f64,
    pub error_kind: String,
}
pub fn annotate_engine(mut result: SearchResult, run: &EngineRun) -> SearchResult {
    result
        .metadata
        .insert("engine_health_score".into(), json!(run.health_score));
    result
        .metadata
        .insert("engine_latency_ms".into(), json!(run.latency_ms));
    result
        .metadata
        .insert("engine_result_count".into(), json!(run.result_count));
    result
}
pub fn annotate_meta(
    mut result: SearchResult,
    profile: &str,
    providers: &[String],
    runs: &[EngineRun],
) -> SearchResult {
    let mut runs = runs.to_vec();
    runs.sort_by(|a, b| a.provider.cmp(&b.provider));
    result
        .metadata
        .insert("meta_profile".into(), json!(profile));
    result
        .metadata
        .insert("meta_providers".into(), json!(providers));
    result
        .metadata
        .insert("meta_engine_runs".into(), json!(runs));
    result
}
fn health_value(value: Option<&Value>) -> f64 {
    let n = match value {
        Some(Value::Number(n)) => n.as_f64(),
        Some(Value::Bool(b)) => Some(f64::from(*b)),
        Some(Value::String(s)) => strip(s).parse::<f64>().ok(),
        _ => None,
    };
    // Python min(NaN, 1) / max(0, NaN) yield 0 for this argument order.
    let n = n.unwrap_or(1.0);
    if n.is_nan() { 0.0 } else { n.clamp(0.0, 1.0) }
}
fn key(value: &str) -> String {
    let parts = crate::urls::parse(value);
    if parts.authority.is_empty() {
        return String::new();
    }
    let path = parts.path_without_params().trim_end_matches('/');
    format!(
        "{}://{}{}",
        parts.scheme,
        parts.authority.to_lowercase(),
        if path.is_empty() { "/" } else { path }
    )
}
struct Fused {
    result: SearchResult,
    score: f64,
    ranks: BTreeMap<String, i64>,
    health: BTreeMap<String, f64>,
}
pub fn reciprocal_rank_fusion(
    lists: Vec<Vec<SearchResult>>,
    rrf_k: i64,
    engine_health: &BTreeMap<String, Value>,
) -> ProviderResult<Vec<SearchResult>> {
    // Preserve insertion/completion order for representative selection.
    let mut fused = Vec::<Fused>::new();
    let mut positions = BTreeMap::<String, usize>::new();
    for (engine, results) in lists.into_iter().enumerate() {
        for (fallback, result) in results.into_iter().enumerate() {
            let key = key(&result.url);
            if key.is_empty() {
                continue;
            }
            let source = if result.source.is_empty() {
                format!("engine_{}", engine + 1)
            } else {
                result.source.clone()
            };
            let rank = if result.rank == 0 {
                fallback as i64 + 1
            } else {
                result.rank
            };
            let denominator = rrf_k as i128 + rank as i128;
            if denominator == 0 {
                return Err(ProviderError::synthetic("ZeroDivisionError"));
            }
            let health = health_value(
                engine_health
                    .get(&source)
                    .or_else(|| result.metadata.get("engine_health_score")),
            );
            let index = *positions.entry(key).or_insert_with(|| {
                fused.push(Fused {
                    result: result.clone(),
                    score: 0.0,
                    ranks: BTreeMap::new(),
                    health: BTreeMap::new(),
                });
                fused.len() - 1
            });
            let current = &mut fused[index];
            current.score += health / denominator as f64;
            current
                .ranks
                .entry(source.clone())
                .and_modify(|r| *r = (*r).min(rank))
                .or_insert(rank);
            current
                .health
                .entry(source)
                .and_modify(|h| *h = (*h).max(health))
                .or_insert(health);
            if rank
                < if current.result.rank == 0 {
                    fallback as i64 + 1
                } else {
                    current.result.rank
                }
            {
                current.result = result;
            }
        }
    }
    let mut results = fused
        .into_iter()
        .map(|mut f| {
            f.result
                .metadata
                .insert("rrf_score".into(), json!(round(f.score, 6)));
            f.result
                .metadata
                .insert("engine_ranks".into(), json!(f.ranks));
            f.result
                .metadata
                .insert("engine_health".into(), json!(f.health));
            f.result
                .metadata
                .insert("source_count".into(), json!(f.ranks.len()));
            f.result
        })
        .collect::<Vec<_>>();
    results.sort_by(|a, b| {
        b.metadata["rrf_score"]
            .as_f64()
            .unwrap()
            .total_cmp(&a.metadata["rrf_score"].as_f64().unwrap())
            .then(a.rank.cmp(&b.rank))
            .then(a.url.cmp(&b.url))
    });
    for (i, result) in results.iter_mut().enumerate() {
        result.rank = i as i64 + 1;
    }
    Ok(results)
}
pub fn fuse_and_rank(
    query: &str,
    lists: Vec<Vec<SearchResult>>,
    limit: i64,
    rrf_k: i64,
    engine_health: &BTreeMap<String, Value>,
    context: &Context<'_>,
) -> ProviderResult<Vec<SearchResult>> {
    let results = reciprocal_rank_fusion(lists, rrf_k, engine_health)?;
    let ranked =
        crate::search::rank_with_validation(query, results, context.registry, context.year, |r| {
            if let Some(date) = &r.published_at {
                let year = date.chars().take(4).collect::<String>();
                if year.chars().count() == 4
                    && year.chars().all(crate::python_digits::is_digit)
                    && crate::python_digits::decimal_int(&year).is_none()
                {
                    return Err(ProviderError::synthetic("ValueError"));
                }
            }
            Ok(())
        })?;
    Ok(crate::search::slice(ranked, limit))
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EngineRequest {
    pub provider: String,
    pub query: String,
    pub limit: i64,
}
pub struct Completion {
    pub request: EngineRequest,
    pub latency_ms: i64,
    pub outcome: ProviderResult<Vec<SearchResult>>,
}
pub trait Executor {
    fn execute(
        &mut self,
        requests: &[EngineRequest],
        max_workers: usize,
    ) -> ProviderResult<Vec<Completion>>;
}
pub struct OfflineExecutor {
    expected: Vec<EngineRequest>,
    workers: usize,
    completions: Option<Vec<Completion>>,
    failed: bool,
    pub calls: usize,
}
impl OfflineExecutor {
    pub fn new(expected: Vec<EngineRequest>, workers: usize, completions: Vec<Completion>) -> Self {
        Self {
            expected,
            workers,
            completions: Some(completions),
            failed: false,
            calls: 0,
        }
    }
    pub fn finish(self) -> ProviderResult<()> {
        if self.failed || self.completions.is_some() {
            Err(ProviderError::synthetic("FixtureError"))
        } else {
            Ok(())
        }
    }
}
impl Executor for OfflineExecutor {
    fn execute(
        &mut self,
        requests: &[EngineRequest],
        max_workers: usize,
    ) -> ProviderResult<Vec<Completion>> {
        self.calls += 1;
        if requests != self.expected || max_workers != self.workers {
            self.failed = true;
            return Err(ProviderError::synthetic("FixtureError"));
        }
        let Some(completions) = self.completions.take() else {
            self.failed = true;
            return Err(ProviderError::synthetic("FixtureError"));
        };
        let mut remaining = requests.to_vec();
        for completion in &completions {
            let Some(index) = remaining.iter().position(|r| *r == completion.request) else {
                self.failed = true;
                return Err(ProviderError::synthetic("FixtureError"));
            };
            remaining.remove(index);
        }
        if !remaining.is_empty() {
            self.failed = true;
            return Err(ProviderError::synthetic("FixtureError"));
        }
        Ok(completions)
    }
}
pub trait Ledger {
    fn weak(&mut self) -> ProviderResult<Vec<String>>;
    fn record(&mut self, runs: &[EngineRun]) -> ProviderResult<()>;
}
pub struct NoLedger;
impl Ledger for NoLedger {
    fn weak(&mut self) -> ProviderResult<Vec<String>> {
        Ok(Vec::new())
    }
    fn record(&mut self, _: &[EngineRun]) -> ProviderResult<()> {
        Ok(())
    }
}
pub struct ArchiveLedger<'a> {
    pub path: &'a std::path::Path,
}
fn archive_error(e: Box<dyn std::error::Error>) -> ProviderError {
    let kind = if let Some(error) = e.downcast_ref::<rusqlite::Error>() {
        match error {
            rusqlite::Error::SqliteFailure(e, _)
                if e.code == rusqlite::ErrorCode::ConstraintViolation =>
            {
                "IntegrityError"
            }
            _ => "OperationalError",
        }
    } else if e.downcast_ref::<std::io::Error>().is_some() {
        "OSError"
    } else {
        // Version/content refusal is an explicit copy-migration policy.
        "ValueError"
    };
    ProviderError::synthetic(kind)
}
impl Ledger for ArchiveLedger<'_> {
    fn weak(&mut self) -> ProviderResult<Vec<String>> {
        let archive = crate::archive::Archive::open(self.path).map_err(archive_error)?;
        Ok(archive
            .engines(50)
            .map_err(archive_error)?
            .into_iter()
            .filter(|r| r["routed_around"] == true)
            .filter_map(|r| r["provider"].as_str().map(str::to_string))
            .collect())
    }
    fn record(&mut self, runs: &[EngineRun]) -> ProviderResult<()> {
        crate::archive::Archive::open(self.path)
            .map_err(archive_error)?
            .record_engine_runs(runs, 500)
            .map_err(archive_error)?;
        Ok(())
    }
}
pub fn search_with(
    query: &str,
    limit: i64,
    profile: &str,
    explicit: &str,
    executor: &mut dyn Executor,
    ledger: &mut dyn Ledger,
    context: &Context<'_>,
) -> ProviderResult<Vec<SearchResult>> {
    let mut names = provider_names(profile, explicit);
    if names.is_empty() {
        return Ok(Vec::new());
    }
    let weak = ledger.weak()?;
    let kept = names
        .iter()
        .filter(|n| !weak.contains(n))
        .cloned()
        .collect::<Vec<_>>();
    if !kept.is_empty() {
        names = kept;
    }
    let requests = names
        .iter()
        .map(|name| EngineRequest {
            provider: name.clone(),
            query: rewrite_query(query, name, profile),
            limit: limit.clamp(2, 8),
        })
        .collect::<Vec<_>>();
    let completions = executor.execute(&requests, requests.len().min(4))?;
    let mut lists = Vec::new();
    let mut runs = Vec::new();
    for completion in completions {
        let (results, error_kind) = match completion.outcome {
            Ok(results) => (results, String::new()),
            Err(e) => (Vec::new(), e.kind.into()),
        };
        let status = if !error_kind.is_empty() {
            "error"
        } else if results.is_empty() {
            "empty"
        } else {
            "ok"
        };
        let run = EngineRun {
            provider: completion.request.provider,
            status: status.into(),
            latency_ms: completion.latency_ms,
            result_count: results.len(),
            health_score: health_score(
                status,
                results.len(),
                completion.latency_ms,
                completion.request.limit,
            ),
            error_kind,
        };
        if !results.is_empty() {
            lists.push(
                results
                    .into_iter()
                    .map(|r| annotate_engine(r, &run))
                    .collect(),
            );
        }
        runs.push(run);
    }
    ledger.record(&runs)?;
    let health = runs
        .iter()
        .map(|r| (r.provider.clone(), json!(r.health_score)))
        .collect();
    Ok(fuse_and_rank(query, lists, limit, 60, &health, context)?
        .into_iter()
        .map(|r| annotate_meta(r, profile, &names, &runs))
        .collect())
}

pub trait EngineRunner: Sync {
    fn run(&self, request: &EngineRequest) -> ProviderResult<Vec<SearchResult>>;
}
pub struct NativeExecutor<'a> {
    pub runner: &'a dyn EngineRunner,
}
impl Executor for NativeExecutor<'_> {
    fn execute(
        &mut self,
        requests: &[EngineRequest],
        max_workers: usize,
    ) -> ProviderResult<Vec<Completion>> {
        self.execute_observed(requests, max_workers, &|_| {})
    }
}
impl NativeExecutor<'_> {
    // Scheduling observation is private and has no CLI/environment control.
    fn execute_observed(
        &mut self,
        requests: &[EngineRequest],
        max_workers: usize,
        after_send: &(dyn Fn(&EngineRequest) + Sync),
    ) -> ProviderResult<Vec<Completion>> {
        if requests.is_empty() {
            return Ok(Vec::new());
        }
        if !(1..=4).contains(&max_workers) {
            return Err(ProviderError::synthetic("ValueError"));
        }
        use std::sync::{
            atomic::{AtomicUsize, Ordering},
            mpsc,
        };
        let next = AtomicUsize::new(0);
        let (send, receive) = mpsc::channel();
        let runner = self.runner;
        std::thread::scope(|scope| {
            for _ in 0..max_workers.min(requests.len()) {
                let send = send.clone();
                let next = &next;
                scope.spawn(move || {
                    loop {
                        let index = next.fetch_add(1, Ordering::Relaxed);
                        let Some(request) = requests.get(index) else {
                            break;
                        };
                        let started = std::time::Instant::now();
                        let outcome = runner.run(request);
                        let latency_ms = format!("{:.0}", started.elapsed().as_secs_f64() * 1000.0)
                            .parse::<i64>()
                            .unwrap_or(i64::MAX);
                        if send
                            .send(Completion {
                                request: request.clone(),
                                latency_ms,
                                outcome,
                            })
                            .is_err()
                        {
                            break;
                        }
                        after_send(request);
                    }
                });
            }
            drop(send);
            Ok(receive.into_iter().collect())
        })
    }
}

pub struct NativeEngines<'a> {
    pub context: &'a Context<'a>,
    pub archive: &'a std::path::Path,
}
impl EngineRunner for NativeEngines<'_> {
    fn run(&self, request: &EngineRequest) -> ProviderResult<Vec<SearchResult>> {
        use super::SearchProvider;
        let mut transport = super::EnvTransport::default();
        let q = &request.query;
        let limit = request.limit;
        let ctx = self.context;
        match request.provider.as_str() {
            "ddg" => super::DuckDuckGo.search(q, limit, &mut transport, ctx),
            "github" => {
                super::github_repo::GitHubRepo::from_env().search(q, limit, &mut transport, ctx)
            }
            "github_code" => {
                super::github::GitHubCode::from_env()?.search(q, limit, &mut transport, ctx)
            }
            "openalex" => {
                super::openalex::OpenAlex::from_env().search(q, limit, &mut transport, ctx)
            }
            "feed" => {
                crate::search::feed(q, self.archive, limit, ctx.registry).map_err(archive_error)
            }
            name => {
                let kind = super::json::Kind::named(name)
                    .ok_or_else(|| ProviderError::synthetic("ValueError"))?;
                super::json::JsonSearch {
                    kind,
                    config: super::json::Config::from_env(kind)?,
                }
                .search(q, limit, &mut transport, ctx)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Condvar, Mutex};
    use std::time::Duration;
    #[test]
    fn native_completion_order_uses_channel_send_without_sleep_guess() {
        struct Runner {
            sent: Mutex<bool>,
            ready: Condvar,
        }
        impl EngineRunner for Runner {
            fn run(&self, request: &EngineRequest) -> ProviderResult<Vec<SearchResult>> {
                if request.provider == "first" {
                    let sent = self.sent.lock().unwrap();
                    let (_guard, timeout) = self
                        .ready
                        .wait_timeout_while(sent, Duration::from_secs(2), |sent| !*sent)
                        .unwrap();
                    assert!(
                        !timeout.timed_out(),
                        "second result must be sent before first is released"
                    );
                }
                Ok(Vec::new())
            }
        }
        let runner = Runner {
            sent: Mutex::new(false),
            ready: Condvar::new(),
        };
        let requests = ["first", "second"].map(|name| EngineRequest {
            provider: name.into(),
            query: "alpha".into(),
            limit: 2,
        });
        let after_send = |request: &EngineRequest| {
            if request.provider == "second" {
                *runner.sent.lock().unwrap() = true;
                runner.ready.notify_one();
            }
        };
        let completions = NativeExecutor { runner: &runner }
            .execute_observed(&requests, 2, &after_send)
            .unwrap();
        assert_eq!(
            completions
                .iter()
                .map(|c| c.request.provider.as_str())
                .collect::<Vec<_>>(),
            ["second", "first"]
        );
    }
}

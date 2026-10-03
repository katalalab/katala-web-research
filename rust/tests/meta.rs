use kwr::{
    providers::{Context, meta},
    registry::Registry,
    search::SearchResult,
};
use serde_json::{Value, json};
fn outcome(result: kwr::providers::ProviderResult<Vec<SearchResult>>) -> Value {
    match result {
        Ok(results) => json!({"results": results}),
        Err(e) => json!({"error_kind": e.kind}),
    }
}
#[test]
fn profiles_rewrites_health_fusion_and_annotations_match_python() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/meta-component-golden.json")).unwrap();
    let registry = Registry::load(None).unwrap();
    let context = Context {
        registry: &registry,
        year: 2026,
    };
    for case in fixture["profiles"].as_array().unwrap() {
        let profile = meta::profile(case["raw"].as_str().unwrap());
        assert_eq!(profile, case["profile"].as_str().unwrap());
        let names = meta::provider_names(&profile, case["explicit"].as_str().unwrap());
        assert_eq!(json!(names), case["names"]);
        for name in names {
            assert_eq!(
                meta::rewrite_query("alpha 日本語", &name, &profile),
                case["rewrites"][&name].as_str().unwrap()
            );
        }
    }
    for case in fixture["health"].as_array().unwrap() {
        assert_eq!(
            meta::health_score(
                case["status"].as_str().unwrap(),
                case["count"].as_u64().unwrap() as usize,
                case["latency"].as_i64().unwrap(),
                case["requested"].as_i64().unwrap()
            ),
            case["score"].as_f64().unwrap()
        );
    }
    for case in fixture["fusion"].as_array().unwrap() {
        let lists = serde_json::from_value(case["lists"].clone()).unwrap();
        let weights = serde_json::from_value(case["weights"].clone()).unwrap();
        let k = case["k"].as_i64().unwrap();
        assert_eq!(
            outcome(meta::reciprocal_rank_fusion(lists, k, &weights)),
            case["fused"],
            "{} fused",
            case["name"]
        );
        for row in case["ranked"].as_array().unwrap() {
            let lists = serde_json::from_value(case["lists"].clone()).unwrap();
            assert_eq!(
                outcome(meta::fuse_and_rank(
                    "alpha 日本語",
                    lists,
                    row["limit"].as_i64().unwrap(),
                    k,
                    &weights,
                    &context
                )),
                row["expected"],
                "{} limit={}",
                case["name"],
                row["limit"]
            );
        }
    }
    for case in fixture["annotations"].as_array().unwrap() {
        let result = serde_json::from_value(case["input"].clone()).unwrap();
        let run = serde_json::from_value(case["run"].clone()).unwrap();
        let runs = serde_json::from_value::<Vec<meta::EngineRun>>(case["runs"].clone()).unwrap();
        let result = meta::annotate_engine(result, &run);
        assert_eq!(json!(result), case["engine"]);
        assert_eq!(
            json!(meta::annotate_meta(
                result,
                "docs",
                &["ddg".into(), "brave".into(), "ddg".into()],
                &runs
            )),
            case["meta"]
        );
    }
}

#[test]
fn strict_completion_routing_partial_failure_and_ledger_oracles() {
    use kwr::providers::{ProviderError, ProviderResult};
    struct Ledger {
        weak: Vec<String>,
        route_error: Option<String>,
        record_error: Option<String>,
        calls: (usize, usize),
        recorded: Vec<meta::EngineRun>,
    }
    fn error(kind: &str) -> ProviderError {
        match kind {
            "OperationalError" => ProviderError::synthetic("OperationalError"),
            "TimeoutError" => ProviderError::synthetic("TimeoutError"),
            "ValueError" => ProviderError::synthetic("ValueError"),
            "FetchError" => ProviderError::synthetic("FetchError"),
            _ => panic!("unscripted fixture error"),
        }
    }
    impl meta::Ledger for Ledger {
        fn weak(&mut self) -> ProviderResult<Vec<String>> {
            self.calls.0 += 1;
            if let Some(e) = &self.route_error {
                Err(error(e))
            } else {
                Ok(self.weak.clone())
            }
        }
        fn record(&mut self, runs: &[meta::EngineRun]) -> ProviderResult<()> {
            self.calls.1 += 1;
            self.recorded = runs.to_vec();
            if let Some(e) = &self.record_error {
                Err(error(e))
            } else {
                Ok(())
            }
        }
    }
    let fixture: Value = serde_json::from_str(include_str!("fixtures/meta-golden.json")).unwrap();
    let registry = Registry::load(None).unwrap();
    let context = Context {
        registry: &registry,
        year: 2026,
    };
    for case in fixture["cases"].as_array().unwrap() {
        let requests: Vec<meta::EngineRequest> =
            serde_json::from_value(case["requests"].clone()).unwrap();
        let completions = case["completions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|c| meta::Completion {
                request: requests[c["request"].as_u64().unwrap() as usize].clone(),
                latency_ms: c["latency_ms"].as_i64().unwrap(),
                outcome: if let Some(e) = c["error_kind"].as_str() {
                    Err(error(e))
                } else {
                    Ok(serde_json::from_value(c["results"].clone()).unwrap())
                },
            })
            .collect();
        let mut executor = meta::OfflineExecutor::new(
            requests,
            case["workers"].as_u64().unwrap() as usize,
            completions,
        );
        let mut ledger = Ledger {
            weak: serde_json::from_value(case["weak"].clone()).unwrap(),
            route_error: case["route_error"].as_str().map(str::to_string),
            record_error: case["record_error"].as_str().map(str::to_string),
            calls: (0, 0),
            recorded: Vec::new(),
        };
        let profile = meta::profile(case["profile"].as_str().unwrap());
        let actual = outcome(meta::search_with(
            "alpha 日本語",
            case["limit"].as_i64().unwrap(),
            &profile,
            case["explicit"].as_str().unwrap(),
            &mut executor,
            &mut ledger,
            &context,
        ));
        assert_eq!(actual, case["expected"], "{}", case["name"]);
        let executed = case["workers"].as_u64().unwrap() > 0;
        assert_eq!(executor.calls, usize::from(executed));
        if executed {
            executor.finish().unwrap();
        }
        assert_eq!(
            ledger.calls,
            (
                case["weak_calls"].as_u64().unwrap() as usize,
                case["record_calls"].as_u64().unwrap() as usize
            ),
            "{}",
            case["name"]
        );
        assert_eq!(json!(ledger.recorded), case["recorded"], "{}", case["name"]);
    }
}

#[test]
fn native_executor_bounds_concurrency_and_drains_all_jobs_after_an_error() {
    use meta::{EngineRunner, Executor};
    use std::sync::{Condvar, Mutex, mpsc};
    use std::time::Duration;
    #[derive(Default)]
    struct State {
        active: usize,
        max: usize,
        started: usize,
        finished: usize,
        released: bool,
    }
    struct Runner {
        state: Mutex<State>,
        ready: Condvar,
    }
    impl EngineRunner for Runner {
        fn run(
            &self,
            r: &meta::EngineRequest,
        ) -> kwr::providers::ProviderResult<Vec<SearchResult>> {
            let mut s = self.state.lock().unwrap();
            s.active += 1;
            s.started += 1;
            s.max = s.max.max(s.active);
            self.ready.notify_all();
            while !s.released {
                s = self.ready.wait(s).unwrap();
            }
            s.active -= 1;
            s.finished += 1;
            if r.provider == "error" {
                Err(kwr::providers::ProviderError::synthetic("FetchError"))
            } else {
                Ok(Vec::new())
            }
        }
    }
    let runner = Runner {
        state: Mutex::new(State::default()),
        ready: Condvar::new(),
    };
    let requests = (0..8)
        .map(|i| meta::EngineRequest {
            provider: if i == 1 {
                "error".into()
            } else {
                format!("fixture{i}")
            },
            query: "alpha".into(),
            limit: 2,
        })
        .collect::<Vec<_>>();
    std::thread::scope(|scope| {
        let (send, receive) = mpsc::channel();
        let worker_runner = &runner;
        let worker_requests = &requests;
        scope.spawn(move || {
            send.send(
                meta::NativeExecutor {
                    runner: worker_runner,
                }
                .execute(worker_requests, 4),
            )
            .unwrap()
        });
        let s = runner.state.lock().unwrap();
        let (mut s, timed) = runner
            .ready
            .wait_timeout_while(s, Duration::from_secs(2), |s| s.started < 4)
            .unwrap();
        assert!(
            !timed.timed_out(),
            "four workers must reach the fixture gate"
        );
        assert_eq!(s.started, 4);
        assert_eq!(s.active, 4);
        assert_eq!(s.max, 4);
        s.released = true;
        runner.ready.notify_all();
        drop(s);
        let completions = receive
            .recv_timeout(Duration::from_secs(2))
            .unwrap()
            .unwrap();
        assert_eq!(completions.len(), 8);
        assert_eq!(completions.iter().filter(|c| c.outcome.is_err()).count(), 1);
        let mut actual = completions
            .iter()
            .map(|c| c.request.provider.clone())
            .collect::<Vec<_>>();
        actual.sort();
        let mut expected = requests
            .iter()
            .map(|r| r.provider.clone())
            .collect::<Vec<_>>();
        expected.sort();
        assert_eq!(actual, expected);
    });
    let s = runner.state.lock().unwrap();
    assert_eq!(s.finished, 8);
    assert_eq!(s.active, 0);
    assert_eq!(s.max, 4);
}

#[test]
fn offline_executor_rejects_unexpected_requests_and_completions() {
    use meta::Executor;
    let expected = meta::EngineRequest {
        provider: "ddg".into(),
        query: "alpha".into(),
        limit: 2,
    };
    let other = meta::EngineRequest {
        query: "beta".into(),
        ..expected.clone()
    };
    let mut executor = meta::OfflineExecutor::new(vec![expected.clone()], 1, Vec::new());
    match executor.execute(std::slice::from_ref(&other), 1) {
        Err(e) => assert_eq!(e.kind, "FixtureError"),
        Ok(_) => panic!("mismatched request unexpectedly accepted"),
    }
    assert_eq!(executor.finish().unwrap_err().kind, "FixtureError");
    let completion = meta::Completion {
        request: other,
        latency_ms: 0,
        outcome: Ok(Vec::new()),
    };
    let mut executor = meta::OfflineExecutor::new(vec![expected.clone()], 1, vec![completion]);
    assert!(executor.execute(&[expected], 1).is_err());
    assert!(executor.finish().is_err());
}

#[test]
fn archive_ledger_prunes_atomically_preserves_other_tables_and_routes_recent_history() {
    use kwr::archive::{Archive, query_json};
    use meta::Ledger;
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("synthetic.sqlite");
    let archive = Archive::open(&path).unwrap();
    archive.conn.execute_batch("INSERT INTO pages(url,title,content,source,fetched_at) VALUES ('https://fixture.test/page','alpha','alpha 日本語','fixture','fixed');
        INSERT INTO runs(query,provider,created_at) VALUES ('alpha','fixture','fixed');
        INSERT INTO search_results(run_id,rank,score,title,url,snippet,source) VALUES (1,1,1.0,'alpha','https://fixture.test/result','alpha','fixture');
        INSERT INTO repo_documents(repo_path,repo_name,rel_path,title,content,kind,indexed_at) VALUES ('/synthetic','fixture','item.rs','alpha','alpha','rust','fixed');
        INSERT INTO feed_sources(url,title,added_at) VALUES ('https://fixture.test/feed','alpha','fixed');
        INSERT INTO feed_items(source_url,url,title,summary,fetched_at) VALUES ('https://fixture.test/feed','https://fixture.test/item','alpha','alpha','fixed');
        INSERT INTO project_items(kind,repository,number,title,url,state,updated_at,labels_json,labels_text) VALUES ('issue','fixture/repo',1,'alpha','https://fixture.test/issue','open','fixed','[]','');").unwrap();
    fn preserved(a: &Archive) -> Vec<Value> {
        [
            "SELECT * FROM pages",
            "SELECT * FROM runs",
            "SELECT * FROM search_results",
            "SELECT * FROM repo_documents",
            "SELECT * FROM feed_sources",
            "SELECT * FROM feed_items",
            "SELECT * FROM project_items",
        ]
        .iter()
        .map(|q| {
            let rows = query_json(&a.conn, q, &[]).unwrap();
            assert!(!rows.is_empty());
            json!(rows)
        })
        .collect()
    }
    let before = preserved(&archive);
    let run = |provider: &str, index: i64, status: &str, count: usize| meta::EngineRun {
        provider: provider.into(),
        status: status.into(),
        latency_ms: index,
        result_count: count,
        health_score: 0.0,
        error_kind: if status == "error" {
            "FetchError".into()
        } else {
            String::new()
        },
    };
    let runs = (0..600)
        .flat_map(|i| [run("ddg", i, "error", 0), run("github", i, "ok", 2)])
        .collect::<Vec<_>>();
    assert_eq!(archive.record_engine_runs(&runs, 500).unwrap(), 1200);
    assert_eq!(preserved(&archive), before);
    let counts=query_json(&archive.conn,"SELECT provider,COUNT(*) AS n,MIN(latency_ms) AS oldest,COUNT(DISTINCT recorded_at) AS timestamps FROM engine_runs GROUP BY provider",&[]).unwrap();
    for row in counts {
        assert_eq!(row["n"], 500);
        assert_eq!(row["oldest"], 100);
        assert_eq!(row["timestamps"], 1);
    }
    assert_eq!(
        archive
            .conn
            .query_row("PRAGMA integrity_check", [], |r| r.get::<_, String>(0))
            .unwrap(),
        "ok"
    );
    assert_eq!(
        archive.query("pages", "alpha", 10, "", "").unwrap().len(),
        1
    );
    let mut ledger = meta::ArchiveLedger { path: &path };
    assert_eq!(ledger.weak().unwrap(), vec!["ddg"]);
    ledger
        .record(&(0..50).map(|i| run("ddg", i, "ok", 2)).collect::<Vec<_>>())
        .unwrap();
    assert!(ledger.weak().unwrap().is_empty());
    assert_eq!(preserved(&archive), before);
    // A TEMP trigger is a test-local fault, not a change to the archive schema.
    archive.conn.execute_batch("CREATE TEMP TRIGGER fail_run BEFORE INSERT ON engine_runs WHEN NEW.provider='reject' BEGIN SELECT RAISE(ABORT,'fixture failure'); END;").unwrap();
    let prior = query_json(&archive.conn, "SELECT * FROM engine_runs ORDER BY id", &[]).unwrap();
    assert!(
        archive
            .record_engine_runs(&[run("ddg", 1, "ok", 2), run("reject", 1, "error", 0)], 1)
            .is_err()
    );
    assert_eq!(
        query_json(&archive.conn, "SELECT * FROM engine_runs ORDER BY id", &[]).unwrap(),
        prior
    );
    assert_eq!(preserved(&archive), before);
    assert_eq!(archive.record_engine_runs(&[], 500).unwrap(), 0);
}

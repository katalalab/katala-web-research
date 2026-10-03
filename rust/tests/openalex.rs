use kwr::{
    http::HttpResponse,
    process::{OfflineRunner, ProcessOutput, ProcessRequest, ProcessStep},
    providers::{
        Context, OfflineTransport, ProviderError, Request, Step,
        openalex::{OpenAlex, work_id},
    },
    registry::Registry,
};
use serde_json::{Value, json};
use std::collections::BTreeMap;
fn bytes(v: &Value) -> Vec<u8> {
    if let Some(s) = v.as_str() {
        s.as_bytes().to_vec()
    } else {
        v.as_array()
            .unwrap()
            .iter()
            .map(|n| n.as_u64().unwrap() as u8)
            .collect()
    }
}
#[test]
fn openalex_search_abstract_auth_cursor_filter_and_error_oracles() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/openalex-golden.json")).unwrap();
    let registry = Registry::load(None).unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let process = case["process_steps"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| {
                if s["operation"] == "available" {
                    ProcessStep::Available {
                        program: s["program"].as_str().unwrap().into(),
                        found: s["found"].as_bool().unwrap(),
                    }
                } else {
                    ProcessStep::Run {
                        request: ProcessRequest {
                            program: s["request"]["program"].as_str().unwrap().into(),
                            args: serde_json::from_value(s["request"]["args"].clone()).unwrap(),
                            timeout_ms: s["request"]["timeout_ms"].as_u64().unwrap(),
                            output_limit: s["request"]["output_limit"].as_u64().unwrap() as usize,
                        },
                        outcome: match s["error_kind"].as_str() {
                            Some("TimeoutExpired") => {
                                Err(ProviderError::synthetic("TimeoutExpired"))
                            }
                            Some("FileNotFoundError") => {
                                Err(ProviderError::synthetic("FileNotFoundError"))
                            }
                            Some(_) => panic!("unknown fixture error"),
                            None => Ok(ProcessOutput {
                                return_code: s["return_code"].as_i64().unwrap() as i32,
                                stdout: bytes(&s["stdout"]),
                                stderr: bytes(&s["stderr"]),
                            }),
                        },
                    }
                }
            })
            .collect();
        let steps = case["steps"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| {
                let request = Request {
                    url: s["request"]["url"].as_str().unwrap().into(),
                    headers: serde_json::from_value(s["request"]["headers"].clone()).unwrap(),
                };
                let outcome = if let Some(status) = s["status"].as_u64() {
                    Err(ProviderError::synthetic_http_status(status as u16))
                } else if s["error_kind"] == "TimeoutError" {
                    Err(ProviderError::synthetic("TimeoutError"))
                } else {
                    Ok(HttpResponse {
                        url: request.url.clone(),
                        status: 200,
                        headers: BTreeMap::new(),
                        body: s["text"].as_str().unwrap().as_bytes().to_vec(),
                    })
                };
                Step { request, outcome }
            })
            .collect();
        let mut runner = OfflineRunner::new(process);
        let mut transport = OfflineTransport::new(steps);
        let values = serde_json::from_value(case["env"].clone()).unwrap();
        let actual = match OpenAlex::with_values(values).search_with_runner(
            case["query"].as_str().unwrap(),
            case["limit"].as_i64().unwrap(),
            &mut transport,
            &mut runner,
            &Context {
                registry: &registry,
                year: 2026,
            },
        ) {
            Ok(results) => json!({"results":results}),
            Err(e) => {
                assert!(!e.to_string().contains("public-fixture-key"));
                assert!(!e.to_string().contains("op://"));
                json!({"error_kind":e.kind})
            }
        };
        assert_eq!(actual, case["expected"], "{}", case["name"]);
        assert_eq!(transport.calls, case["steps"].as_array().unwrap().len());
        assert_eq!(
            runner.calls,
            case["process_steps"].as_array().unwrap().len()
        );
        runner.finish().unwrap();
        transport.finish().unwrap();
    }
    for case in fixture["identifiers"].as_array().unwrap() {
        let actual = match work_id(case["seed"].as_str().unwrap()) {
            Ok(id) => json!({"id":id}),
            Err(e) => json!({"error_kind":e.kind}),
        };
        assert_eq!(actual, case["expected"]);
    }
}

use kwr::{
    http::HttpResponse,
    providers::{
        Context, OfflineTransport, ProviderError, Request, SearchProvider, Step,
        json::{Config, JsonSearch, Kind},
    },
    registry::Registry,
};
use serde_json::{Value, json};
#[test]
fn per_provider_request_encoding_pagination_failure_and_rank_oracles() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/json-provider-golden.json")).unwrap();
    let registry = Registry::load(None).unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let provider = Kind::named(case["provider"].as_str().unwrap()).unwrap();
        let config = Config::from_values(serde_json::from_value(case["env"].clone()).unwrap());
        let steps = case["steps"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| {
                let request = Request {
                    url: s["request"]["url"].as_str().unwrap().into(),
                    headers: serde_json::from_value(s["request"]["headers"].clone()).unwrap(),
                };
                let outcome = if let Some(kind) = s["error_kind"].as_str() {
                    Err(ProviderError::synthetic(match kind {
                        "FetchError" => "FetchError",
                        "TimeoutError" => "TimeoutError",
                        _ => panic!("unexpected fixture error kind"),
                    }))
                } else {
                    Ok(HttpResponse {
                        url: request.url.clone(),
                        status: 200,
                        headers: [(
                            "content-type".into(),
                            "application/json; charset=utf-8".into(),
                        )]
                        .into(),
                        body: s["text"].as_str().unwrap().as_bytes().to_vec(),
                    })
                };
                Step { request, outcome }
            })
            .collect();
        let mut transport = OfflineTransport::new(steps);
        let result = JsonSearch {
            kind: provider,
            config,
        }
        .search(
            case["query"].as_str().unwrap(),
            case["limit"].as_i64().unwrap(),
            &mut transport,
            &Context {
                registry: &registry,
                year: 2026,
            },
        );
        let actual = match result {
            Ok(results) => json!({"results":results}),
            Err(e) => {
                assert!(
                    !e.to_string().contains("public-fixture-key"),
                    "{} {} diagnostics",
                    case["provider"],
                    case["name"]
                );
                json!({"error_kind":e.kind})
            }
        };
        assert_eq!(
            actual, case["expected"],
            "{} {}",
            case["provider"], case["name"]
        );
        assert_eq!(transport.calls, case["steps"].as_array().unwrap().len());
        transport.finish().unwrap();
    }
}

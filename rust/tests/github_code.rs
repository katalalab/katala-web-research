use kwr::{
    http::HttpResponse,
    providers::{
        Context, OfflineTransport, ProviderError, Request, SearchProvider, Step, github::GitHubCode,
    },
    registry::Registry,
};
use serde_json::{Value, json};
#[test]
fn code_request_paging_query_rejection_fragment_and_metadata_oracles() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/github-code-golden.json")).unwrap();
    let registry = Registry::load(None).unwrap();
    for case in fixture["cases"].as_array().unwrap() {
        let steps = case["steps"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| {
                let request: Request = Request {
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
        let actual = match GitHubCode::with_token(case["token"].as_str().unwrap().into()).search(
            case["query"].as_str().unwrap(),
            case["limit"].as_i64().unwrap(),
            &mut transport,
            &Context {
                registry: &registry,
                year: 2026,
            },
        ) {
            Ok(results) => json!({"results":results}),
            Err(e) => {
                assert!(!e.to_string().contains("public-fixture-key"));
                json!({"error_kind":e.kind})
            }
        };
        assert_eq!(actual, case["expected"], "{}", case["name"]);
        assert_eq!(transport.calls, case["steps"].as_array().unwrap().len());
        transport.finish().unwrap();
    }
}

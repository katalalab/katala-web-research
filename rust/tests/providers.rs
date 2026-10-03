use kwr::{
    http::HttpResponse,
    providers::{
        Context, DuckDuckGo, OfflineTransport, ProviderError, Request, SearchProvider, Step,
        Transport, ddg_request, parse_ddg,
    },
    registry::Registry,
};
use serde_json::Value;
fn response(text: &str) -> HttpResponse {
    HttpResponse {
        url: "fixture".into(),
        status: 200,
        headers: [("content-type".into(), "text/html; charset=utf-8".into())].into(),
        body: text.as_bytes().to_vec(),
    }
}
#[test]
fn python_derived_ddg_parser_request_and_rank_goldens() {
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/provider-golden.json")).unwrap();
    let registry = Registry::load(None).unwrap();
    for case in fixture["parsers"].as_array().unwrap() {
        assert_eq!(
            serde_json::to_value(parse_ddg(case["html"].as_str().unwrap())).unwrap(),
            case["expected"],
            "parser {}",
            case["name"]
        );
    }
    for case in fixture["searches"].as_array().unwrap() {
        let expected = Request {
            url: case["request"]["url"].as_str().unwrap().into(),
            headers: serde_json::from_value(case["request"]["headers"].clone()).unwrap(),
        };
        let mut transport = OfflineTransport::new(vec![Step {
            request: expected,
            outcome: Ok(response(case["html"].as_str().unwrap())),
        }]);
        let actual = DuckDuckGo
            .search(
                case["query"].as_str().unwrap(),
                case["limit"].as_i64().unwrap(),
                &mut transport,
                &Context {
                    registry: &registry,
                    year: 2026,
                },
            )
            .unwrap();
        assert_eq!(
            serde_json::to_value(actual).unwrap(),
            case["expected"],
            "search {} limit {}",
            case["name"],
            case["limit"]
        );
        assert_eq!(transport.calls, 1);
        transport.finish().unwrap();
    }
}
#[test]
fn offline_transport_rejects_unscripted_calls_and_no_retries() {
    let registry = Registry::load(None).unwrap();
    let context = Context {
        registry: &registry,
        year: 2026,
    };
    let request = ddg_request("fixture");
    for kind in ["FetchError", "TimeoutError", "IncompleteRead"] {
        let mut transport = OfflineTransport::new(vec![Step {
            request: request.clone(),
            outcome: Err(ProviderError::synthetic(kind)),
        }]);
        let error = DuckDuckGo
            .search("fixture", 10, &mut transport, &context)
            .unwrap_err();
        assert_eq!(error.kind, kind);
        assert_eq!(transport.calls, 1);
        transport.finish().unwrap();
    }
    let mut empty = OfflineTransport::new(vec![]);
    assert_eq!(empty.get(&request).err().unwrap().kind, "FixtureError");
    let unused = OfflineTransport::new(vec![Step {
        request: request.clone(),
        outcome: Ok(response("")),
    }]);
    assert!(unused.finish().is_err());
    let mut mismatch = OfflineTransport::new(vec![Step {
        request,
        outcome: Ok(response("")),
    }]);
    assert!(mismatch.get(&ddg_request("other")).is_err());
    assert!(mismatch.finish().is_err());
}

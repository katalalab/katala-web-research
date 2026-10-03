use kwr::{
    http::HttpResponse,
    providers::{Context, OfflineTransport, ProviderError, Request, Step},
};
use serde_json::Value;

#[test]
fn enrichment_reference_transcripts() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/enrichment-golden.json")).unwrap();
    let registry = kwr::registry::Registry::load(None).unwrap();
    let context = Context {
        registry: &registry,
        year: 2026,
    };
    for case in cases {
        let steps = case["steps"]
            .as_array()
            .unwrap()
            .iter()
            .map(|step| Step {
                request: Request {
                    url: step["request"]["url"].as_str().unwrap().into(),
                    headers: serde_json::from_value(step["request"]["headers"].clone()).unwrap(),
                },
                outcome: if let Some(kind) = step["error_kind"].as_str() {
                    Err(ProviderError::synthetic(match kind {
                        "FetchError" => "FetchError",
                        "TimeoutError" => "TimeoutError",
                        "ValueError" => "ValueError",
                        "RuntimeError" => "RuntimeError",
                        _ => panic!("unknown fixture error"),
                    }))
                } else {
                    let response = &step["response"];
                    Ok(HttpResponse {
                        url: response["url"].as_str().unwrap().into(),
                        status: response["status"].as_u64().unwrap() as u16,
                        headers: serde_json::from_value(response["headers"].clone()).unwrap(),
                        body: serde_json::from_value(response["body"].clone()).unwrap(),
                    })
                },
            })
            .collect();
        let mut transport = OfflineTransport::new(steps);
        let mut clocks = 0;
        let results = kwr::workflow::enrich_offline(
            case["query"].as_str().unwrap(),
            serde_json::from_value(case["results"].clone()).unwrap(),
            case["read_top"].as_i64().unwrap(),
            case["reader"].as_str().unwrap(),
            &mut transport,
            &context,
            || {
                clocks += 1;
                "2026-01-01T00:00:00+00:00".into()
            },
        );
        assert_eq!(
            serde_json::to_value(results).unwrap(),
            case["expected"],
            "{}",
            case["name"]
        );
        assert_eq!(clocks, case["clock_calls"].as_u64().unwrap());
        assert_eq!(transport.calls, case["steps"].as_array().unwrap().len());
        transport.finish().unwrap();
    }
}

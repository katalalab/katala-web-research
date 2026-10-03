use kwr::http::{HttpResponse, Proxies, redact_url, resolve_timeout};
use serde_json::Value;
use std::collections::BTreeMap;
#[test]
fn reference_charset_proxy_and_redaction_goldens() {
    let fixture: Value = serde_json::from_str(include_str!("fixtures/http-golden.json")).unwrap();
    for case in fixture["decode"].as_array().unwrap() {
        let response = HttpResponse {
            url: "fixture".into(),
            status: 200,
            headers: [(
                "content-type".into(),
                case["content_type"].as_str().unwrap().into(),
            )]
            .into(),
            body: serde_json::from_value(case["bytes"].clone()).unwrap(),
        };
        assert_eq!(
            response.text(),
            case["expected"].as_str().unwrap(),
            "charset {}",
            case["content_type"]
        );
    }
    for case in fixture["proxies"].as_array().unwrap() {
        let values: BTreeMap<String, String> =
            serde_json::from_value(case["values"].clone()).unwrap();
        let proxies = Proxies::from_values(&values);
        assert_eq!(serde_json::to_value(&proxies.http).unwrap(), case["http"]);
        assert_eq!(serde_json::to_value(&proxies.https).unwrap(), case["https"]);
        assert_eq!(
            serde_json::to_value(&proxies.no_proxy).unwrap(),
            case["no_proxy"]
        );
        for probe in case["bypass"].as_array().unwrap() {
            assert_eq!(
                proxies.bypass(
                    probe["host"].as_str().unwrap(),
                    probe["port"].as_u64().map(|p| p as u16)
                ),
                probe["expected"].as_bool().unwrap()
            );
        }
    }
    for case in fixture["redact"].as_array().unwrap() {
        assert_eq!(
            redact_url(case["input"].as_str().unwrap()),
            case["expected"].as_str().unwrap()
        );
    }
}
#[test]
fn timeout_configuration_is_finite_positive_and_representable() {
    for (value, seconds) in [
        ("", 20.0),
        ("  ", 20.0),
        ("0.15", 0.15),
        (" 2.5 ", 2.5),
        ("1e2", 100.0),
    ] {
        assert_eq!(resolve_timeout(value).unwrap().as_secs_f64(), seconds);
    }
    for value in ["0", "-1", "bad", "nan", "inf", "-inf", "1e200"] {
        assert!(resolve_timeout(value).is_err(), "{value}");
    }
}

use kwr::{feeds, registry::Registry, search};
use serde_json::Value;
#[test]
fn reference_feed_ranking_and_html_goldens() {
    let golden: Value = serde_json::from_str(include_str!("fixtures/feed-golden.json")).unwrap();
    for case in golden["feeds"].as_array().unwrap() {
        let parsed = feeds::parse(
            case["text"].as_str().unwrap(),
            case["source_url"].as_str().unwrap(),
            case["fetched_at"].as_str().unwrap(),
        )
        .unwrap();
        assert_eq!(
            serde_json::to_value(parsed).unwrap(),
            case["expected"],
            "feed {}",
            case["text"]
        );
    }
    let registry = Registry::load(None).unwrap();
    for case in golden["ranking"].as_array().unwrap() {
        let inputs = serde_json::from_value(case["input"].clone()).unwrap();
        let ranked = search::rank(
            case["query"].as_str().unwrap(),
            inputs,
            &registry,
            case["year"].as_i64().unwrap() as i32,
        );
        assert_eq!(
            serde_json::to_value(ranked).unwrap(),
            case["expected"],
            "query {}",
            case["query"]
        );
    }
    for case in golden["html"].as_array().unwrap() {
        let parsed = kwr::text::html_text(case["input"].as_str().unwrap());
        assert_eq!(parsed.title, case["title"].as_str().unwrap());
        assert_eq!(parsed.content, case["content"].as_str().unwrap());
    }
    for case in golden["entities"].as_array().unwrap() {
        let actual = kwr::text::unescape(case["input"].as_str().unwrap());
        let expected = case["expected"].as_str().unwrap();
        if actual != expected {
            let first = actual
                .chars()
                .zip(expected.chars())
                .position(|(a, b)| a != b)
                .unwrap_or(actual.chars().count().min(expected.chars().count()));
            panic!(
                "entity mismatch at {first}: actual {:?}, expected {:?}",
                actual
                    .chars()
                    .skip(first.saturating_sub(20))
                    .take(60)
                    .collect::<String>(),
                expected
                    .chars()
                    .skip(first.saturating_sub(20))
                    .take(60)
                    .collect::<String>()
            );
        }
    }
    for case in golden["queries"].as_array().unwrap() {
        let categories: Vec<String> = serde_json::from_value(case["categories"].clone()).unwrap();
        let includes: Vec<String> = serde_json::from_value(case["includes"].clone()).unwrap();
        let excludes: Vec<String> = serde_json::from_value(case["excludes"].clone()).unwrap();
        let built = search::build_query(
            case["query"].as_str().unwrap(),
            &categories,
            &includes,
            &excludes,
        );
        assert_eq!(
            serde_json::json!({"query":built.query,"domains":built.domains,"pdf":built.pdf}),
            case["expected"]
        );
    }
    for case in golden["highlights"].as_array().unwrap() {
        assert_eq!(
            search::highlight(
                case["query"].as_str().unwrap(),
                case["content"].as_str().unwrap()
            ),
            case["expected"].as_str().unwrap()
        );
    }
}
#[test]
fn malformed_and_non_feed_inputs_are_rejected() {
    for input in [
        "<rss><broken>",
        "<urlset><url/></urlset>",
        "{invalid}",
        "[]",
        "<!DOCTYPE rss [<!ENTITY x 'text'>]><rss><channel><title>&x;</title></channel></rss>",
    ] {
        assert!(feeds::parse(input, "https://fixture.test/feed", "fixed").is_err());
    }
}

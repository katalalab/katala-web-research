//! Owned library fixture; no environment/CLI production test hook.
use std::io::Read;
fn main() {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).unwrap();
    let input: serde_json::Value = serde_json::from_str(&input).unwrap();
    let registry = kwr::registry::Registry::load(None).unwrap();
    let context = kwr::providers::Context {
        registry: &registry,
        year: 2026,
    };
    let archive = input["archive"].as_str().map(std::path::Path::new);
    let outcome = kwr::providers::meta::native_search(
        input["query"].as_str().unwrap(),
        input["limit"].as_i64().unwrap(),
        archive,
        &context,
    );
    let value = match outcome {
        Ok(results) => serde_json::json!({"results":results}),
        Err(e) => serde_json::json!({"error_kind":e.kind,"message":e.to_string()}),
    };
    println!("{value}");
}

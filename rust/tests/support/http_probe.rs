//! Test-only probe for the stdlib fixture harness; not a kwr command.
use kwr::http::{HttpResponse, Settings, fetch_url};
use serde_json::{Value, json};
use std::{io::Read, time::Duration};
fn main() {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).unwrap();
    let input: Value = serde_json::from_str(&input).unwrap();
    let settings = Settings::from_env().map(|mut settings| {
        if let Some(seconds) = input["timeout"].as_f64() {
            settings.timeout = Duration::from_secs_f64(seconds);
        }
        if let Some(limit) = input["limit"].as_u64() {
            settings.body_limit = Some(limit as usize);
        }
        if let Some(pem) = input["root_pem"].as_str() {
            settings
                .root_certificates
                .push(reqwest::Certificate::from_pem(pem.as_bytes()).unwrap());
        }
        settings
    });
    let result = settings.and_then(|s| {
        fetch_url(
            input["url"].as_str().unwrap(),
            &[("Accept", kwr::http::FEED_ACCEPT)],
            &s,
        )
    });
    let output = match result {
        Ok(response) => {
            let text = response.text();
            let HttpResponse {
                url,
                status,
                headers,
                body,
            } = response;
            json!({"url":url,"status":status,"headers":headers,"body":body,"text":text})
        }
        Err(e) => json!({"error_kind":e.kind,"error_message":e.to_string()}),
    };
    println!("{}", serde_json::to_string(&output).unwrap());
}

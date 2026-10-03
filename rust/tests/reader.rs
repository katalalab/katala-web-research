use kwr::{
    http::HttpResponse,
    providers::{OfflineTransport, ProviderError, Request, Step},
};
use serde_json::{Value, json};
#[test]
fn direct_reference_cases() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/reader-golden.json")).unwrap();
    for case in cases {
        let steps = case["requests"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| Step {
                request: Request {
                    url: r["url"].as_str().unwrap().into(),
                    headers: serde_json::from_value(r["headers"].clone()).unwrap(),
                },
                outcome: if let Some(kind) = case["error"].as_str() {
                    Err(ProviderError::synthetic(match kind {
                        "FetchError" => "FetchError",
                        "TimeoutError" => "TimeoutError",
                        _ => "ValueError",
                    }))
                } else {
                    Ok(HttpResponse {
                        url: case["returned"].as_str().unwrap().into(),
                        status: case["status"].as_u64().unwrap() as u16,
                        headers: serde_json::from_value(case["headers"].clone()).unwrap(),
                        body: serde_json::from_value(case["body"].clone()).unwrap(),
                    })
                },
            })
            .collect();
        let mut transport = OfflineTransport::new(steps);
        let actual =
            match kwr::reader::direct_with(case["url"].as_str().unwrap(), &mut transport, || {
                "2026-01-01T00:00:00+00:00".into()
            }) {
                Ok(page) => json!({"page":page}),
                Err(error) => json!({"error_kind":error.kind}),
            };
        assert_eq!(actual, case["expected"], "{}", case["name"]);
        assert_eq!(transport.calls, case["requests"].as_array().unwrap().len());
        transport.finish().unwrap();
    }
}

#[test]
fn real_sqlite_writer_contention_and_abort_preserve_page_and_fts() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("reader.sqlite");
    let archive = kwr::archive::Archive::open(&path).unwrap();
    let mut page = kwr::reader::PageSnapshot {
        url: "https://fixture.test/page".into(),
        title: "old".into(),
        content: "old evidence".into(),
        source: "cached".into(),
        fetched_at: "fixed".into(),
        status_code: Some(200),
        content_type: Some("text/plain".into()),
    };
    archive.upsert_page(&page).unwrap();
    let original = archive.cached_page(&page.url).unwrap();
    let competitor = rusqlite::Connection::open(&path).unwrap();
    competitor.execute_batch("BEGIN IMMEDIATE").unwrap();
    archive
        .conn
        .busy_timeout(std::time::Duration::from_millis(20))
        .unwrap();
    page.content = "new evidence".into();
    assert!(archive.upsert_page(&page).is_err());
    competitor.execute_batch("ROLLBACK").unwrap();
    assert_eq!(archive.cached_page(&page.url).unwrap(), original);
    archive.conn.execute_batch("CREATE TEMP TRIGGER abort_reader BEFORE UPDATE ON pages BEGIN SELECT RAISE(ABORT,'owned fixture'); END;").unwrap();
    assert!(archive.upsert_page(&page).is_err());
    assert_eq!(archive.cached_page(&page.url).unwrap(), original);
    let stored: String = archive
        .conn
        .query_row(
            "SELECT content FROM pages_fts WHERE pages_fts MATCH 'old'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(stored, "old evidence");
    let count: i64 = archive
        .conn
        .query_row(
            "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'new'",
            [],
            |r| r.get(0),
        )
        .unwrap();
    assert_eq!(count, 0);
    let integrity: String = archive
        .conn
        .query_row("PRAGMA integrity_check", [], |r| r.get(0))
        .unwrap();
    assert_eq!(integrity, "ok");
}

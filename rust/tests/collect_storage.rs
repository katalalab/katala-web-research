use kwr::{archive::Archive, search::SearchResult};
use serde_json::{Value, json};

fn rows(archive: &Archive) -> (Vec<Value>, Vec<Value>) {
    (
        kwr::archive::query_json(&archive.conn, "SELECT * FROM runs ORDER BY id", &[]).unwrap(),
        kwr::archive::query_json(
            &archive.conn,
            "SELECT * FROM search_results ORDER BY id",
            &[],
        )
        .unwrap(),
    )
}
fn result(rank: i64) -> SearchResult {
    serde_json::from_value(json!({"title":"alpha 日本語","url":"https://fixture.test/item","snippet":"evidence","source":"feed","published_at":null,"rank":rank,"score":1.25,"metadata":{}})).unwrap()
}

#[test]
fn store_run_python_sequences_and_durable_reopen() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/collect-storage-golden.json")).unwrap();
    for case in cases {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("日本語.sqlite");
        let mut archive = Archive::open(&path).unwrap();
        let mut clocks = 0;
        for (call, expected) in case["calls"]
            .as_array()
            .unwrap()
            .iter()
            .zip(case["expected"].as_array().unwrap())
        {
            let input: Vec<SearchResult> = serde_json::from_value(call["results"].clone()).unwrap();
            let id = archive
                .store_run_with_clock(
                    call["query"].as_str().unwrap(),
                    call["provider"].as_str().unwrap(),
                    &input,
                    || {
                        clocks += 1;
                        "2026-01-01T00:00:00+00:00".into()
                    },
                )
                .unwrap();
            let (runs, results) = rows(&archive);
            assert_eq!(
                json!({"run_id":id,"runs":runs,"results":results}),
                *expected,
                "{}",
                case["name"]
            );
            assert!(archive.conn.is_autocommit());
            drop(archive);
            archive = Archive::open(&path).unwrap();
            let (runs, results) = rows(&archive);
            assert_eq!(
                json!({"run_id":id,"runs":runs,"results":results}),
                *expected,
                "{} durable reopen",
                case["name"]
            );
        }
        assert_eq!(clocks, case["clock_calls"].as_u64().unwrap());
        assert_eq!(
            archive
                .conn
                .query_row("PRAGMA integrity_check", [], |r| r.get::<_, String>(0))
                .unwrap(),
            "ok"
        );
    }
}

#[test]
fn actual_writer_lock_and_later_result_abort_roll_back_only_new_batch() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("synthetic.sqlite");
    let archive = Archive::open(&path).unwrap();
    archive
        .store_run_with_clock("old", "feed", &[result(1)], || "fixed".into())
        .unwrap();
    archive
        .upsert_page(&kwr::reader::PageSnapshot {
            url: "https://fixture.test/page".into(),
            title: "old".into(),
            content: "old evidence".into(),
            source: "cached".into(),
            fetched_at: "fixed".into(),
            status_code: Some(200),
            content_type: Some("text/plain".into()),
        })
        .unwrap();
    let old = rows(&archive);
    let page = archive.cached_page("https://fixture.test/page").unwrap();
    let competitor = rusqlite::Connection::open(&path).unwrap();
    competitor.execute_batch("BEGIN IMMEDIATE").unwrap();
    archive
        .conn
        .busy_timeout(std::time::Duration::from_millis(20))
        .unwrap();
    assert!(archive.store_run("blocked", "feed", &[result(2)]).is_err());
    competitor.execute_batch("ROLLBACK").unwrap();
    assert!(archive.conn.is_autocommit());
    assert_eq!(rows(&archive), old);
    archive.conn.execute_batch("CREATE TEMP TRIGGER fail_later_result BEFORE INSERT ON search_results WHEN new.rank=3 BEGIN SELECT RAISE(ABORT,'owned fixture'); END;").unwrap();
    assert!(
        archive
            .store_run_with_clock("partial", "feed", &[result(2), result(3)], || "fixed"
                .into())
            .is_err()
    );
    assert!(archive.conn.is_autocommit());
    assert_eq!(rows(&archive), old);
    assert_eq!(
        archive.cached_page("https://fixture.test/page").unwrap(),
        page
    );
    archive
        .conn
        .execute_batch("INSERT INTO pages_fts(pages_fts,rank) VALUES('integrity-check',1)")
        .unwrap();
    assert_eq!(
        archive
            .conn
            .query_row(
                "SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'old'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
        1
    );
    archive
        .conn
        .execute_batch("DROP TRIGGER fail_later_result")
        .unwrap();
    assert_eq!(
        archive
            .store_run_with_clock("retry", "feed", &[result(2), result(3)], || "fixed".into())
            .unwrap(),
        2
    );
    assert_eq!(rows(&archive).0.len(), 2);
    assert_eq!(rows(&archive).1.len(), 3);
}

#[test]
fn default_clock_writes_utc_seconds() {
    let temp = tempfile::tempdir().unwrap();
    let archive = Archive::open(&temp.path().join("clock.sqlite")).unwrap();
    let id = archive.store_run("clock", "feed", &[result(1)]).unwrap();
    let stamp: String = archive
        .conn
        .query_row("SELECT created_at FROM runs WHERE id=?", [id], |r| r.get(0))
        .unwrap();
    assert_eq!(stamp.len(), 25);
    assert!(stamp.ends_with("+00:00"));
    let parsed = chrono::DateTime::parse_from_rfc3339(&stamp).unwrap();
    assert_eq!(parsed.timestamp_subsec_nanos(), 0);
    assert_eq!(parsed.offset().local_minus_utc(), 0);
    assert!(archive.conn.is_autocommit());
}

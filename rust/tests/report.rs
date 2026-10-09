use kwr::{reader::PageSnapshot, report, search::SearchResult};
use serde_json::Value;

#[test]
fn unchanged_python_report_goldens() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/report-golden.json")).unwrap();
    for case in &cases {
        let mut results: Vec<SearchResult> =
            serde_json::from_value(case["results"].clone()).unwrap();
        // The public renderer takes a typed f64; parse exact Python float repr so
        // this test does not conflate report rendering with serde JSON parsing.
        if let Some(text) = case["score_text"].as_str() {
            results[0].score = text.parse().unwrap();
        }
        let pages: Vec<PageSnapshot> = serde_json::from_value(case["pages"].clone()).unwrap();
        let mut clocks = 0;
        let actual = report::build(
            case["query"].as_str().unwrap(),
            case["provider"].as_str().unwrap(),
            &results,
            &pages,
            case["archive"].as_str().unwrap(),
            || {
                clocks += 1;
                "2026-01-01T00:00:00+00:00".into()
            },
        );
        assert_eq!(
            actual,
            case["expected"].as_str().unwrap(),
            "{}",
            case["name"]
        );
        assert_eq!(clocks, case["clock_calls"].as_u64().unwrap());
    }
}

#[test]
fn no_clobber_publication_preserves_existing_paths_and_cleans_temporary_files() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("日本語/report.md");
    report::write_new(&path, "日本語\n").unwrap();
    assert_eq!(std::fs::read(&path).unwrap(), "日本語\n".as_bytes());
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            std::fs::metadata(&path).unwrap().permissions().mode() & 0o777,
            0o600
        );
    }
    assert!(report::write_new(&path, "replacement\n").is_err());
    assert_eq!(std::fs::read(&path).unwrap(), "日本語\n".as_bytes());
    assert_eq!(
        std::fs::read_dir(path.parent().unwrap()).unwrap().count(),
        1
    );
    #[cfg(unix)]
    {
        let link = tmp.path().join("link.md");
        std::os::unix::fs::symlink(&path, &link).unwrap();
        assert!(report::write_new(&link, "replacement").is_err());
        assert!(
            std::fs::symlink_metadata(link)
                .unwrap()
                .file_type()
                .is_symlink()
        );
        assert_eq!(std::fs::read(path).unwrap(), "日本語\n".as_bytes());
    }
}

#[test]
fn lexical_utf8_report_paths_preserve_parent_components() {
    for (input, expected) in [
        ("./reports//./日本語.md", "reports/日本語.md"),
        ("", "."),
        ("a/../b", "a/../b"),
        ("./", "."),
    ] {
        assert_eq!(report::lexical_path(input).to_string_lossy(), expected);
    }
    #[cfg(unix)]
    for (input, expected) in [("//a///./b", "//a/b"), ("///a//b", "/a/b")] {
        assert_eq!(report::lexical_path(input).to_string_lossy(), expected);
    }
}

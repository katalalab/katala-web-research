use serde_json::Value;
use std::process::Command;

#[test]
fn native_eval_cli_emits_a_successful_json_summary() {
    let output = Command::new(env!("CARGO_BIN_EXE_kwr-rs"))
        .args(["eval", "--json"])
        .env_remove("KWR_SOURCE_REGISTRY_OVERLAY")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(0));
    assert!(serde_json::from_slice::<Value>(&output.stdout).is_ok());
    assert_eq!(output.stderr, b"");
}

#[test]
fn native_eval_cli_matches_python_reference_goldens() {
    let goldens: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/evaluation-golden.json")).unwrap();
    for golden in goldens {
        let args = golden["args"]
            .as_array()
            .unwrap()
            .iter()
            .map(|arg| arg.as_str().unwrap())
            .collect::<Vec<_>>();
        let output = Command::new(env!("CARGO_BIN_EXE_kwr-rs"))
            .args([vec!["eval"], args.clone()].concat())
            .env_remove("KWR_SOURCE_REGISTRY_OVERLAY")
            .output()
            .unwrap();
        assert_eq!(
            output.status.code(),
            golden["exit"].as_i64().map(|code| code as i32),
            "{args:?}"
        );
        assert_eq!(
            String::from_utf8(output.stdout).unwrap(),
            golden["stdout"].as_str().unwrap(),
            "{args:?}"
        );
        assert_eq!(output.stderr, b"", "{args:?}");
    }
}

#[test]
fn native_eval_creates_missing_report_parent_like_python() {
    for (options, status) in [
        (vec![], 0),
        (vec!["--min-score", "90", "--max-subqueries", "1"], 1),
    ] {
        let root = tempfile::tempdir().unwrap();
        let report = root.path().join("reports/research-quality.md");
        let output = Command::new(env!("CARGO_BIN_EXE_kwr-rs"))
            .args(["eval", "--out", report.to_str().unwrap()])
            .args(options)
            .env_remove("KWR_SOURCE_REGISTRY_OVERLAY")
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(status));
        assert!(report.is_file());
        assert!(output.stderr.is_empty());
    }
}

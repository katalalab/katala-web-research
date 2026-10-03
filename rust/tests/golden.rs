use serde_json::Value;
use std::process::Command;
#[test]
fn python_baseline_golden_cli() {
    let golden: Value = serde_json::from_str(include_str!("fixtures/golden.json")).unwrap();
    assert_eq!(
        golden["baseline"],
        "e66e449cc210bd80ecb25a00391091e72abd9c2b"
    );
    let cwd = tempfile::tempdir().unwrap();
    for case in golden["cases"].as_array().unwrap() {
        let args: Vec<_> = case["args"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_str().unwrap())
            .collect();
        let result = Command::new(env!("CARGO_BIN_EXE_kwr-rs"))
            .args(&args)
            .env_remove("KWR_SOURCE_REGISTRY_OVERLAY")
            .current_dir(cwd.path())
            .output()
            .unwrap();
        assert_eq!(
            result.status.code().unwrap(),
            case["exit"].as_i64().unwrap() as i32,
            "{args:?}"
        );
        let actual: Value = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(actual, case["json"], "{args:?}");
        assert_eq!(
            String::from_utf8(result.stderr).unwrap(),
            case["stderr"].as_str().unwrap(),
            "{args:?}"
        );
    }
}

//! Synthetic differential harness, not a collect CLI or shipped capture command.
use kwr::{archive::Archive, search::SearchResult};
use serde::Deserialize;
use serde_json::json;
use std::io::{self, Read};

#[derive(Deserialize)]
struct Input {
    archive: std::path::PathBuf,
    calls: Vec<Call>,
    #[serde(default)]
    abort_later: bool,
}
#[derive(Deserialize)]
struct Call {
    query: String,
    provider: String,
    results: Vec<SearchResult>,
}
fn main() -> kwr::Result<()> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;
    let input: Input = serde_json::from_str(&input)?;
    let mut archive = Archive::open(&input.archive)?;
    let mut ids = Vec::new();
    for call in input.calls {
        if input.abort_later {
            archive.conn.execute_batch("CREATE TEMP TRIGGER fail_later_result BEFORE INSERT ON search_results WHEN new.rank=3 BEGIN SELECT RAISE(ABORT,'owned fixture'); END;")?;
        }
        ids.push(archive.store_run_with_clock(
            &call.query,
            &call.provider,
            &call.results,
            || "2026-01-01T00:00:00+00:00".into(),
        )?);
        drop(archive);
        archive = Archive::open(&input.archive)?;
    }
    println!("{}", json!({"run_ids":ids}));
    Ok(())
}

//! Pure Python-compatible Markdown rendering and preview no-clobber publication.
use crate::{Result, reader::PageSnapshot, search::SearchResult};
use std::{io::Write, path::Path};

fn python_whitespace(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

fn score(value: f64) -> String {
    if value.is_nan() {
        return "nan".into();
    }
    let text = format!("{value:?}");
    if let Some((mantissa, exponent)) = text.split_once('e') {
        let exponent: i32 = exponent.parse().unwrap();
        format!("{mantissa}e{exponent:+03}")
    } else {
        text
    }
}

pub fn build(
    query: &str,
    provider: &str,
    results: &[SearchResult],
    pages: &[PageSnapshot],
    archive_path: &str,
    clock: impl FnOnce() -> String,
) -> String {
    let mut lines = vec![
        format!("# Web Research Report: {query}"),
        String::new(),
        format!("- generated_at: {}", clock()),
        format!("- provider: {provider}"),
        format!("- archive: `{archive_path}`"),
        format!("- results: {}", results.len()),
        format!("- pages_read: {}", pages.len()),
        String::new(),
        "## Ranked Results".into(),
        String::new(),
    ];
    for result in results {
        lines.extend([
            format!("### {}. {}", result.rank, result.title),
            String::new(),
            format!("- url: {}", result.url),
            format!("- source: {}", result.source),
            format!("- score: {}", score(result.score)),
            format!(
                "- published_at: {}",
                result
                    .published_at
                    .as_deref()
                    .filter(|date| !date.is_empty())
                    .unwrap_or("unknown")
            ),
            format!(
                "- snippet: {}",
                if result.snippet.is_empty() {
                    "none"
                } else {
                    &result.snippet
                }
            ),
            String::new(),
        ]);
    }
    if !pages.is_empty() {
        lines.extend(["## Captured Pages".into(), String::new()]);
        for page in pages {
            let excerpt: String = page.content.chars().take(700).collect();
            let excerpt = excerpt.replace('\n', " ");
            lines.extend([
                format!("### {}", page.title),
                String::new(),
                format!("- url: {}", page.url),
                format!("- reader: {}", page.source),
                format!("- fetched_at: {}", page.fetched_at),
                String::new(),
                excerpt.trim_matches(python_whitespace).into(),
                String::new(),
            ]);
        }
    }
    format!("{}\n", lines.join("\n").trim_end_matches(python_whitespace))
}

/// Unlike Python write_text, existing destinations (including symlinks) fail.
/// The run is already committed by the CLI before this function is called.
pub fn write_new(path: &Path, report: &str) -> Result<()> {
    let parent = path.parent().filter(|p| !p.as_os_str().is_empty());
    let parent = parent.unwrap_or_else(|| Path::new("."));
    std::fs::create_dir_all(parent)?;
    let mut temp = tempfile::Builder::new()
        .prefix(".kwr-report-")
        .tempfile_in(parent)?;
    temp.write_all(report.as_bytes())?;
    temp.as_file().sync_all()?;
    temp.persist_noclobber(path).map_err(|error| error.error)?;
    Ok(())
}

/// Python Path removes redundant separators and dot components, preserving .. .
/// Actual Windows and non-UTF8 path gates remain pending.
pub fn lexical_path(value: &str) -> std::path::PathBuf {
    use std::path::{Component, PathBuf};
    let mut normalized = PathBuf::new();
    for part in Path::new(value).components() {
        if part != Component::CurDir {
            normalized.push(part);
        }
    }
    if normalized.as_os_str().is_empty() {
        normalized.push(".");
    }
    #[cfg(unix)]
    if value.starts_with("//") && !value.starts_with("///") {
        normalized = PathBuf::from(format!("/{}", normalized.display()));
    }
    normalized
}

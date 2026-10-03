pub mod archive;
pub mod migration;
pub mod planner;
pub mod registry;

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
pub fn now() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, false)
}

// Python str.split treats the four C0 separators as whitespace too.
pub fn words(value: &str) -> impl Iterator<Item = &str> {
    value
        .split(|c: char| c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c))
        .filter(|s| !s.is_empty())
}

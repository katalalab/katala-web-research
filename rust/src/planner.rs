use serde::Serialize;

#[derive(Debug, Serialize, PartialEq)]
pub struct Step {
    pub intent: &'static str,
    pub query: String,
}

pub fn plan(query: &str, maximum: i64, year: Option<i64>) -> Vec<Step> {
    let cleaned = crate::words(query).collect::<Vec<_>>().join(" ");
    if cleaned.is_empty() {
        return vec![];
    }
    let mut candidates = vec![
        Step {
            intent: "baseline",
            query: cleaned.clone(),
        },
        Step {
            intent: "official",
            query: format!("{cleaned} official docs documentation"),
        },
        Step {
            intent: "primary",
            query: format!("{cleaned} GitHub arxiv paper benchmark"),
        },
        Step {
            intent: "critique",
            query: format!("{cleaned} limitations evaluation source quality"),
        },
    ];
    if let Some(year) = year
        && !cleaned.contains(&year.to_string())
    {
        candidates.push(Step {
            intent: "freshness",
            query: format!("{cleaned} {year} latest changelog release notes"),
        });
    }
    // Python historically emits the first step for nonpositive maxima.
    candidates.truncate(maximum.max(1) as usize);
    candidates
}

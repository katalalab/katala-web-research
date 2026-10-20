//! Deterministic, bundled evaluation preview. Python is the development oracle only.
use crate::{
    Result, planner,
    registry::Registry,
    search::{self, SearchResult},
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

const RELEVANT_GRADE: i64 = 1;

#[derive(Deserialize)]
struct Fixture {
    year: i32,
    cases: Vec<Case>,
}

#[derive(Clone, Deserialize)]
struct Case {
    name: String,
    category: String,
    query: String,
    candidates: Vec<SearchResult>,
    expected_plan_intents: Vec<String>,
    preferred_url_terms: Vec<String>,
    #[serde(default)]
    discouraged_url_terms: Vec<String>,
    #[serde(default = "minimum_quality")]
    min_top_quality: i64,
    #[serde(default)]
    relevance: Vec<(String, i64)>,
}
fn minimum_quality() -> i64 {
    75
}

#[derive(Clone, Serialize)]
pub struct CaseResult {
    category: String,
    metrics: BTreeMap<String, Value>,
    name: String,
    passed: bool,
    plan_intents: Vec<String>,
    query: String,
    retrieval: BTreeMap<String, f64>,
    score: i64,
    top_urls: Vec<String>,
}

#[derive(Serialize)]
pub struct Summary {
    pub cases: Vec<CaseResult>,
    pub category_scores: BTreeMap<String, i64>,
    pub min_score: i64,
    pub passed: bool,
    pub retrieval: BTreeMap<String, Value>,
    pub score: i64,
}

fn fixtures() -> Result<Fixture> {
    Ok(serde_json::from_str(include_str!(
        "../tests/fixtures/evaluation-cases.json"
    ))?)
}

fn rounded(value: f64, places: usize) -> f64 {
    format!("{value:.places$}").parse().unwrap()
}
fn first_index(urls: &[String], terms: &[String]) -> Option<usize> {
    urls.iter()
        .position(|url| terms.iter().any(|term| url.contains(term)))
}
fn discouraged_above_preferred(case: &Case, urls: &[String]) -> bool {
    let preferred = first_index(urls, &case.preferred_url_terms);
    first_index(urls, &case.discouraged_url_terms)
        .is_some_and(|discouraged| preferred.is_none_or(|i| discouraged < i))
}
fn recall(urls: &[String], labels: &BTreeMap<String, i64>, k: usize) -> f64 {
    let relevant = labels
        .values()
        .filter(|grade| **grade >= RELEVANT_GRADE)
        .count();
    if relevant == 0 {
        return 0.0;
    }
    urls.iter()
        .take(k)
        .filter(|url| labels.get(*url).copied().unwrap_or(0) >= RELEVANT_GRADE)
        .count() as f64
        / relevant as f64
}
fn mrr(urls: &[String], labels: &BTreeMap<String, i64>, k: usize) -> f64 {
    urls.iter()
        .take(k)
        .position(|url| labels.get(url).copied().unwrap_or(0) >= RELEVANT_GRADE)
        .map_or(0.0, |i| 1.0 / (i + 1) as f64)
}
fn dcg(grades: impl Iterator<Item = i64>) -> f64 {
    grades
        .enumerate()
        .map(|(index, grade)| ((2_i64.pow(grade as u32) - 1) as f64) / ((index + 2) as f64).log2())
        .sum()
}
fn ndcg(urls: &[String], labels: &BTreeMap<String, i64>, k: usize) -> f64 {
    let mut ideal: Vec<_> = labels.values().copied().collect();
    ideal.sort_by(|a, b| b.cmp(a));
    let maximum = dcg(ideal.into_iter().take(k));
    if maximum == 0.0 {
        0.0
    } else {
        dcg(urls
            .iter()
            .take(k)
            .map(|url| labels.get(url).copied().unwrap_or(0)))
            / maximum
    }
}
fn evaluate(
    case: &Case,
    min_score: i64,
    max_subqueries: i64,
    registry: &Registry,
    year: i32,
) -> CaseResult {
    let plan = planner::plan(&case.query, max_subqueries, None);
    let plan_intents = plan
        .iter()
        .map(|step| step.intent.to_string())
        .collect::<Vec<_>>();
    let mut baseline = case.candidates.clone();
    baseline.sort_by_key(|result| result.rank);
    let baseline_urls = baseline
        .iter()
        .map(|result| result.url.clone())
        .collect::<Vec<_>>();
    let ranked = search::rank(&case.query, case.candidates.clone(), registry, year);
    let top_urls = ranked
        .iter()
        .take(3)
        .map(|result| result.url.clone())
        .collect::<Vec<_>>();
    let top_quality = top_urls
        .first()
        .map_or(0, |url| search::classify(registry, url).1);
    let intent_hits = case
        .expected_plan_intents
        .iter()
        .filter(|intent| plan_intents.contains(intent))
        .count() as i64;
    let preferred_hits = case
        .preferred_url_terms
        .iter()
        .filter(|term| top_urls.iter().any(|url| url.contains(*term)))
        .count() as i64;
    let discouraged = discouraged_above_preferred(case, &top_urls);
    let quality_ok = top_quality >= case.min_top_quality;
    let score = (30.0 * intent_hits as f64 / case.expected_plan_intents.len().max(1) as f64)
        .round_ties_even() as i64
        + (40.0 * preferred_hits as f64 / case.preferred_url_terms.len().max(1) as f64)
            .round_ties_even() as i64
        + if quality_ok { 20 } else { 0 }
        + if !discouraged { 10 } else { 0 };
    let labels = case.relevance.iter().cloned().collect::<BTreeMap<_, _>>();
    let ranked_urls = ranked
        .iter()
        .map(|result| result.url.clone())
        .collect::<Vec<_>>();
    let retrieval = if labels.is_empty() {
        BTreeMap::new()
    } else {
        BTreeMap::from([
            (
                "recall@5".into(),
                rounded(recall(&ranked_urls, &labels, 5), 4),
            ),
            ("mrr@5".into(), rounded(mrr(&ranked_urls, &labels, 5), 4)),
            (
                "ndcg@10".into(),
                rounded(ndcg(&ranked_urls, &labels, 10), 4),
            ),
            (
                "baseline_ndcg@10".into(),
                rounded(ndcg(&baseline_urls, &labels, 10), 4),
            ),
        ])
    };
    CaseResult {
        category: case.category.clone(),
        metrics: BTreeMap::from([
            ("intent_hits".into(), json!(intent_hits)),
            ("preferred_hits".into(), json!(preferred_hits)),
            ("quality_ok".into(), json!(quality_ok)),
            ("discouraged_above_preferred".into(), json!(discouraged)),
        ]),
        name: case.name.clone(),
        passed: score >= min_score,
        plan_intents,
        query: case.query.clone(),
        retrieval,
        score,
        top_urls,
    }
}

pub fn run(min_score: i64, max_subqueries: i64, registry: &Registry) -> Result<Summary> {
    let fixture = fixtures()?;
    let cases = fixture
        .cases
        .iter()
        .map(|case| evaluate(case, min_score, max_subqueries, registry, fixture.year))
        .collect::<Vec<_>>();
    let score = (cases.iter().map(|case| case.score).sum::<i64>() as f64
        / cases.len().max(1) as f64)
        .round_ties_even() as i64;
    let mut groups = BTreeMap::<String, Vec<i64>>::new();
    for case in &cases {
        groups
            .entry(case.category.clone())
            .or_default()
            .push(case.score);
    }
    let category_scores = groups
        .into_iter()
        .map(|(category, scores)| {
            (
                category,
                (scores.iter().sum::<i64>() as f64 / scores.len() as f64).round_ties_even() as i64,
            )
        })
        .collect();
    let labelled = cases
        .iter()
        .filter(|case| !case.retrieval.is_empty())
        .collect::<Vec<_>>();
    let mut retrieval = BTreeMap::new();
    if !labelled.is_empty() {
        for key in ["recall@5", "mrr@5", "ndcg@10", "baseline_ndcg@10"] {
            retrieval.insert(
                key.into(),
                json!(rounded(
                    labelled.iter().map(|case| case.retrieval[key]).sum::<f64>()
                        / labelled.len() as f64,
                    4
                )),
            );
        }
        retrieval.insert("labeled_cases".into(), json!(labelled.len()));
    }
    let ranking_beats = ranking_beats_provider_order(&retrieval);
    let passed = score >= min_score && cases.iter().all(|case| case.passed) && ranking_beats;
    Ok(Summary {
        cases,
        category_scores,
        min_score,
        passed,
        retrieval,
        score,
    })
}

fn ranking_beats_provider_order(retrieval: &BTreeMap<String, Value>) -> bool {
    retrieval
        .get("ndcg@10")
        .zip(retrieval.get("baseline_ndcg@10"))
        .is_none_or(|(ranked, baseline)| ranked.as_f64().unwrap() > baseline.as_f64().unwrap())
}

pub fn report(summary: &Summary) -> String {
    let mut lines = vec![
        "# Research Quality Benchmark".into(),
        String::new(),
        format!("- score: {}", summary.score),
        format!("- min_score: {}", summary.min_score),
        format!("- passed: {}", summary.passed),
        format!("- cases: {}", summary.cases.len()),
        String::new(),
        "## Category Scores".into(),
        String::new(),
    ];
    lines.extend(
        summary
            .category_scores
            .iter()
            .map(|(category, score)| format!("- {category}: {score}")),
    );
    if !summary.retrieval.is_empty() {
        lines.extend([String::new(), "## Retrieval Metrics".into(), String::new()]);
        for key in [
            "labeled_cases",
            "recall@5",
            "mrr@5",
            "ndcg@10",
            "baseline_ndcg@10",
        ] {
            lines.push(format!("- {key}: {}", summary.retrieval[key]));
        }
    }
    lines.extend([String::new(), "## Cases".into(), String::new()]);
    for case in &summary.cases {
        lines.extend([
            format!("### {}", case.name),
            String::new(),
            format!("- category: {}", case.category),
            format!("- query: {}", case.query),
            format!("- score: {}", case.score),
            format!("- passed: {}", case.passed),
            format!("- plan_intents: {}", case.plan_intents.join(", ")),
            format!("- top_urls: {}", case.top_urls.join(", ")),
            format!("- metrics: {}", python_dict(&case.metrics)),
            String::new(),
        ]);
    }
    format!("{}\n", lines.join("\n").trim_end())
}
fn python_dict(metrics: &BTreeMap<String, Value>) -> String {
    let body = [
        "intent_hits",
        "preferred_hits",
        "quality_ok",
        "discouraged_above_preferred",
    ]
    .iter()
    .map(|key| {
        format!(
            "'{}': {}",
            key,
            match &metrics[*key] {
                Value::Bool(value) =>
                    if *value {
                        "True".into()
                    } else {
                        "False".into()
                    },
                value => value.to_string(),
            }
        )
    })
    .collect::<Vec<_>>()
    .join(", ");
    format!("{{{body}}}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quality_gate_rejects_provider_order_ties() {
        let retrieval = BTreeMap::from([
            ("ndcg@10".into(), json!(0.75)),
            ("baseline_ndcg@10".into(), json!(0.75)),
        ]);
        assert!(!ranking_beats_provider_order(&retrieval));
    }

    #[test]
    fn python_slice_and_metric_edges_are_preserved() {
        let labels = BTreeMap::from([("a".into(), 3), ("b".into(), 2), ("c".into(), 0)]);
        assert_eq!(mrr(&["c".into(), "b".into()], &labels, 5), 0.5);
        assert_eq!(recall(&["a".into()], &labels, 1), 0.5);
        assert_eq!(
            ndcg(&["a".into(), "b".into(), "c".into()], &labels, 10),
            1.0
        );
    }
}

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import log2

from .models import SearchResult
from .planner import build_search_plan
from .rank import rank_results
from .source_quality import classify_url

# Fixtures anchor publish dates to the current year so freshness scoring stays
# identical every year instead of decaying as hardcoded years age out.
CURRENT_YEAR = datetime.now(timezone.utc).year

# BEIR grades relevance rather than treating it as a boolean, so a mirror of an official
# page and the official page itself are not scored the same. Anything at or above this is
# counted as a hit by Recall@K and MRR@K; nDCG uses the full grade.
RELEVANT_GRADE = 1


@dataclass(slots=True, frozen=True)
class EvalCase:
    name: str
    category: str
    query: str
    candidates: list[SearchResult]
    expected_plan_intents: tuple[str, ...]
    preferred_url_terms: tuple[str, ...]
    discouraged_url_terms: tuple[str, ...] = ()
    min_top_quality: int = 75
    # url -> graded relevance (0 irrelevant, 3 the primary answer). Kept as a tuple so the
    # case stays frozen. Empty means the case is excluded from the retrieval metrics.
    relevance: tuple[tuple[str, int], ...] = ()


@dataclass(slots=True)
class EvalCaseResult:
    name: str
    category: str
    query: str
    score: int
    passed: bool
    plan_intents: list[str]
    top_urls: list[str]
    metrics: dict[str, int | bool]
    retrieval: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class EvalSummary:
    score: int
    passed: bool
    min_score: int
    cases: list[EvalCaseResult]
    category_scores: dict[str, int]
    retrieval: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "passed": self.passed,
            "min_score": self.min_score,
            "category_scores": self.category_scores,
            "retrieval": self.retrieval,
            "cases": [case.to_dict() for case in self.cases],
        }


def default_eval_cases() -> list[EvalCase]:
    return [
        EvalCase(
            name="agentic_retrieval_prefers_official_and_primary",
            category="platform_api_docs",
            query="agentic retrieval source quality",
            candidates=[
                SearchResult(
                    title="Agentic retrieval: a practical guide",
                    url="https://www.algolia.com/blog/ai/agentic-retrieval",
                    snippet="Agentic retrieval amplifies existing data quality issues.",
                    rank=1,
                ),
                SearchResult(
                    title="Agentic Retrieval Overview - Azure AI Search",
                    url="https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview",
                    snippet="A pipeline that decomposes complex queries into subqueries for agent workflows.",
                    rank=2,
                ),
                SearchResult(
                    title="Agentic retrieval in Azure AI Search",
                    url="https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/search/agentic-retrieval-overview.md",
                    snippet="Primary documentation source for agentic retrieval behavior.",
                    rank=3,
                ),
            ],
            expected_plan_intents=("baseline", "official", "primary"),
            preferred_url_terms=("learn.microsoft.com", "github.com/MicrosoftDocs"),
            discouraged_url_terms=("algolia.com/blog",),
            relevance=(
                ("https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview", 3),
                (
                    "https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/search/agentic-retrieval-overview.md",
                    2,
                ),
                ("https://www.algolia.com/blog/ai/agentic-retrieval", 0),
            ),
        ),
        EvalCase(
            name="citations_prefers_vendor_docs",
            category="ai_vendor_docs",
            query="Claude citations source documents",
            candidates=[
                SearchResult(
                    title="How to add citations to an AI app",
                    url="https://example.com/claude-citations-guide",
                    snippet="A blog tutorial about citations.",
                    rank=1,
                ),
                SearchResult(
                    title="Citations - Anthropic",
                    url="https://docs.anthropic.com/en/docs/build-with-claude/citations",
                    snippet="Citations provide source locations for generated responses.",
                    rank=2,
                ),
            ],
            expected_plan_intents=("baseline", "official"),
            preferred_url_terms=("docs.anthropic.com",),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://docs.anthropic.com/en/docs/build-with-claude/citations", 3),
                ("https://example.com/claude-citations-guide", 0),
            ),
        ),
        EvalCase(
            name="papers_surface_primary_research",
            category="scholarly_research",
            query="query decomposition retrieval augmented generation evaluation",
            candidates=[
                SearchResult(
                    title="Query decomposition for RAG",
                    url="https://arxiv.org/abs/2510.18633",
                    snippet="Retrieval-augmented generation systems decompose requests into subqueries.",
                    rank=2,
                    published_at=f"{CURRENT_YEAR - 1}-10-22",
                ),
                SearchResult(
                    title="Advanced RAG production patterns",
                    url="https://example.com/advanced-rag-patterns",
                    snippet="A high-level production guide.",
                    rank=1,
                ),
                SearchResult(
                    title="Question Decomposition for Retrieval-Augmented Generation",
                    url="https://aclanthology.org/2025.acl-srw.32/",
                    snippet="A RAG pipeline that incorporates question decomposition and reranking.",
                    rank=3,
                    published_at=f"{CURRENT_YEAR - 1}-07-01",
                ),
            ],
            expected_plan_intents=("baseline", "primary", "critique"),
            preferred_url_terms=("arxiv.org", "aclanthology.org"),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://arxiv.org/abs/2510.18633", 3),
                ("https://aclanthology.org/2025.acl-srw.32/", 2),
                ("https://example.com/advanced-rag-patterns", 0),
            ),
        ),
        EvalCase(
            name="fusion_consensus_beats_single_engine_outlier",
            category="metasearch_fusion",
            query="agent search documentation rank fusion",
            candidates=[
                SearchResult(
                    title="Generic search notes",
                    url="https://example.com/rank-fusion",
                    snippet="A single-engine blog result.",
                    rank=1,
                ),
                SearchResult(
                    title="Agent search rank fusion documentation",
                    url="https://docs.github.com/en/search-github",
                    snippet="Official documentation for searching GitHub.",
                    rank=2,
                    metadata={"rrf_score": 0.031, "source_count": 2},
                ),
            ],
            expected_plan_intents=("baseline", "official", "primary"),
            preferred_url_terms=("docs.github.com",),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://docs.github.com/en/search-github", 3),
                ("https://example.com/rank-fusion", 0),
            ),
        ),
        EvalCase(
            name="feed_monitoring_prefers_official_release_notes",
            category="feed_monitoring",
            query="Python release feed security notes",
            candidates=[
                SearchResult(
                    title="Python release rumors",
                    url="https://example.com/python-release-rumors",
                    snippet="A commentary post about Python releases and security notes.",
                    rank=1,
                ),
                SearchResult(
                    title="What is New In Python",
                    url="https://docs.python.org/3/whatsnew/3.14.html",
                    snippet="Official release notes and changed behavior for Python.",
                    rank=2,
                    published_at=f"{CURRENT_YEAR}-05-01",
                ),
            ],
            expected_plan_intents=("baseline", "official", "primary"),
            preferred_url_terms=("docs.python.org",),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://docs.python.org/3/whatsnew/3.14.html", 3),
                ("https://example.com/python-release-rumors", 0),
            ),
            min_top_quality=70,
        ),
        EvalCase(
            name="security_prefers_primary_advisory",
            category="security_advisory",
            query="Node.js OpenSSL vulnerability advisory",
            candidates=[
                SearchResult(
                    title="Node OpenSSL vulnerability analysis",
                    url="https://example.com/node-openssl-analysis",
                    snippet="A secondary article about a Node.js vulnerability.",
                    rank=1,
                ),
                SearchResult(
                    title="Node.js security advisory",
                    url="https://github.com/nodejs/node/security/advisories/GHSA-node-openssl",
                    snippet="Primary security advisory for Node.js and OpenSSL.",
                    source="github",
                    rank=2,
                    published_at=f"{CURRENT_YEAR}-04-10",
                ),
                SearchResult(
                    title="NVD CVE detail",
                    url="https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
                    snippet="Government vulnerability database entry.",
                    rank=3,
                ),
            ],
            expected_plan_intents=("baseline", "primary", "critique"),
            preferred_url_terms=("github.com/nodejs", "nvd.nist.gov"),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://github.com/nodejs/node/security/advisories/GHSA-node-openssl", 3),
                ("https://nvd.nist.gov/vuln/detail/CVE-2026-0001", 2),
                ("https://example.com/node-openssl-analysis", 0),
            ),
            min_top_quality=75,
        ),
        EvalCase(
            name="regulatory_prefers_government_source",
            category="legal_regulatory",
            query="FTC endorsements disclosure business guidance",
            candidates=[
                SearchResult(
                    title="Influencer disclosure tips",
                    url="https://example.com/influencer-disclosure-tips",
                    snippet="Marketing blog summary of endorsement rules.",
                    rank=1,
                ),
                SearchResult(
                    title="FTC Endorsement Guides",
                    url="https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides",
                    snippet="Government business guidance for endorsements and disclosures.",
                    rank=2,
                ),
            ],
            expected_plan_intents=("baseline", "official", "critique"),
            preferred_url_terms=("ftc.gov",),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides", 3),
                ("https://example.com/influencer-disclosure-tips", 0),
            ),
            min_top_quality=75,
        ),
        EvalCase(
            name="open_source_prefers_primary_implementation",
            category="open_source_code",
            query="SearXNG engine adapter implementation",
            candidates=[
                SearchResult(
                    title="Metasearch adapter blog",
                    url="https://example.com/metasearch-adapter",
                    snippet="A general article about search adapters.",
                    rank=1,
                ),
                SearchResult(
                    title="SearXNG engines source",
                    url="https://github.com/searxng/searxng/tree/master/searx/engines",
                    snippet="Primary implementation of SearXNG engine adapters.",
                    source="github",
                    rank=2,
                ),
                SearchResult(
                    title="SearXNG engine docs",
                    url="https://docs.searxng.org/dev/engines/index.html",
                    snippet="Developer documentation for SearXNG engines.",
                    rank=3,
                ),
            ],
            expected_plan_intents=("baseline", "official", "primary"),
            preferred_url_terms=("github.com/searxng", "docs.searxng.org"),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://github.com/searxng/searxng/tree/master/searx/engines", 3),
                ("https://docs.searxng.org/dev/engines/index.html", 2),
                ("https://example.com/metasearch-adapter", 0),
            ),
        ),
        EvalCase(
            name="product_release_prefers_official_changelog",
            category="product_release_freshness",
            query="OpenAI Agents SDK changelog release notes",
            candidates=[
                SearchResult(
                    title="Agents SDK release recap",
                    url="https://example.com/agents-sdk-release-recap",
                    snippet="An unofficial recap of release notes.",
                    rank=1,
                ),
                SearchResult(
                    title="OpenAI Agents SDK docs",
                    url="https://developers.openai.com/tracks/building-agents",
                    snippet="Official OpenAI developer documentation for building agents.",
                    rank=2,
                    published_at=f"{CURRENT_YEAR}-05-01",
                ),
                SearchResult(
                    title="OpenAI Agents Python releases",
                    url="https://github.com/openai/openai-agents-python/releases",
                    snippet="Primary release history for the OpenAI Agents Python SDK.",
                    source="github",
                    rank=3,
                    published_at=f"{CURRENT_YEAR}-05-20",
                ),
            ],
            expected_plan_intents=("baseline", "official", "primary"),
            preferred_url_terms=("developers.openai.com", "github.com/openai"),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://github.com/openai/openai-agents-python/releases", 3),
                ("https://developers.openai.com/tracks/building-agents", 2),
                ("https://example.com/agents-sdk-release-recap", 0),
            ),
        ),
        EvalCase(
            name="news_bias_prefers_bias_comparison_source",
            category="bias_aware_news",
            query="news coverage political bias comparison",
            candidates=[
                SearchResult(
                    title="Political bias in the news",
                    url="https://example.com/political-bias-news",
                    snippet="A single-site commentary article about media bias.",
                    rank=1,
                ),
                SearchResult(
                    title="Ground News bias comparison",
                    url="https://ground.news/",
                    snippet="Compare news coverage by source mix and political bias.",
                    rank=2,
                    published_at=f"{CURRENT_YEAR}-05-01",
                ),
                SearchResult(
                    title="AllSides media bias ratings",
                    url="https://www.allsides.com/media-bias/media-bias-ratings",
                    snippet="Media bias ratings across news sources.",
                    rank=3,
                ),
            ],
            expected_plan_intents=("baseline", "official", "critique"),
            preferred_url_terms=("ground.news", "allsides.com"),
            discouraged_url_terms=("example.com",),
            relevance=(
                ("https://ground.news/", 3),
                ("https://www.allsides.com/media-bias/media-bias-ratings", 2),
                ("https://example.com/political-bias-news", 0),
            ),
            min_top_quality=75,
        ),
    ]


def recall_at_k(ranked_urls: list[str], labels: dict[str, int], k: int) -> float:
    relevant = {url for url, grade in labels.items() if grade >= RELEVANT_GRADE}
    if not relevant:
        return 0.0
    return sum(1 for url in ranked_urls[:k] if url in relevant) / len(relevant)


def mrr_at_k(ranked_urls: list[str], labels: dict[str, int], k: int) -> float:
    for position, url in enumerate(ranked_urls[:k], start=1):
        if labels.get(url, 0) >= RELEVANT_GRADE:
            return 1.0 / position
    return 0.0


def ndcg_at_k(ranked_urls: list[str], labels: dict[str, int], k: int) -> float:
    ideal = _dcg(sorted(labels.values(), reverse=True)[:k])
    if not ideal:
        return 0.0
    return _dcg([labels.get(url, 0) for url in ranked_urls[:k]]) / ideal


def _dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / log2(position + 1) for position, grade in enumerate(grades, start=1))


def run_eval(*, min_score: int = 80, max_subqueries: int = 4) -> EvalSummary:
    results = [
        evaluate_case(case, max_subqueries=max_subqueries, min_score=min_score)
        for case in default_eval_cases()
    ]
    score = round(sum(result.score for result in results) / max(len(results), 1))
    category_scores = _category_scores(results)
    retrieval = _retrieval_summary(results)
    # The gate is the gap, not a tuned constant: ranking has to beat the order the
    # providers already handed us, or it is doing nothing worth its latency.
    ranking_beats_providers = (
        not retrieval or retrieval["ndcg@10"] > retrieval["baseline_ndcg@10"]
    )
    return EvalSummary(
        score=score,
        passed=(
            score >= min_score
            and all(case.passed for case in results)
            and ranking_beats_providers
        ),
        min_score=min_score,
        cases=results,
        category_scores=category_scores,
        retrieval=retrieval,
    )


def evaluate_case(case: EvalCase, *, max_subqueries: int = 4, min_score: int = 80) -> EvalCaseResult:
    plan = build_search_plan(case.query, max_subqueries=max_subqueries)
    # rank_results mutates the candidates it is given, so the provider baseline has to be
    # read off before it runs.
    baseline_urls = [result.url for result in sorted(case.candidates, key=lambda r: r.rank)]
    ranked = rank_results(case.query, list(case.candidates))
    top_urls = [result.url for result in ranked[:3]]
    top_quality = classify_url(top_urls[0])[1] if top_urls else 0

    plan_intents = [step.intent for step in plan]
    intent_hits = sum(1 for intent in case.expected_plan_intents if intent in plan_intents)
    preferred_hits = sum(1 for term in case.preferred_url_terms if any(term in url for url in top_urls))
    discouraged_above_preferred = _discouraged_above_preferred(case, top_urls)
    quality_ok = top_quality >= case.min_top_quality

    score = 0
    score += round(30 * intent_hits / max(len(case.expected_plan_intents), 1))
    score += round(40 * preferred_hits / max(len(case.preferred_url_terms), 1))
    score += 20 if quality_ok else 0
    score += 10 if not discouraged_above_preferred else 0

    return EvalCaseResult(
        name=case.name,
        category=case.category,
        query=case.query,
        score=score,
        passed=score >= min_score,
        plan_intents=plan_intents,
        top_urls=top_urls,
        metrics={
            "intent_hits": intent_hits,
            "preferred_hits": preferred_hits,
            "quality_ok": quality_ok,
            "discouraged_above_preferred": discouraged_above_preferred,
        },
        retrieval=_retrieval_metrics(
            [result.url for result in ranked], baseline_urls, dict(case.relevance)
        ),
    )


def _retrieval_metrics(
    ranked_urls: list[str], baseline_urls: list[str], labels: dict[str, int]
) -> dict[str, float]:
    if not labels:
        return {}
    return {
        "recall@5": round(recall_at_k(ranked_urls, labels, 5), 4),
        "mrr@5": round(mrr_at_k(ranked_urls, labels, 5), 4),
        "ndcg@10": round(ndcg_at_k(ranked_urls, labels, 10), 4),
        "baseline_ndcg@10": round(ndcg_at_k(baseline_urls, labels, 10), 4),
    }


def _retrieval_summary(results: list[EvalCaseResult]) -> dict[str, float]:
    labeled = [result for result in results if result.retrieval]
    if not labeled:
        return {}
    summary = {
        key: round(sum(result.retrieval[key] for result in labeled) / len(labeled), 4)
        for key in ("recall@5", "mrr@5", "ndcg@10", "baseline_ndcg@10")
    }
    summary["labeled_cases"] = len(labeled)
    return summary


def build_eval_report(summary: EvalSummary) -> str:
    lines = [
        "# Research Quality Benchmark",
        "",
        f"- score: {summary.score}",
        f"- min_score: {summary.min_score}",
        f"- passed: {str(summary.passed).lower()}",
        f"- cases: {len(summary.cases)}",
        "",
        "## Category Scores",
        "",
    ]
    for category, score in sorted(summary.category_scores.items()):
        lines.append(f"- {category}: {score}")
    if summary.retrieval:
        lines.extend(["", "## Retrieval Metrics", ""])
        for key in ("labeled_cases", "recall@5", "mrr@5", "ndcg@10", "baseline_ndcg@10"):
            lines.append(f"- {key}: {summary.retrieval[key]}")
    lines.extend(
        [
            "",
            "## Cases",
            "",
        ]
    )
    for case in summary.cases:
        lines.extend(
            [
                f"### {case.name}",
                "",
                f"- category: {case.category}",
                f"- query: {case.query}",
                f"- score: {case.score}",
                f"- passed: {str(case.passed).lower()}",
                f"- plan_intents: {', '.join(case.plan_intents)}",
                f"- top_urls: {', '.join(case.top_urls)}",
                f"- metrics: {case.metrics}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _discouraged_above_preferred(case: EvalCase, top_urls: list[str]) -> bool:
    first_preferred = _first_index(top_urls, case.preferred_url_terms)
    first_discouraged = _first_index(top_urls, case.discouraged_url_terms)
    return first_discouraged is not None and (first_preferred is None or first_discouraged < first_preferred)


def _first_index(urls: list[str], terms: tuple[str, ...]) -> int | None:
    for idx, url in enumerate(urls):
        if any(term in url for term in terms):
            return idx
    return None


def _category_scores(results: list[EvalCaseResult]) -> dict[str, int]:
    grouped: dict[str, list[int]] = {}
    for result in results:
        grouped.setdefault(result.category, []).append(result.score)
    return {category: round(sum(scores) / len(scores)) for category, scores in grouped.items()}

# RL And Evaluation Roadmap

This repository should not jump directly to online reinforcement learning. Research workflows can overfit to noisy rewards such as clickability, SEO-heavy pages, or verbose reports. The safe progression is:

1. deterministic offline evaluation
2. structured action logs
3. learning-to-rank on fixed judgments
4. contextual bandits for provider and read-top selection
5. preference learning or offline RL only after enough reviewed traces exist

## Action Surface

The learnable policy can eventually choose:

- query plan shape
- provider selection
- candidate reranking
- read-top selection
- stopping point
- token allocation

The current implementation keeps these actions explicit through:

- `kwr plan`
- `kwr brief --expand-queries`
- `kwr investigate --expand-queries`
- `kwr eval`
- `scripts/benchmark-token-budget.py`
- `scripts/benchmark-research-quality.py`

## Katala Search Engine Adaptation

The search engine borrows Katala Match's pipeline discipline:

- Gate: reject unusable candidates early, including empty URLs and retracted scholarly works.
- Scorer: combine fit, source quality, freshness, and risk penalties into an inspectable score.
- Selector: apply host and source-type diversity caps before final Top-K output.
- SideEffect: record benchmark reports instead of silently changing runtime state.

This mirrors Katala Match's `Source -> Hydrator -> Gate -> Scorer -> Selector -> SideEffect` shape without importing the private workspace package.

## SearXNG-Inspired Engine Boundary

SearXNG's public source and docs show a broad engine catalog, engine result normalization, and settings-driven engine selection. `katala-web-research` keeps the same extensibility boundary in a smaller form:

- each provider is a replaceable engine adapter
- `meta` fans out across configured engines
- every engine returns `SearchResult`
- ranking and diversity are centralized after normalization
- `.env`/1Password references configure optional engines without committing secrets

This keeps the project MIT-compatible while still applying SearXNG's metasearch architecture.

## Reward Signals

Use a composite reward. Do not reward raw clicks or result count alone.

Recommended positive signals:

- official or primary source coverage
- expected good URL in top results
- citation/capture availability
- local corpus agreement
- contradiction discovery
- freshness when the task is time-sensitive

Recommended penalties:

- discouraged source above preferred source
- missing official or primary source
- token budget overrun
- excessive page capture
- duplicate URLs
- stale pages for current API or product questions

## Current Offline Benchmark

`kwr eval` runs fixed cases with known preferred and discouraged sources. It scores:

- query-plan intent coverage
- preferred URL terms in top candidates
- top source-quality band
- discouraged source ordering

The deterministic suite now covers these domain categories:

- platform API docs
- AI vendor docs
- scholarly research
- metasearch fusion
- bias-aware news comparison
- feed monitoring
- security advisories
- legal/regulatory guidance
- open-source implementation research
- product release freshness

This is intentionally small and deterministic. It is a regression gate, not a full relevance benchmark.

## Relevance Labels And Retrieval Metrics

Every case also carries graded relevance labels (`EvalCase.relevance`, url to grade 0-3) over the same candidates, so BEIR-style metrics can be read off the existing fixtures instead of a second corpus:

- `recall@5` - labelled relevant documents that survive ranking
- `mrr@5` - reciprocal rank of the first relevant document
- `ndcg@10` - graded, position-weighted quality, exponential gain
- `baseline_ndcg@10` - the same nDCG over the order the providers returned

`kwr eval` fails when `ndcg@10` is not strictly above `baseline_ndcg@10`. The gate is the gap rather than a tuned threshold: a fixed number drifts into either a rubber stamp or a chore, while the gap goes red the moment ranking stops improving on provider order.

Benchmark boundary:

- **In CI (always run):** the labelled fixture subset above. No network, no downloads, deterministic.
- **Skipped (external, opt-in):** real BEIR/MTEB corpora such as NFCorpus or SciFact. They need multi-hundred-MB downloads and an embedding model, which contradicts the no-mandatory-service rule that the provider boundary is built on. Run them out of band when a retrieval model is actually being adopted, and record the numbers in a dated note under `docs/`; do not wire them into `make verify`.

## Next Learning Step

The next practical learning feature is a simple learning-to-rank dataset:

```json
{
  "query": "agentic retrieval source quality",
  "url": "https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview",
  "features": {
    "source_quality": 100,
    "query_overlap": 3,
    "is_primary": true,
    "is_fresh": false
  },
  "label": 1
}
```

A contextual bandit should come after this, using `kwr eval` and human-reviewed reports as offline validation before any automatic online adaptation.

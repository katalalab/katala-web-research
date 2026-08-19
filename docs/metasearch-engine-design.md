# Katala Metasearch Engine Design

This project does not vendor or fork SearXNG. SearXNG is AGPL-3.0, broad, and operationally useful as a self-hosted metasearch service. `katala-web-research` stays MIT-compatible by adopting the architectural boundary rather than copying implementation code.

## SearXNG Reference Points

- source: https://github.com/searxng/searxng
- engine docs: https://docs.searxng.org/dev/engines/index.html
- settings docs: https://docs.searxng.org/admin/settings/index.html

Useful patterns:

- many small engine adapters
- settings-driven engine selection
- normalized result objects
- per-engine failure isolation
- privacy-respecting self-host option
- categories and result types

## Katala Adaptation

The local design adds Katala-style decision discipline after metasearch retrieval:

```text
Source engines -> Normalize -> Gate -> Scorer -> Selector -> Report / Archive
```

Mapping:

- Source engines: `ddg`, `feed`, `github`, `openalex`, `searxng`, optional `brave` and `jina`
- Normalize: all engines return `SearchResult`
- Gate: drop unusable URLs and retracted scholarly candidates
- Scorer: source quality, query fit, freshness, primary-source bonus, provider boost
- Selector: host and source-type diversity caps
- SideEffect: archive captures and benchmark reports

## Why This Can Beat A Plain SearXNG Instance

SearXNG is strong at broad fan-out. The Katala layer adds research-specific judgment:

- OpenAlex is useful for scholarly candidates but can drift on broad terms; the selector prevents it from dominating.
- GitHub is useful for implementation evidence but can overfit to repositories; source-type caps reduce that.
- DDG/SearXNG are useful web coverage engines; source-quality scoring keeps generic articles below official and primary sources.
- Local repo evidence gives prior-art comparison that public metasearch engines cannot see.

## Current Engine

`kwr search --provider meta` fans out over `KWR_META_PROFILE` or explicit `KWR_META_PROVIDERS`.

Example:

```sh
KWR_META_PROVIDERS=ddg,github,openalex \
op run --env-file=.env -- kwr search "research agent evaluation metrics" --provider meta --limit 8
```

The default profile is `broad`:

```text
ddg,github,openalex,searxng
```

Available profiles:

- `broad`: default web, code, scholarly, and SearXNG mix
- `docs`: official/vendor documentation bias
- `scholarly`: OpenAlex-first paper discovery
- `code`: GitHub-first implementation discovery
- `fresh`: current web/news-like discovery
- `local`: feed archive plus low-dependency DDG/GitHub path
- `monitoring`: feed archive first, then low-dependency DDG/GitHub path

Engines that lack credentials or URLs fail closed and do not block the whole search.

Before final Katala scoring, `meta` applies health-aware Reciprocal Rank Fusion so a URL seen by multiple healthy engines gets a consensus boost without trusting incompatible engine score scales. Each result carries `meta_engine_runs` metadata with provider status, latency, result count, bounded health score, and error kind for failed engines.

## Engine Health Ledger

Per-search health only describes the search that just happened, so it cannot tell a bad afternoon from a dead engine. When the caller names an archive (`--archive`, exported as `KWR_ARCHIVE`; every CLI command that owns an archive does this), `meta` appends each engine run to the `engine_runs` table and reads the accumulated record back on the next search:

- failure rate, useful-result rate, and nearest-rank p95 latency per engine, over a rolling window of the last 50 runs
- `kwr engines [--archive PATH] [--window N] [--json]` prints the ledger and marks the engines currently routed around
- an engine is demoted only after at least 5 recorded runs, and only for a failure rate above 0.5, a p95 above 5s, or a useful-result rate below 0.2
- if every engine in the profile is weak, none is dropped: a fleet-wide outage has to read as "everything is failing", not as "no results"

Without an archive the ledger is off entirely, so importing the library never creates a database in the working directory.

## Next Engine Improvements

- Optional Firecrawl-inspired enrichment pass: fetch top search candidates with the configured reader, merge page text into thin snippets, keep read failures in metadata, and re-rank. Implemented as `kwr search --enrich-top N --reader auto|jina|direct`.
- Firecrawl-inspired query filters: `kwr search --category github|research|pdf --include-domain DOMAIN --exclude-domain DOMAIN` rewrites the provider query using `site:` and `filetype:pdf` operators and annotates matched categories in result metadata.
- Archive-backed highlights: `kwr search --highlight-top N` mirrors Firecrawl's index-backed highlight shape with local SQLite pages instead of remote index/GCS/model dependencies.
- Candidate buffering: search commands default to fetching `limit * 2` candidates before final trimming so diversity and source-quality scoring have enough material to work with. Tune with `--candidate-multiplier`.
- SearXNG pagination: large limits fetch enough SearXNG result pages before Katala ranking trims the candidate set.
- SearXNG-compatible env validation: `KWR_SEARXNG_TIME_RANGE` and `KWR_SEARXNG_SAFESEARCH` are checked locally before the provider sends a request.
- Provider rank retention: final ranking overwrites `rank`, but the original provider position remains available as `metadata.provider_rank`.
- Local repo FTS uses weighted BM25 fields so repo name, path, title, and deterministic context can outrank body-only matches.
- Host/source quotas exposed as config
- Optional local SearXNG instance bootstrap, kept outside the MIT code path

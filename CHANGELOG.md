# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- `kwr read`, `kwr.read` and the page fetches in `kwr.investigate` now refuse URLs that resolve to a
  non-public address (loopback, private, link-local and cloud metadata ranges, including IPv4 wrapped in
  IPv6). The check runs on the connection itself, so DNS rebinding and redirects are covered, and a
  private URL is never forwarded to r.jina.ai. These fetches also ignore proxy environment variables
  and cap the body at 8 MiB. Provider calls (for example `KWR_SEARXNG_URL`) are unchanged.

### Added
- ruff + mypy linting config in `pyproject.toml` (advisory mypy, blocking ruff).
- CI Python matrix expanded to 3.11 and 3.12.
- Fixture-based DDG HTML parser regression test (`tests/fixtures/sample.duckduckgo.html`).
- `.env` secret-pattern guard in `scripts/verify.sh` (rejects `sk-`, `ghp_`, `AKIA`, private key headers).
- PyPI classifiers and `[project.optional-dependencies]` groups in `pyproject.toml`.
- `CHANGELOG.md` (this file).
- HTML `<meta charset>` sniffing in the direct reader so CJK pages decode correctly when the
  `Content-Type` header omits a charset.
- Korean Hangul range in query tokenization (`TOKEN_RE`) so Korean queries produce tokens.
- `year` parameter threaded through `search_with_plan` to reach the freshness sub-query.
- Shared `registry_lines()` in `source_registry` (de-duplicates the helper previously copied into
  `brief.py` and `investigation.py`).

### Changed
- Repo-archive multi-term queries now require **all** terms (FTS5 implicit AND) instead of any term
  (OR), trading recall for precision.
- `source_quality` overlap and title bonus use token-set intersection instead of substring matching,
  fixing false positives such as "on" matching "optimization".
- `_freshness_bonus` no longer rewards future-dated results; only the current year earns the full bonus.
- Eval `preferred_hits` scans the same top-3 window as the discouraged-source check, removing a
  scoring asymmetry.
- RRF engine-health bookkeeping keeps the maximum observed health per source.
- `search_with_plan` with an empty expansion plan falls back to a direct search instead of returning
  no results.

### Fixed
- Removed unused `quote_plus` import from `providers.py` (ruff F401).
- Corpus re-indexing no longer lets unchanged files consume the `max_files` budget, so newly added
  files are not silently skipped.
- `classify_file` tags `CLAUDE.md`/`GEMINI.md` as `agent-context` (previously `docs`).
- DuckDuckGo snippet parser no longer truncates snippets that contain nested links.
- Provider JSON parsing wraps non-JSON responses (e.g. WAF/error HTML) as `FetchError` naming the URL.
- MCP server skips malformed stdin frames instead of crashing the long-lived process.

## [0.1.0] - 2026-05-27

### Added
- Local-first research toolkit: `kwr search`, `kwr read`, `kwr collect`, `kwr brief`,
  `kwr investigate`, `kwr query`, `kwr archive`, `kwr plan`, `kwr eval`, `kwr sources`,
  `kwr feeds`, `kwr doctor` commands.
- SQLite FTS5 archive for search results and page snapshots.
- Multi-provider search: DuckDuckGo HTML, SearXNG, Brave Search API, OpenAlex,
  GitHub Code Search, Jina AI reader, local feed archive.
- Metasearch engine layer with Reciprocal Rank Fusion and per-provider health scoring.
- Query-profile rewriting (`scholarly`, `broad`, `code`, `docs`, `fresh`).
- Research quality evaluation harness (`kwr eval`, `scripts/benchmark-research-quality.py`).
- Token-budget benchmark (`scripts/benchmark-token-budget.py`).
- Source quality registry with 60+ trusted domains across 12 categories.
- RSS/Atom/JSON Feed ingestion pipeline (`kwr feeds add`, `kwr feeds refresh`).
- Feed evidence integration in research briefs and investigation reports.
- MCP server interface for agent integration.
- `scripts/verify.sh` end-to-end verification script covering compile, unit tests,
  CLI smoke tests, and tracked-artifact guard.
- GitHub Actions CI workflow.
- Contribution guide, PR template, and issue templates.

[Unreleased]: https://github.com/Nicolas0315/katala-web-research/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Nicolas0315/katala-web-research/releases/tag/v0.1.0

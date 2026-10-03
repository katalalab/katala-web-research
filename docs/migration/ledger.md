# Rust migration ledger

Baseline main: `e66e449cc210bd80ecb25a00391091e72abd9c2b`. Scope: public Katala repository only. Research proposals are reserved for separate commits after parity comparison. No performance claim or live provider benchmark.

## Slice 1: native local retrieval and copy migration

Implemented: plan; source registry list/match with overlay; four archive query surfaces; feed registration; engine health summaries; existing cached-page reads; copy-only schema migration with version/fingerprint/FTS validation. Runtime code has no Python subprocess or interpreter dependency. Bundled SQLite removes reliance on system FTS5 availability. Toolchain/MSRV 1.96.0 and Cargo.lock are committed.

The complete reference inventory is in `python-contract.json` (22 leaf commands, 41 SQLite objects, 7 MCP schemas), backed by `scripts/migration/inventory.py`. The reference's source files have not been changed. Golden fixtures record deterministic Python outputs with the exact baseline SHA; the differential harness uses synthetic archives and clears provider/registry environment values before testing.

Local evidence (2026-10-03, aarch64 macOS only):

- Python reference: 167 unit tests pass. Existing ResourceWarning about an unclosed Python test database is present.
- Rust: 9 migration tests plus one golden test containing 8 CLI cases pass.
- CLI differential: 133 comparisons pass (plan, registry boundaries/overlay, query JSON/text, repo filters, Unicode paths/content, health windows, cache hit, feed upsert, parser/runtime exits, source-preserving migration and Python reopen).
- Formatting and clippy with warnings denied pass on pinned toolchain.
- Existing `scripts/verify.sh` passes (167 unit tests, CLI/benchmark/artifact gates; configured gitleaks found no leaks). Pinned `--release --locked --offline` build passes; local native binary reports kwr 0.1.0.
- Recording/build workspace size was below 2 GiB throughout the slice. No cross-host operations, real archive/credential reads, paid API/model calls, or live providers.

## Remaining migration work

Pending native surfaces: search and all nine providers (including local feed search transformation); read network/Jina/direct/refresh/cache miss; openalex expand; collect; feed refresh RSS/Atom/JSONFeed; repos scan including encoding/incremental context; issues ingest/report; brief/investigate; doctor; deterministic eval; seven-tool MCP server.

Pending gates: complete golden/differential provider/ranking/Markdown/evaluation tests; TLS/charset/URL redaction and proxy fixtures; provider-specific fallback/pagination/secret-ref timeout; at-most-four meta concurrency and health ledger pruning; signals/broken-pipe semantics beyond simple CLI handling; hard-kill/power-loss migration recovery; additional known legacy schema variants; Windows/Linux execution; notices packaging and release target validation. All live providers are unverified. The Rust preview must not be described as a full migration or replace the user's common CLI until these gates pass.

## Review/publication boundary

Push/draft PR is authorized. Existing standard GitHub-hosted public-repo workflows and main ruleset were read: four required checks (lint, no-instance-data, Python 3.11/3.12 verification), PR required, forcepush/deletion forbidden, no bypass actors. Workflows/runner matrix remain unchanged. Parent provides independent review; no self-approval or merge before exact-head checks and review. Source archive, installed CLI, main, and repository visibility remain unchanged by this slice.

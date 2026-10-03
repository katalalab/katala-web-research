# Rust migration ledger

Baseline main: `e66e449cc210bd80ecb25a00391091e72abd9c2b`. Scope: public Katala repository only. Research proposals are reserved for separate commits after parity comparison. No performance claim or live provider benchmark.

## Slice 1: native local retrieval and copy migration

Implemented: plan; source registry list/match with overlay; four archive query surfaces; feed registration; engine health summaries; existing cached-page reads; copy-only schema migration with version/fingerprint/FTS validation. Runtime code has no Python subprocess or interpreter dependency. Bundled SQLite removes reliance on system FTS5 availability. Toolchain/MSRV 1.96.0 and Cargo.lock are committed.

The complete reference inventory is in `python-contract.json` (22 leaf commands, 41 SQLite objects, 7 MCP schemas), backed by `scripts/migration/inventory.py`. The reference's source files have not been changed. Golden fixtures record deterministic Python outputs with the exact baseline SHA; the differential harness uses synthetic archives and clears provider/registry environment values before testing.

Local evidence (2026-10-03, aarch64 macOS only):

- Python reference: 167 unit tests pass. Existing ResourceWarning about an unclosed Python test database is present.
- Rust: 14 migration tests plus one golden test containing 12 CLI cases pass.
- CLI differential: 139 comparisons pass (plan, registry boundaries/overlay, query JSON/text, repo filters, Unicode paths/content, health windows, cache hit, feed upsert, parser/runtime exits, source-preserving migration and Python reopen).
- Formatting and clippy with warnings denied pass on pinned toolchain.
- Existing `scripts/verify.sh` passes (167 unit tests, CLI/benchmark/artifact gates; configured gitleaks found no leaks). Pinned `--release --locked --offline` build passes; local native binary reports kwr 0.1.0.
- Recording/build workspace size was below 2 GiB throughout the slice. No cross-host operations, real archive/credential reads, paid API/model calls, or live providers.

## Remaining migration work

Pending native surfaces: eight network search providers and positive enrichment; read network/Jina/direct/refresh/cache miss; openalex expand; collect; HTTP feed refresh and remaining parser edges; repos scan including encoding/incremental context; issues ingest/report; brief/investigate; doctor; deterministic eval; seven-tool MCP server.

Pending gates: complete golden/differential provider/ranking/Markdown/evaluation tests; TLS/charset/URL redaction and proxy fixtures; provider-specific fallback/pagination/secret-ref timeout; at-most-four meta concurrency and health ledger pruning; signals/broken-pipe semantics beyond simple CLI handling; hard-kill/power-loss migration recovery; additional known legacy schema variants; Windows/Linux execution; notices packaging and release target validation. All live providers are unverified. The Rust preview must not be described as a full migration or replace the user's common CLI until these gates pass.

## Review/publication boundary

Push/draft PR is authorized. Existing standard GitHub-hosted public-repo workflows and main ruleset were read: four required checks (lint, no-instance-data, Python 3.11/3.12 verification), PR required, forcepush/deletion forbidden, no bypass actors. Workflows/runner matrix remain unchanged. Parent provides independent review; no self-approval or merge before exact-head checks and review. Source archive, installed CLI, and repository visibility are unchanged; authorized preview integration is recorded below.

## Independent review repair (slice 1)

The review of `14d6ae68e5f9bb871b164e3aad44f12a939137d2` requested three corrections. That head's four required CI checks and SAST completed successfully, but merge remained blocked for review.

- P1: destination SQLite namespace includes body, `-wal`, `-shm`, `-journal`, including dangling symlinks. Refuse occupied entries without deleting them, check again immediately before no-clobber publication, and fail preserving files if a sidecar appears during publication. Synthetic real WAL/SHM and rollback journal, individual sidecars, dangling links, and pre-publication injection are regression tests. Source/destination-sidecar bytes remain untouched on rejection.
- P2: engine health now rounds the original binary value to decimal precision without first multiplying. Eight successful 10 ms runs with one useful result match Python's `0.6937`.
- P2: registry matching strips ASCII tab/newlines and leading C0/space like urllib, and handles semicolon params on the final path segment while preserving explicit ports and dot segments. Differential and committed golden fixtures cover the reported CISA cases.

Concurrent uncooperative writers cannot be excluded by a namespace check alone; choose an unused destination in a quiescent directory. A late-race error preserves all files and requires operator inspection, rather than deleting a possibly owned archive or sidecar. No real archive, CLI cutover, main merge, or next-slice feature is included in this repair.

The follow-up review found that a scheme-less URL with a leading space was over-matched. Scheme detection now uses urllib's cleaned view, while fallback `https://` completion uses the original string before the final parse cleanup. The reported leading-space CISA input is a committed unmatched golden and differential case. This is a separate compatibility-only repair commit.

## Slice 2: offline feed vertical slice (published draft checkpoint)

Base: slice-1 review head `414d0ffce7b454d04dd733a317b968852493cc31`. Separate `codex/rust-feed-parity` worktree; this feature diff is not in PR #18. Native RSS/Atom/JSONFeed normal-field parsing, local file feed refresh, source health updates, atomic item batch upsert, and stored-feed search are implemented. Search retains the Python lexical quality scoring, source/host diversity, duplicate/retraction gates, query filters, candidate multiplier and two CLI slices (including negative limits), category metadata and cached archive highlights. No new research algorithm or speed claim.

Reference-derived fixtures cover namespace/CDATA/GUID/Atom IDs, relative Unicode/port-preserving URLs, semicolon params, DuckDuckGo normalization, RFC/ISO dates including naive `-0000`, HTML skip behavior and entity decoding, ranking ties/precision, filters and highlights. The fixture generator uses the Python reference and a fixed year for ranking. Parser DTD/entity declarations remain rejected; malformed non-string JSON values, less common dates, ill-formed HTML/file URI and injected database errors remain parity work. This is not full feed-network or complete CLI migration.

Local gates (2026-10-03, aarch64 macOS, synthetic data only): pinned offline verifier passes; 14 migration tests, 12 original CLI golden cases, 2 feed test functions covering 59 parser/rank/HTML/entity/query/highlight golden cases and rejection cases; 218 Python/Rust CLI comparisons pass. Refresh comparisons include RSS/Atom/JSONFeed, empty/explicit/all-source selection, repeat refresh, parse/missing-file failures, source metadata and preserved old item rows, SQLite integrity, FTS retrieval. Pending network refresh/enrichment/provider failures are asserted explicitly without live access. New locked dependencies (119 registry packages total) have MIT/Apache/Unicode/Zlib alternatives recorded in dependency-licenses.json; no paid runtime. Existing scripts/verify.sh passes (167 tests and benchmark/artifact/gitleaks gates); pinned local release --locked --offline build passes. Recording/build workspace remains below 2 GiB.

HTTP feeds and the eight network search providers remain pending; no TLS/proxy/fallback/retry implementation is inferred from this offline slice. MCP still requires legacy Content-Length plus official NDJSON compatibility. Remaining full-migration gates above continue to apply. All live providers and Windows/Linux execution remain unverified; installed CLI and real archive are unchanged.

## Preview publication and independent review

PR #18 (https://github.com/katalalab/katala-web-research/pull/18) was authorized for normal integration only after the parent's independent final review resolved P1/P2/P3. Immediately before integration, head `414d0ffce7b454d04dd733a317b968852493cc31`, base `e66e449cc210bd80ecb25a00391091e72abd9c2b`, active main ruleset 24318413, four required checks plus SAST success, zero unresolved threads, CLEAN/MERGEABLE were read back. Draft was cleared and merge performed with exact-head matching, without admin/bypass/self-approval or branch deletion. GitHub reports merged at 2026-10-03T07:27:48Z; merge commit and main readback both `e2c128296d4588062193086f833f623c5a4ad964`.

Feed PR #19 (https://github.com/katalalab/katala-web-research/pull/19) was created separately and retargeted to that main after #18 merged. Its common implementation base remains `414d0ff`; no feed feature entered #18. The initial published head `cce1ce2df0239f6da8b18d6f0eb9f45328123862` passed the four normal required checks and SAST. A separate agent's independent offline review found that ordinary JSONFeed content_text `Conditions: x < y > z, then continue.` lost `y >` in native HTML cleaning. The repair preserves whitespace-start angle expressions instead of treating them as tags, with Python-derived parser/HTML goldens and CLI/SQLite row regression. The repaired local verifier passes 218 comparisons.

Parent independently checked the repaired source, finding-specific fixture, CI and scope; the parent did not rerun all 218 native comparisons. After explicit #19-only integration authorization, repaired head `969ab09c40513f8f8332c57b646b7660b8ee9c73`, base `e2c128296d4588062193086f833f623c5a4ad964`, active protection, four required checks plus SAST success, empty review threads and CLEAN/MERGEABLE were freshly read. Normal exact-head merge, without admin/bypass/self-approval or branch deletion, completed at 2026-10-03T07:42:47Z. Merge commit/main: `9586f6e8614d7331ece5485c8d2f64b372914420`.

## Slice 3: native HTTP feed transport (local checkpoint)

Independent branch `codex/rust-http-feed-parity` starts at main `9586f6e`. Native reqwest/rustls GET feeds, environment proxy selection, common charset decoding, verified TLS, redirects and failure retention are implemented. No provider API, paid search/model call or real archive is exercised. Contracts and intentional diagnostic differences are in [http-contract.md](http-contract.md). The lock contains 193 registry packages with declared licenses recorded; notices packaging remains pending. Local pinned offline verifier passes existing 218 CLI comparisons, feed/migration tests and 28 new charset/proxy/redaction golden cases plus timeout validation. Network fixtures run separately on loopback; Windows/Linux and live providers remain unverified.

Preview integration does not certify complete migration, cross-platform/live providers, production archive switching, or installed CLI replacement. Copy migration still requires an unused destination in a quiescent directory; the independent writer race constraint remains in the runbook.

Independent review record: [review-feed-slice.md](review-feed-slice.md). The reviewer additionally passed 24 synthetic CLI comparisons for same-title items, same URL across sources, URL query/fragment dedup, retraction, oversampling/negative limits/highlights and unchanged existing feed/source/page rows. The reviewer read the repair diff and independently reran the finding-specific CLI. Remaining observed edge parity: local file references escaping above URI root, lone semicolon parameter references, and U+001C sentence separators.

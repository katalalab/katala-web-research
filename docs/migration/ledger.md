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

Pending native surfaces: four remaining network search surfaces (github/github_code/openalex/meta), positive enrichment and DDG parser/transport edges; read network/Jina/direct/refresh/cache miss; openalex expand; collect; remaining feed parser/transport edges; repos scan including encoding/incremental context; issues ingest/report; brief/investigate; doctor; deterministic eval; seven-tool MCP server.

Pending gates: complete golden/differential provider/ranking/Markdown/evaluation tests; full codec/URL/OS proxy and resolver cancellation edges beyond common transport fixtures; provider-specific fallback/pagination/secret-ref timeout; at-most-four meta concurrency and health ledger pruning; signals/broken-pipe semantics beyond simple CLI handling; hard-kill/power-loss migration recovery; additional known legacy schema variants; Windows/Linux execution; notices packaging and release target validation. All live providers are unverified. The Rust preview must not be described as a full migration or replace the user's common CLI until these gates pass.

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

The native HTTP core checkpoint is `4539b04`. Safety bounds are a separate follow-up commit: 8 MiB bytes, a shared deadline, 10 total redirects, downgrade/userinfo rejection, cross-origin sensitive-header removal and redacted body-free diagnostics. Normal Location/URI, charset, proxy/CONNECT/TLS, status/timeout/truncation and feed health/item comparisons: **40 pass**. Separate intentional safety checks: **12 pass**, including drip bodies, delayed redirect chains, cyclic redirect count, content-length/actual-byte bounds, error secret markers, downgrade, userinfo and old-item preservation. The cycle reference makes more than 11 requests; native stops after 11 requests / 10 redirects. No latency improvement is inferred from deadline checks.

Local final gates (2026-10-03, aarch64 macOS only): `scripts/verify-rust.sh` passes fmt, warnings-denied clippy, native tests and 218 CLI comparisons; `scripts/verify-http.sh` passes 11 fixture test functions / 40 reference comparisons / 12 safety checks; `scripts/verify.sh` passes the existing 167 Python tests and artifact/benchmark/secret gates; pinned `--release --locked --offline` build passes. Full migration, OS proxy/codec/URL edges, hard-kill recovery, release notices, other OS targets and all live providers remain pending. The existing CI runner matrix and workflows are unchanged. This HTTP slice needs the parent's independent exact-head review and CI before any integration; prior #19 merge authorization does not apply to it.

Draft PR #20: https://github.com/katalalab/katala-web-research/pull/20. Initial head `5a542fd` passed lint, Python 3.11/3.12 and SAST, but the existing instance-data heuristic rejected synthetic private-address CIDR fixtures. The reference generator now uses documentation-reserved TEST-NET addresses for the same unsupported-CIDR/host case and regenerates expected values from Python. No exemption, workflow change or protection bypass; fixture checks pass after regeneration. Exact repaired-head CI and independent review remain the publication gate.

Parent reviewed exact repaired head `5da9fc831b7fac6d08c796d97847bb7c735d57a5` through source, fixtures, dependencies, CI and recorded evidence; no native test rerun by the reviewer is claimed. After explicit #20-only normal integration authorization, head/base, active main ruleset, four required checks plus SAST success, empty threads and CLEAN/MERGEABLE were freshly read. Draft was cleared and exact-head normal merge completed without admin/bypass/self-approval or branch deletion at 2026-10-03T08:41:42Z. Merge/main readback: `96519c13350dfc35dab7847d932565fb24f4403e`. Full migration and real archive/CLI switch remain unauthorized. The subsequent provider worktree tracks this merged base; roadmap.md and golden-matrix.json record all final gates. Recoverable owned HTTP dev cache was cleaned after review to keep all worktrees/builds below 2 GiB; source/release outputs and user data were preserved.

## Slice 4: common provider boundary and normal DDG vertical slice

Independent worktree/branch codex/rust-provider-parity first saved roadmap/matrix checkpoint `fdf398b` atop unmerged HTTP head 5da9fc8, then merged approved main 96519c1 into its owned branch. HTTP review/integration was prioritized before publication. The roadmap records all remaining stages and dependency handling; the machine-readable matrix covers exactly 22 inventoried CLI leaves, eight network surfaces and five cross-cutting gates (35 rows). Its validator checks names against the reference inventory, uniqueness, reference identity and complete-versus-pending consistency. Every final acceptance row remains pending.

Native Request / Transport / SearchProvider / ProviderError boundaries and strict in-memory offline response steps now support future provider adapters. The DDG vertical implementation fetches its existing HTML endpoint with the reference q/Accept/user-agent, parses normal title/URL/snippet fields, preserves provider rank, and uses existing rank/query/category/candidate/highlight/CLI slicing. Python remains an oracle only. No production fixture URL knob, key, new dependency, registry fetch or paid/live service call is introduced. Other seven providers and positive enrichment remain unsupported; malformed/partial HTML and unusual attribute/transport edges remain DDG parity work.

Local evidence (2026-10-03, authorized aarch64 macOS): 12 parser + 72 request/rank Python goldens (84 cases), strict adapter mismatch/unused/unscripted and scripted failure/no-retry tests; 23 default/explicit DDG localhost TLS/proxy CLI comparisons including signed limits/query options/highlights, preserved pages/SQLite integrity, empty/status/timeout; existing 218 CLI comparisons; inherited 40 HTTP comparisons plus 12 safety checks; existing 167 Python tests and all benchmark/artifact/secret gates; fmt/warnings-denied clippy and pinned offline release build pass. Build gates execute sequentially; final gates/release use Cargo jobs=1. Owned worktrees/build targets total approximately 1.77 GiB, below the 2 GiB cap. No real archive, credentials, OS trust/network/auth settings, common CLI replacement or other-host validation. Future HTTP/2/3 feature changes must explicitly disable/test protocol retries. DNS/nativeTrust full wallclock cancellation, auth proxy/codecs/OS/live gates remain unverified.

This provider feature requires a separate parent's independent exact-head review and normal CI/integration decision. The #20 integration authorization does not authorize this slice's merge or a full-migration claim.

PR #21 head 2391115 received independent source/fixture/dependency/CI review with no blocking issue. A Python-measured P3 exposed unquoted href terminal slash being treated as self-closing in native parsing. The separate repair only changes the delimiter decision after parsed attributes; it adds Python-derived unquoted/quoted delimiter regressions and a localhost CLI test preserving the preexisting page row. Current affected gates: 98 parser/request/rank goldens and strict adapter tests, warnings-denied clippy, 24 localhost CLI comparisons pass. Review details: review-provider-slice.md. Repaired-head CI and independent diff confirmation remain required before normal integration.

Next group worktree codex/rust-json-provider-parity was created at frozen 2391115 before the P3 arrived; feature implementation is paused to prioritize the isolated PR #21 repair. No next-provider code enters PR #21. The fresh capacity inventory separates record/source material (approximately 7.67 MiB) from owned build targets (approximately 1877.66 MiB) rather than treating them as the same category. Available disk was approximately 593 GiB; the recording cap is 2048 MiB, below 10% free space. The combined estimate is approximately 1.84 GiB; it is not record-only usage. No new target is duplicated in the next worktree; idle build-cache reuse will occur after the dependency review checkpoint, with sequential jobs=1 and build growth monitored separately. No user data is removed.

Preview integration does not certify complete migration, cross-platform/live providers, production archive switching, or installed CLI replacement. Copy migration still requires an unused destination in a quiescent directory; the independent writer race constraint remains in the runbook.

Independent review record: [review-feed-slice.md](review-feed-slice.md). The reviewer additionally passed 24 synthetic CLI comparisons for same-title items, same URL across sources, URL query/fragment dedup, retraction, oversampling/negative limits/highlights and unchanged existing feed/source/page rows. The reviewer read the repair diff and independently reran the finding-specific CLI. Remaining observed edge parity: local file references escaping above URI root, lone semicolon parameter references, and U+001C sentence separators.

## PR #21 authorized preview integration

The parent independently reviewed repaired head `77a97a7990d8b00dd74d7cffbb7444662a28dec9`, including five Python delimiter model cases, source/fixture scope, CI and review evidence. No reviewer native rerun is claimed. After explicit #21-only authorization, repaired head, base `96519c13350dfc35dab7847d932565fb24f4403e`, active main ruleset, four required checks plus SAST success, empty comments/reviews/threads and CLEAN/MERGEABLE were freshly read. Normal exact-head merge completed without admin/bypass/self-approval or branch deletion at 2026-10-03T09:31:01Z. Merge/main readback: `2b8720c8cef6431490ded8b645acc62e297f05de`.

The next owned JSON-provider worktree fast-forwarded first to repaired 77a97a7, then approved main 2b8720c, before feature publication. PR #21 contains no JSON provider feature. A head-specific compiled snapshot with full SHA/provenance/checksums was saved in the frozen worktree's ignored build checkpoint before sharing its Cargo target. The common target's debug/release binaries now correspond to the JSON slice; they must never be assumed to be the frozen #21 binary. Run source-specific builds sequentially, or use that exact snapshot for reviewer verification.

## Slice 5: native normal SearXNG / Brave / Jina

Separate branch `codex/rust-json-provider-parity`, base approved main `2b8720c8cef6431490ded8b645acc62e297f05de`. Each provider implements its existing request/env/preflight, normal response fields and common ranking, with native CLI query/category/candidate/highlight/slicing integration. SearXNG retains 20/page requested-count bounding and validated optional settings; Brave retains count/offset, ten-page cap and localization/date/safety settings; Jina retains its single request, signed library slice and content/date fallback. Config credentials have no Debug output, and errors preserve redacted/body-free diagnostics. No Python runtime, additional dependency/lock change, new fixture URL option, workflow/runner/protection change or research algorithm.

Local evidence (2026-10-03, aarch64 macOS only):

- Python reference-derived adapters: **83 cases**, separately SearXNG 31, Brave 33, Jina 19; exact URL/header/order, signed limits/config/empty/null fields, paging/empty/later failures, rank/dedup/retraction, no retry, secret-marker diagnostics. Strict offline adapter never falls through to network.
- JSON provider localhost CLI: **76 comparisons**, separately 27/27/22, JSON/text/exit behavior, query/category/candidate/highlights, default env and invalid/missing config, status/timeout/non-JSON/later failure. Every comparison verifies complete preexisting synthetic database schema/row dump, user_version and integrity are unchanged. Exact Brave/Jina fixture CONNECT names map only to loopback; temporary CA is process-local. No live API/DNS/provider, paid call, real token or OS trust changes.
- Full pinned `scripts/verify-rust.sh` passes native tests, fmt and warnings-denied clippy plus existing **218** CLI comparisons. The first regression invocation could not locate a relative shared binary after harness chdir; rerun used absolute paths and passed. No failed run is counted as passing evidence.
- Inherited DDG: **24** localhost comparisons; HTTP: **40** reference comparisons plus **12** intentional safety checks. Existing `scripts/verify.sh`: **167** Python tests, benchmarks/artifact/gitleaks pass; known Python unclosed test database ResourceWarning remains. `--release --locked --offline` with jobs=1 passes.
- Record/source material approximately **8.58 MiB**, separately owned build targets **2001.18 MiB**, free disk **591.97 GiB**. Record cap 2048 MiB; build storage monitored separately per parent's clarified budget. One shared target, no duplicate JSON worktree target; sequential jobs=1. No source/user data removal.

Normal response checkpoints do not close final matrix acceptance. Remaining JSON edges include Unicode digit config, arbitrary ill-typed date/model values, NaN/Infinity/complex malformed/deep JSON, header-invalid keys, invalid HTTP-setting versus missing-config precedence, uncommon URL/codec/auth proxy, resolver cancellation, OS and all live behavior. Doctor/preflight CLI remains pending. Four other network surfaces, enrichment, network read/collect, repo scan/issues, reports/investigate/graph, doctor/eval/MCP and storage/release/platform gates still block full migration. This slice needs its own independent exact-head review and normal CI; #21 merge authorization does not authorize it.


## PR #22 independent P1: provider key across redirect origins

Parent source review of frozen head 1f47947 identified Brave X-Subscription-Token forwarding to another HTTPS origin. Before repair, a new synthetic localhost TLS/CONNECT test fails against the preserved exact-head binary: fixture-redirect-host receives public-fixture-key. No real credential or live service was involved. Prior #22 CI success therefore did not establish this secret-header contract.

The isolated repair keeps only ordinary negotiation/cache headers across a changed scheme/host/effective port; all conventional, provider-specific and unknown credential headers are removed case-insensitively. Same-origin redirects preserve headers. Once removed, credentials remain absent if the redirect chain returns to the original origin. Four Brave policy comparisons measure Python's marker-forwarding behavior versus Rust's removal, while comparing successful result JSON and preserving the full synthetic DB schema/row/version/integrity. The common transport regression retains Authorization/Cookie/Proxy-Authorization checks and adds X-Subscription-Token, mixed-case X-Api-Key and an unknown credential header, with preserved Accept-Language.

Affected/final local gates: JSON adapters 83, normal JSON CLI comparisons 76 plus four redirect safety comparisons; native fmt/clippy/tests and 218 baseline CLI comparisons; HTTP 40 comparisons plus 12 strengthened policy checks; DDG 24; existing Python verifier 167 tests/benchmark/artifact/gitleaks; pinned locked offline release build pass on aarch64 macOS. Diagnostics contain no synthetic key/body. Dependencies, workflow/runner matrix and main protection are unchanged. Python CI success is not Rust three-OS acceptance; Windows/Linux and all live providers remain unverified.

PR #22 remains draft and unmerged. The next edge-provider worktree remains at its original 1f47947 base with no feature changes while this P1 is prioritized. It must follow the repaired dependency after publication; no edge/new-provider feature enters this repair. A fresh exact-head independent repair review and current CI remain integration gates; no real archive or runtime CLI switch is authorized.


## PR #22 normal authorized preview integration

After independent repair review confirmed P1 resolved and no additional blocker at exact 23369e8, the parent authorized #22-only normal integration. Parent predicate/source/fixture/current-CI confirmation is distinct from the author's executed native/TLS tests; no reviewer native/TLS rerun is claimed. Immediately before integration, head 23369e8c1b3119a27d028825f870b88322285310, base 2b8720c8cef6431490ded8b645acc62e297f05de, active ruleset 24318413 with no bypass, four required checks plus SAST success, empty comments/reviews/threads and CLEAN/MERGEABLE were freshly read. Draft was cleared and exact-head normal merge completed without admin/bypass/self-approval or branch deletion at 2026-10-03T10:18:42Z. Merge/main readback: fc8db85fb0d0505899f410ba9d0b4455eb2b9df3. The frozen #22 worktree stays clean at repaired head; next owned branches follow approved main.

## Slice 6: malformed JSON / type / Unicode / config fixtures

Independent branch codex/rust-provider-edge-parity, base fc8db85. Additional library oracles: 259 (SearXNG 90 / Brave 86 / Jina 83); normal inherited oracles 83 retained byte-for-byte. Shared ranking now recognizes frozen Unicode decimal year facts, JSON preflight preserves reference digit conversion, and environment HTTP transport setup waits until the provider's first request. This resolves Unicode field/config and missing-key versus invalid HTTP-setting precedence rather than silently whitelisting mismatches.

Additional localhost evidence: 263 paired CLI comparisons (92/87/84), including 55 explicit named safety differences; 9 credential/config boundaries, of which 8 are included in the paired count and one is native-only userinfo rejection. 255 library cases execute through CLI; 3 NUL queries remain library-only because OS argv cannot carry NUL, and whitespace SearXNG URL belongs to the transport boundary. Root/null/collection/item/model types, malformed/nonstandard/deep JSON, Unicode/IDN, empty/header-invalid keys, missing key before invalid timeout, wrong endpoint and source preservation are covered. All cases preserve full old synthetic DB dump/version/integrity; every native error omits secret markers. Python userinfo DNS is never attempted.

Final affected gates executed once after implementation: fmt/warnings-denied clippy/native tests plus 218 baseline CLI comparisons; normal JSON 76 plus four Brave redirect safety comparisons; DDG 24; existing repo verifier 167 Python tests/benchmark/artifact/gitleaks; locked offline release jobs=1 pass on local aarch64 macOS. Existing HTTP core is unchanged, so prior author-executed repaired #22 HTTP 40+12 evidence is inherited and not falsely described as rerun here. Python unclosed test DB warning remains. Unicode tables are derived from the existing local Python 3.13/Unicode 15.1 oracle, with no new library/lock dependency; generator version asserts and committed fixtures allow reproducible native gates.

Five named safety policies (55 measured differences) stay explicit and require final contract acceptance. Every 35-row matrix final_acceptance remains pending. Four remaining providers and downstream command/storage/release/OS gates are still unimplemented. Separate remaining-provider worktree codex/rust-remaining-provider-parity was created at approved main fc8db85; no feature from it enters this edge slice. No live/paid service, real key/archive, OS trust/config change or installed CLI switch.


## Slice 7a: native GitHub code request/result/paging

The owned remaining-provider worktree began at approved main fc8db85 and fast-forwarded to fixed dependency PR #23 head 93fbeb0 before implementation. No GitHub feature enters the frozen #23 worktree. GitHub-code requests/results/config/422/empty/paging/fragments/metadata and native CLI wiring are implemented. Raw requests cap at 100/page and ten pages, token required before zero handling, any 422 aborts prior results to [], other failures propagate body-free without retry. Existing query/category/candidate/highlight and signed slice behavior is preserved.

Author evidence so far on aarch64 macOS: 29 exact strict Python adapter cases pass; 28 localhost TLS/proxy CLI comparisons pass, including a complete dump/version/integrity comparison of a page-seeded synthetic DB (other history tables initially empty), Unicode token/path/query/fragment behavior, cached highlights, ten-page cap, empty/later failures, missing token precedence and status-specific 422 behavior. Formatting/warnings-denied all-target clippy passes. Final affected gate readback: pinned fmt/warnings-denied clippy/all native tests plus 218 baseline CLI comparisons, existing repo verifier 167 Python tests/benchmark/artifact/gitleaks, and locked offline release jobs=1 pass. HTTP/JSON/DDG implementations are unchanged, so prior dependency-native/TLS gate evidence is inherited rather than redundantly rerun. Oracle replay is byte-identical. No actual gh program/token store, paid/live provider/DNS, real archive/credential, OS trust/network config, CLI replacement or workflow changes.

Publication must disclose stacked base codex/rust-provider-edge-parity at exact 93fbeb0 until #23 independent review/integration. No inherited merge authorization. All 35 final acceptance rows remain pending; GitHub repository fallback, OpenAlex, meta, enrichment/downstream commands/storage/platform/release and live gates remain incomplete. Subprocess native implementation/bounds are still pending with the repository/OpenAlex work; Rust never uses a Python wrapper.

## PR #23 independent P2: defer string-year conversion until after discard

Parent review of fixed head 93fbeb0 found that normalization converted a superscript string year before ranking could discard its row. The parent's separate Python 3.12 execution confirmed duplicate, retracted and empty-URL rows are discarded without conversion, while a surviving bad year raises ValueError. A new strict adapter fixture reproduces the failure on unchanged 93fbeb0 production code before repair. The isolated change adds an optional validation hook at the authoritative shared rank loop after existing discard gates; ordinary callers keep their infallible rank interface. JSON normalization retains non-text typed-field rejection; only ordinary string conversion moves to the reference evaluation point.

Twelve cases, four per JSON provider, have ordinary Python expected outcomes without policy overrides. Original 259 edge cases, all five policies/55 explicit differences, and original 83 golden fixture values are preserved. Author final affected gates: fmt/warnings-denied clippy/all native tests and 218 baseline CLI comparisons; new/current edge library 271, localhost paired CLI 275, nine config boundaries including one extra native-only endpoint rejection, locked offline release jobs=1 pass. Shared feed/rank goldens pass. Unchanged HTTP/Python gates use already executed author evidence rather than meaningless reruns. No reviewer native/TLS rerun is claimed; the parent's evidence is independent predicate/source and Python baseline execution. No paid/live API, real key/archive, OS trust/config, dependency/lock/CI or installed CLI change.

PR #23 remains unmerged pending repaired exact-head CI and independent diff confirmation. PR #24 stays fixed at 230b7d7/base93fbeb0 until its dependency-follow-up is separately recorded and affected gates confirmed. The separate repo/OpenAlex/meta worktree is paused at 230b7d7 for this repair. Current acceptance decomposition work remains outside both repair scopes; no final migration or Rust three-OS claim.

## PR #24 dependency follow-up and preservation fixture

The owned branch merged repaired dependency c728562b513295ba1774c50b70e8a5bf680ecde9 without rewriting history. Its production Rust/Cargo.toml feature diff against that base is byte-identical to the independently reviewed original 93fbeb0..230b7d7 feature diff. Append-only documentation conflicts retain both slices. No next-provider or acceptance implementation is included.

The parent identified that the original GitHub-code preservation fixture populated pages only. Earlier claims are narrowed accordingly. The 28 paired CLI comparisons now populate all eight user tables: pages, runs, search_results, repo_documents, feed_sources, feed_items, project_items and engine_runs. The fixture asserts every table is nonempty before snapshotting the complete SQLite dump, user_version and integrity, then compares each child archive before/after every success or failure. All data are synthetic; this proves preservation of these populated fixture rows, not arbitrary archives or migration/crash recovery.

Author affected gates on aarch64 macOS: pinned fmt/warnings-denied clippy/all native tests (including 29 GitHub-code and 271 JSON edge adapter cases), 218 baseline CLI comparisons, strengthened GitHub-code 28 and repaired JSON edge 275 paired localhost comparisons pass; 55 named safety differences and nine config boundaries remain explicit. Locked offline release jobs=1 passes. Unchanged Python verifier/HTTP/DDG evidence is inherited, not rerun here. Existing public CI/workflows/cost posture remains unchanged; no live calls, real credentials/archive, other-host execution, installed CLI switch, main merge or inherited merge authorization. Independent review should use dependency c728562 and the new exact feature head.

The first follow-up CI at e444696 found SQL-formatting patterns in the fixed-table fixture counter. The counter now uses a literal UNION ALL query and asserts exactly the eight expected table names and nonzero counts; no ignore, rule or workflow change. The affected 28 paired CLI comparisons pass again. Native production files are unchanged, so their completed gates and release artifacts remain applicable; exact-head CI still requires fresh readback.

## Authorized preview integration of PR #23 and #24

Independent final review confirmed PR #23 c728562 P2 resolution, twelve Python fixture expectations and unchanged prior 259 cases, with no new blocker. PR #24 2f67545 Rust/Cargo feature diff matched its original reviewed delta; the reviewer independently executed eight-table seed/integrity and checked literal SQL plus five green CI checks. Native/TLS gates remain author evidence. Explicit parent authorization covered ordinary #23 then #24 integration, never installed CLI or real-data cutover.

Fresh #23 checks: head c728562/basefc8db85, active ruleset24318413/no bypass actors, five checks SUCCESS, no review threads, CLEAN/MERGEABLE. Normal merge yielded main 6fce86e35c96fca9e56b6be463f4555ff16da632 at 2026-10-03T11:43:09Z, tree-identical to c728562. #24 retargeted without head change to that main; effective feature diff stayed identical, so completed exact-source affected gates remained applicable. Fresh #24 head2f67545/base6fce86e, unchanged protection/five SUCCESS checks/no threads/CLEAN/MERGEABLE; normal merge yielded main 5a2ee672297e31ba78c340b824c791e75e200b80 at 2026-10-03T11:44:38Z, tree-identical to 2f67545. No admin bypass/self-approval/forcepush/branch deletion or direct main edit. Readback confirmed both merges.

Separate clean next-provider worktree codex/rust-repo-openalex-meta-parity fast-forwarded to integrated main5a2ee67 before implementation. No old repair enters the next feature diff. All 35 final acceptance rows and OS/live/storage/downstream gates remain open; new scoped case evidence will be added alongside executed next-slice gates.

## Slice 7b: native repository fallback and owned subprocess

No old repair is mixed into the feature: branch begins at integrated main5a2ee67, with the preceding documentation-only commit recording #23/#24 authorized integration. GitHub repository normal Unix gh/REST request/result/CLI slice is implemented. Author final gates on aarch64 macOS: 51 strict Python adapter expectations, byte-identical oracle regeneration, all native tests/218 baseline CLI comparisons/fmt/warnings-denied clippy, 30 paired loopback/owned-gh CLI comparisons, five owned executable raw parity cases, eight separate safety assertions, locked offline release pass. The process fixture verifies cap/deadline/graceful SIGINT/SIGTERM and descendant heartbeat stops, not SIGKILL or detached-child recovery. Native sources/binary tree evidence is recorded with a reproducible content hash in matrix case_evidence. The 35 final rows remain pending despite newly passed scoped cases.

One new direct dependency relationship uses already locked/cached libc=0.2.190 on Unix (MIT OR Apache-2.0); Cargo.lock package versions/checksums and package set remain unchanged. Required repository verifier also passes: 167 Python tests, deterministic benchmark/smoke/artifact guards and gitleaks (no leaks); known Python test DB warning remains. No unknown software, added paid/API/model call, new auth/network/OS setup, real data or installed CLI change. Own compiled gh fixture and exact loopback TLS mapping only. Windows native child safety is explicitly unimplemented; Linux execution unverified. Empty stdin/output cap/signal behavior needs final contract acceptance, and complex model/representation/env/codec/transport/lifecycle/live gates stay open. OpenAlex and meta remain next separate slices.

## PR #25 independent P3: deadline before completed-stream success

Parent independent source/scope review confirmed no blocking issue and replayed all 51 Python/transcript cases with five green CI checks. It identified a small deadline-order issue: completed child status and both captured streams returned success before elapsed was checked. A separate repair commit changes only the process decision order, a private owned-child scheduling fixture and its documentation/evidence. The fixture first fails against the old production decision order, then passes after deadline is checked before success. Test helper selection is explicit; no production environment/CLI fault hook or installed executable is used. No OpenAlex feature or older repair enters this commit.

Final affected author gates: fmt/warnings-denied all-target clippy, process boundary/lib and strict runner/51 GitHub-repository adapter cases, five owned-process raw comparisons/eight safety assertions, 30 paired repository CLI comparisons and locked offline release pass; existing broad 218 CLI/Python/other-provider gates are unchanged and not redundantly rerun. The case record includes the repaired production content hash. Exact-head CI is recorded in PR readback; independent repaired-head review and normal merge authorization still pending. OpenAlex remains in its separate dirty worktree at the old dependency, to follow the repaired checkpoint separately. No paid/live API, real data/credential, OS/network configuration or installed CLI change.

## Authorized PR #25 integration and slice 7c OpenAlex search

Parent final independent repair review confirmed eda15e2 P3 closure/no additional blocker and explicitly authorized ordinary integration. Fresh readback: head eda15e2c23dbf9564183c7a2751dbf68bba37c27/base5a2ee672297e31ba78c340b824c791e75e200b80, active ruleset24318413/no bypass actors/five checks SUCCESS/no review threads/CLEAN/MERGEABLE. Normal merge at 2026-10-03T12:37:10Z yielded main e91513bc0516b328d6432ba73d293343b8b3af42, tree-identical to eda15e2. No admin/self-approval/forcepush/branch deletion/direct main edit. Separate OpenAlex worktree followed that integrated main with existing owned dirty feature files preserved; the feature diff contains no previous process repair. Installed CLI and real archives were never switched.

Native OpenAlex search now includes lazy/per-page raw/op key resolution and filter validation order, exact select/query/cursor/remaining count parameters, normal identifier/abstract/metadata/snippet/date/URL normalization, shared rank discard-year order and CLI wiring. Pure work_id spelling helper is included but does not implement graph/cache. The only op executable exercised is our own Rust fixture in isolated PATH; all HTTP maps api.openalex.org only to loopback using process-local ephemeral CA. No real credential/vault/op, paid API/model/live DNS/call, user research archive or OS/network/auth setup.

Author final executed gates on aarch64 macOS: 95 exact Python search/HTTP/op transcript cases, 13 identifier cases, 34 paired localhost/owned-op CLI comparisons preserving all eight populated user tables/full dump/version/integrity across errors; byte-identical oracle replay; 660 Python3.13/Unicode15.1 alphabetic ranges replay identically after pinned formatting without rewriting sources. fmt/warnings-denied all-target clippy/all native tests plus 218 baseline CLI comparisons, required verifier 167 Python tests/deterministic benchmark/smoke/artifact/gitleaks and locked offline release pass. No new dependency/lock/workflow/runner/protection change. Previous HTTP/DDG/JSON/GitHub localhost gates are unchanged and inherited, not claimed as rerun here. The offline unsupported-provider guard now uses remaining meta and cannot accidentally access OpenAlex.

All 35 rows now contain concrete pending_reasons separate from scoped case_evidence and final_acceptance_scope; ten measured passing case records are present, while final acceptance remains pending in every row. Historical unallocated aggregate gates are not inflated into per-row completion. Meta is the remaining component provider; graph/cache, enrichment and downstream command/report/storage/release/Windows/Linux/full lifecycle/live/safety approval gates remain open. No final migration or speed claim. Exact source/binary provenance and CI/independent review are recorded with the published checkpoint.

## Draft #26 freeze and local Meta components

OpenAlex Draft PR #26 remains fixed at 91da3879ee84e8226f858da7d812e0ccb2d898e3/basee91513bc0516b328d6432ba73d293343b8b3af42. Read-only readback confirms all five existing CI checks SUCCESS, draft OPEN; these Ubuntu Python/security checks are not native Linux evidence. No #26 merge authorization or independent-review completion is inferred.

A separate owned worktree starts on that exact draft head. Meta contract/completion gates were saved before implementation. The local native component checkpoint implements profile/rewrite, bounded four-worker execution, completion-order fusion, health annotations/routing and transactional ledger writes. It deliberately leaves the Meta CLI refusal in place until combined native/config/archive/CLI/error/signal cases are executed. No partial provider completion, release or final-migration claim.

Author aarch64 macOS evidence: 60 profile/rewrite, 168 health boundary, 32 fusion inputs (each six signed limits), two annotation cases; 33 fixed provider/clock/completion transcripts with exact calls and partial/error/weak routing/duplicate behavior. Four native policy cases cover strict fixture refusal, channel-controlled completion, four-worker/all-jobs-drained after error and synthetic ledger 500/provider prune/50-row routing/seven unrelated populated tables/FTS/integrity/atomic rollback. Both generators replay byte-identically. fmt/warnings-denied all-target clippy/all locked offline native tests pass. Required Python verifier passes 167 tests, smoke/deterministic benchmarks, artifact guards and gitleaks/no leaks; inherited CLI/release/live checks are not relabeled as Meta execution.

Three scoped Meta case records bring the matrix to 13 passing records and 35 pending final rows. Production source content hash is 7d37ae7cd1bdf374e886bed5d056013616dc6aa8b9aede9b37dfa61a2849f6ad; original #26 binaries/provenance remain recoverable at their immutable checkpoint. No dependency/lock/toolchain/workflow/runner/protection/auth/network configuration changes. No live/paid/API/model calls, real archive/vault, installed CLI or other-host action. Remaining combined CLI/config/schema/refusal/signal/panic/representation/history-boundary and final OS/downstream/storage/release work is concrete in meta-contract.md and matrix pending_reasons.

## PR #26 independent P3: unused best-location URL branch

Parent focus review independently replayed all original 95 search/13 identifier Python
expectations byte-identically and checked five green existing CI checks, with no new
blocking issue. The review found that a valid primary URL plus string best_oa_location
succeeds in Python but native eagerly inspected the unused best branch. The isolated
repair only moves best lookup behind primary URL selection. Eight unannotated fixture
cases (string/number/bool/array, each unused versus selected) first fail on unchanged
91da387 production code and then pass. Original 95/13 expectations are unchanged.

Author affected Mac gates: 103/13 strict cases, identical regeneration, fmt/warnings-denied
all-target clippy, locked offline debug/owned-fixture and release builds pass. Existing
34 paired OpenAlex CLI/218 broader CLI/Python evidence is inherited, not called rerun;
independent native/TLS execution remains absent. Matrix adds only eight new scoped cases
with production source hash a3a28d1739ceb921c5c7d1e139e798891c5b6f0b615af1fb95d5ec3f15281e98.
All 35 final rows remain pending. Abstract-position/aggregate result/page/byte budgets
and cap/one-over/allocation/interruption tests are concretely pending in openalex-contract.md.
Meta remains on its separate local 7e6f3b8 branch and is not part of the repaired diff.
No dependency/lock/CI/budget/auth/network/OS/real archive/installed CLI change. Repaired
exact-head CI/focus confirmation and ordinary merge authorization remain separate steps.

## Authorized PR #26 integration and native Meta preview

Parent final independent review confirmed the eight-case short-circuit repair on
5dffce09d2a04c1281dc36c1149b44823d80902e and explicitly authorized ordinary merge.
Fresh head/base e91513bc, active ruleset24318413/no bypass actors, five SUCCESS checks,
no review threads and CLEAN/MERGEABLE were checked. Normal merge at
2026-10-03T13:54:50Z yielded main186511a102d241dd207d9b616c00b94bfd16537e,
tree-identical to repaired head; fresh API readback confirms MERGED/main. No bypass,
self-approval, forcepush, branch deletion, installed CLI or archive cutover.

The separate Meta branch normally merged that integrated base before CLI publication.
Native preview now includes all component providers, four-worker completion fusion,
health routing and transactional ledger; exact-source tests run only on author Mac.
Production source SHA256:
2fa7950c42f6c2db3baf05c6fae6ff6081702e91376b675a43416d0eb79d9b77.
Completed gates are retained rather than rerun because of a model/session change:
262 component fixture inputs/33 fixed completion transcripts/four native policy cases,
all locked offline native tests, warnings-denied clippy, 37 combined CLI/library pairs,
four worker-time signal executions, 218 baseline CLI comparisons, locked offline release
and required verifier (167 Python tests/benchmarks/smoke/artifact guards/gitleaks).
Five additional schema pairs expose all eight returned component metadata sources
(26 native rows). The clock/order replay uses raw reference components and recomputes
all health/fusion/ranking/output; no result/health/score/rank normalization. Freshness
and limits are explicit in meta-contract.md.

CLI coverage allocates 167 leaf cases and one root version case from 168 strict hooks;
remaining aggregate assertions are unallocated, not claimed as per-command evidence.
Native MCP is 0/7; all 35 final rows remain pending with concrete missing assertions,
proposed test files and closure conditions, distinct from 27 scoped passing case records.
Worker-time archive preservation does not cover SQLite-busy/during-commit interruption
or panic/redaction; raw signal exits differ explicitly. Other OS/native release, graph,
read/enrichment, downstream/report/storage crash and live/resource-budget gates stay open.
No dependencies/lock/toolchain/workflows/runners/protection changes, paid API/model/live
calls, real data/credential, OS/auth/network setup or other-host execution. No speed claim.
Source/log recording remains far below the 2 GiB cap; shared build cache is measured
separately. Existing public CI and exact draft head will be read back before review.

## Authorized #27 integration and next reader dependency

Independent parent preview review found no blocking issue on8940c1f; health168/fusion224
Python oracles and same-SQL500/provider/50-window/rollback/FTS/integrity independently
confirmed. Parent authorized normal merge. Fresh exact head8940c1f/base186511a, active
ruleset24318413/no bypass actors, five SUCCESS checks, no threads/no next page and
CLEAN/MERGEABLE checked. Normal merge at2026-10-03T15:13:13Z yielded
maincb79a8a2a6af316cea9d547835a5277ac24dee9d, tree-identical readback. No bypass,
branch deletion, installed CLI or archive switch. Owned separate read branch
fast-forwarded to that main with its own dirty implementation preserved.

Correction: actual reference MCP has **nine** tools; original README's seven-tool
example and my earlier0/7 prose were inaccurate. Saved inventory/coverage already
contain all9schemas and remain unchanged. Native tools are0/9. Current code requires
reader for MCP read/investigate, search enrichment and collect, with eval/brief also
unimplemented; direct reader/selected-cache is prioritized as a small native slice
before completing all MCP tools. #27 source head remains fixed. Shared HTTP startup/
cancel waits, commit interruption, worker panic/shared-archive contention and actual
OS/final gates are still unverified; simulated commit cannot close these assertions.

## Direct-reader local slice

Native direct HTTP read and selected cache miss/refresh writes are implemented on
a separate branch following integrated maincb79a8a. Exact production content SHA256:
fac5dbbb0201960148459c43b8fb5f71b7e83071a2a6b20313556b550657b5f3.
Author aarch64 Mac gates:51 Python response/request/error/clock expectations with
byte-identical regeneration;36 paired normal localhost CLI cases and six paired
cache hit/failure cases; two owned SIGINT executions during actual HTTP wait; actual
competing SQLite writer lock and owned TEMP-trigger abort preserve old page/pages
FTS/integrity. JSON/text/timestamp shape/source fields/cache flags, populated seven
unrelated tables and selected/unselected archives/schema/version are checked. Other
FTS data were not independently dumped by the CLI fixture and remain explicitly open.

Affected inherited cache/engine method, golden suite and12 migration tests pass, all-target
clippy and locked offline debug/release pass. Required verifier167 Python tests,
benchmarks/smoke/artifact guards and gitleaks/no leaks pass. Prior Meta/provider/218-wide stages
remain inherited at their hashes and are not relabeled as rerun. Initial new CLI
fixture failures were independent seed timestamps, duplicate --reader in fixture
argv, Python error-body and cache-hit expectation mistakes; corrected expectations
use the Python contract, not values learned from native output. Successful36 normal
cases/signals were preserved and only affected six cases rerun. Normal timestamps
are the only output normalization; clock format is validated. Native HTTP diagnostics
remain body-free, an inherited policy difference from Python raw error bodies.

Matrix now has31 scoped records and35 pending final rows. Native MCP0/9; auto/Jina
and positive enrichment/native downstream remain pending. This is no final read or
full migration claim. Actual SQLite busy-interrupt/commit-window/worker-panic/crash
recovery must use real owned processes and databases, not mocked commit results. No
new dependency/workflow/toolchain/lock/license/paid/live/key/data/CLI/OS changes.

## PR28 independent P3 index proof

Parent final source review found no production blocker but independently demonstrated
that FTS delete-all can leave external-content SELECT and SQLite integrity unchanged,
while MATCH changes. Minimal test-only repair adds rank1 FTS integrity plus MATCH
snapshots; a removed-entry negative control fails old helper and is rejected after
repair. Two paired successful cache miss/refresh cases assert new MATCH/old-term
removal using immutable9451 native binary. No production/Cargo change, previous51/42
expectation rewrite or feature-whole rerun. Independent exact-head CI/focus follow-up
remains separate from merge permission. Trusted CLI and untrusted MCP target policies
remain separate; full35 acceptance rows stay pending.

## Separate Jina/auto reader vertical checkpoint

Dedicated branch follows #28 test-only75e7980 repair; original/direct feature is not
rewritten or mixed into its repair. Production source4bf2ce644b69da67b65d58245f3fe92201c296b1aee023b5f0cf02bfbd95d488.
Native Jina quote/Markdown/JSON-error/source/original-target behavior and FetchError-only
auto fallback are implemented; real raw TimeoutError stops without fallback. Jina
transport error diagnostics mask opaque target URL/body/reason, direct errors retain
inherited redaction. Native CLI output buffers at most8MiB before cache upsert/stdout;
output cap differs from unbounded Python and awaits final policy approval.

Author Mac evidence:93 exact Python response/request/error/clock transcripts and
byte-identical regeneration;44 paired CLI cases (38 normal source/redirect/query/cache,
6 failed-refresh/timeout/secret-diagnostic cases),7 separate exact/one-over byte cap
policy cases (text/JSON/UTF8 and HTTP body),2 owned real TLS HTTP-wait SIGINT executions.
Old successful cache/seven unrelated populated tables/schema/version, selected versus
unselected archive/pages MATCH/rank1 integrity are preserved. Initial fixture's auto
timeout expectation was wrong: actual Python/source propagates TimeoutError. Existing
successes were retained; only remaining7 and new UTF8/query cases were executed.

One existing serde_json raw_value feature is enabled to preserve huge integer spelling
without changing ordinary Value parsing. Official cached license MIT OR Apache2; no
new package/dependency/version/checksum/lock/license/workflow/runner/toolchain; the
existing serde_json feature configuration changes explicitly.
Because the shared feature changed, all locked offline native tests ran once and pass;
warnings-denied clippy/debug/release and affected old cache method pass. Required
verifier167 Python tests/benchmarks/smoke/artifact guards/gitleaks/no leaks pass. Prior
provider TLS/218-wide gates remain inherited, not claimed rerun.

MCP tool dependency map/checker requires all9 exact schema names and all35 rows accounted
for, including standalone commands; mapping is not native protocol evidence (0/9).
36 scoped records/35 final rows pending. Trusted opt-in CLI URL contract differs from
future untrusted-tool resolved-address/redirect/proxy target policy. Real SQLite busy
interrupt/before-during-after commit/restart, worker panic/redaction, SIGKILL/power-loss/
broken-pipe and actual other OS/live/resource/package gates remain concrete and open.
No mock closes those gates. No real data/credential store/installed CLI/network/OS setup
or paid/live/API/model call; no speed claim.


## PR28 and PR29 authorized normal integration

Parent independently reviewed the #28 P3 helper and exact75e7980 with five green CI
checks; native production remained9451 content. Fresh head75e798023dac23689168201948ccc867fc9c3d26/
basecb79a8a2a6af316cea9d547835a5277ac24dee9d, active ruleset24318413/no bypass actors,
five SUCCESS checks/no threads/CLEAN/MERGEABLE were confirmed. Normal exact-head
merge completed2026-10-03T16:41:02Z, main08052376f50601f32c5bff80aa03e5574ed7fbbc
read back tree-identical to75. #29 retargeted to that main without changing0e9 head;
effective diff SHA2567e49b6a538c4cac8b8917a207b77ebcb2e5414bb705c5981c39dd4dcb8bf8897
was byte-identical to the earlier stacked-base diff; retained gates stayed applicable.

Parent independently checked93 Python oracle structures, FetchError-only fallback,
cap-before-cache and diagnostic masking; no new preview blocker. Independent native/
TLS execution was not claimed. Explicit29-only normal merge authorization preceded
fresh head0e9c5defc2baaf57c64d8231ea19427b441a3a49/base08052376, unchanged active
protection/no bypass actors/all five SUCCESS checks/no threads/CLEAN/MERGEABLE and
public repositoryID1251159956 readback. Existing workflows were unchanged. Normal
merge completed2026-10-03T16:57:21Z, maincc086afb6a1c5acb080f00ac4ae24456262cf1c7
read back tree-identical to0e9. No admin/bypass/self-approval/forcepush/branch deletion,
installed CLI/data cutover, budget or authentication/network setting change.
Jina complete target query/fragment/userinfo transmission remains a distinct policy
gate from diagnostic masking; confidential URLs/untrusted MCP must not default to it.

## Separate search enrichment slice

Dedicated codex/rust-enrichment-parity worktree starts at integratedcc086afb; #29 head
was kept fixed. Contract enrichment-collect-contract.md was saved before implementation.
Native workflow and search CLI reuse the existing reader, transport, registry/ranker
and cache highlights. Initial candidate order, plain Python whitespace/Unicode700,
stale metadata, title fallback, exception class only, original result URL/source,
original-query rerank and enrichment-before-signed-slice are preserved. No page write.
Cargo.toml adds the workflow test target only; lock/toolchain/dependencies unchanged.

Author aarch64 macOS evidence:57 exact raw Python transcripts with request/clock/error
assertions;40 paired feed CLI cases +12 separately added SearXNG/category/domain/
highlight cases =52 unique pairs;2 actual owned TLS HTTP-wait SIGINT executions.
Selected/unselected eight-table synthetic archives/schema/version/pages MATCH/rank1
integrity remain unchanged. Initial fixture seed/dedup/invalid-CLI-choice assumptions
were corrected against Python, not learned from native output. Successful scopes were
retained; only added12 cases reran. The old uncounted unsupported-enrichment refusal
was removed;218 counted existing comparisons still pass. Pinned fmt/all-target
warnings-denied clippy/all native tests, existing Python167/benchmark/smoke/artifact/
gitleaks gates pass. Release result/provenance is recorded with the final checkpoint.

Source0930d484d0858a299732b34cfc75f3b02ac5d3ca7a047495820ef630a9024485; fixture
7c1958a92f1ca10cd9c02b5ea5b7097ae40d5bf4114f836390be8369ef48afbb. Matrix now38
scoped case records/35 final rows pending; native MCP0/9. All-provider combined
enrichment, malformed/resource/full lifecycle/actual Windows-Linux/live gates remain.
Collect/report/store_run remain unimplemented; failed error-page upsert conflicts
with successful-cache retention and needs a separate concrete policy/test slice.
No live/paid/API/model/real credential/archive/other-host/installed CLI changes.
Shared build target ~3.36GiB is tracked separately; source/fixture/log recordings stay
under2GiB, free disk ~569GiB. No budgets, workflows/runners/protection, OS/auth/network
configuration were changed; no new package/license condition or speed claim.

Pinned locked offline release build passes (jobs1); fixture regeneration is byte-
identical. Recoverable owned checkpoints retain prior heads and the new exact-source
binaries. Local artifact provenance (aarch64 macOS only):
- debug: SHA256 de98d5a80f26d6d0b76a760cf14ae09b0094454317081080e67595dd7e4f3809, 28773752 bytes.
- release: SHA256 e8dd6d6a044ca11c09fa36d66dfbdc011f344781ba7e01e234d4ccdd9493cb5f, 8384448 bytes.

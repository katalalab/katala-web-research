# Complete native migration roadmap

Reference Python source: `e66e449cc210bd80ecb25a00391091e72abd9c2b`; inventory: python-contract.json, 22 leaf commands, 41 SQLite objects, seven MCP tools. Native migration is incomplete. Preview integration never satisfies the final acceptance gate or authorizes installed CLI / real archive replacement.

## Branch and dependency ledger

| Slice | Exact checkpoint | Integration / dependency |
| --- | --- | --- |
| Local retrieval / copy migration | PR #18 head 414d0ff | Merged as e2c1282 after independent review and exact-head checks. |
| Feed parse / file refresh / stored-feed search | PR #19 head 969ab09 | Merged as main 9586f6e after separate authorization. |
| Native HTTP feeds / transport safety | PR #20 head 5da9fc831b7fac6d08c796d97847bb7c735d57a5 | Draft, review pending; frozen. Five existing CI checks pass. Not merged. |
| Provider common contract / first vertical provider | codex/rust-provider-parity | Own worktree starts at exact PR #20 head above. HTTP dependency is unmerged; no claim its APIs/security decisions are approved. |

A provider PR must initially use codex/rust-http-feed-parity as its stacked base and name both head SHAs. It must not silently include PR #20 in an independent main-based feature diff. If HTTP review requests repairs, fix PR #20 first, then update only the owned provider branch to the reviewed dependency and repeat affected gates. After authorized PR #20 merge, retarget the provider PR to main and verify the final feature-only diff / exact heads again. No forcepush, main direct edit, or inherited merge authorization.

## Implementation order and completion evidence

| Stage | Native deliverable | Dependencies / exit evidence |
| --- | --- | --- |
| 4 | Common provider request/result/error/transport contract; strict offline response adapter; DDG GET/parser/rank/CLI vertical slice | HTTP #20 dependency; Python-derived request/result goldens, synthetic error/empty/no-retry tests, localhost CLI differential without provider access. |
| 5a | SearXNG pagination/config/preflight; GitHub repo gh-to-REST fallback and code query repair/paging | Shared adapter; request URLs/headers/order, invalid env rejection before calls, subprocess timeout/missing executable/nonzero/malformed output fixtures. No real token reads. |
| 5b | Jina, Brave, OpenAlex request/response adapters | Synthetic env only; authentication posture, filters, pagination/cursor stops, metadata, redacted failures. No paid or live calls. |
| 5c | Meta query profiles, provider selection, bounded four-worker fanout, fusion, partial failures, health routing/pruning | All component adapters; deterministic clock/latency fixtures, tie/order/dedup/source-count metadata, 500/provider pruning, non-writable ledger behavior. |
| 6 | Network read auto/Jina/direct, refresh/cache miss, enrichment, collect storage/reports | Provider/read transport; FetchError-only fallback, charset/header/meta text extraction, pages/run/results schemas, evidence/report parity and failed capture retention. |
| 7 | Repository scan/incremental/context; issues ingest/report/live adapter | Synthetic filesystem / JSON / gh transcripts; traversal skips, encoding, Unicode paths, size/mtime/hash/context, FTS triggers and issue radar ordering. |
| 8 | Brief/investigate and OpenAlex graph/cache | Planning/rank/read/storage; selected evidence/capture failures/provenance/checklist/Markdown exact fixtures; graph direction/paging/cache/dedup. |
| 9 | Doctor, deterministic eval, seven-tool MCP server | All native commands; FTS probe/config posture, threshold/exit behavior, legacy Content-Length plus NDJSON, partial/invalid frames, notifications/error codes/stdout purity. |
| 10 | Complete storage migration/release/platform gate | All commands; known schema versions/legacy variants, synthetic-copy crash interruption/restart/rollback, signals/broken pipe, locked reproducible Mac/Windows/Linux target runs, licenses/notices/package validation. Other hosts currently unauthorized and unverified. |
| 11 | Optional research improvements | Separate commit/PR after full reference baseline comparison; parent supplies paper review; adopt only measured evaluation gains within existing cost/network limits. No inferred speed claim. |

Stages can be split into reviewable vertical PRs. The golden matrix is in golden-matrix.json; every pending row blocks a complete-migration claim. An adapter trait or an offline parser alone never marks a provider/command complete. Final acceptance requires native CLI/library/storage/report/error behavior, real target execution evidence, explicit approved intentional differences, no Python runtime dependency, and all pending rows closed. Live provider certification is tracked separately; it remains unverified unless narrowly authorized. No automatic production cutover follows acceptance.

## Reproducibility, recording and cost

Rust/MSRV 1.96.0 and Cargo.lock are fixed. Existing CI public-runner matrix is unchanged; Rust gates are local aarch64 macOS evidence. One CPU/build job at a time. The 2 GiB recording/build cap includes all owned worktrees/targets, not only tracked files. Inspect sizes before a new build; retain compact fixtures/commit evidence, avoid cumulative raw logs/downloads, and remove only recoverable self-generated build cache when idle. Never remove user archives, credentials or someone else's cache/dirty files. Provider fixtures reject unscripted requests; localhost fixtures bind only loopback. Official registry dependencies only, zero paid API/model/live search calls, no OS/network/auth configuration changes.

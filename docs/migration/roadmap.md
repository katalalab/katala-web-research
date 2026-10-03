# Complete native migration roadmap

Reference Python source: `e66e449cc210bd80ecb25a00391091e72abd9c2b`; inventory: python-contract.json, 22 leaf commands, 41 SQLite objects, nine MCP tools. Native migration is incomplete. Preview integration never satisfies the final acceptance gate or authorizes installed CLI / real archive replacement.

## Branch and dependency ledger

| Slice | Exact checkpoint | Integration / dependency |
| --- | --- | --- |
| Local retrieval / copy migration | PR #18 head 414d0ff | Merged as e2c1282 after independent review and exact-head checks. |
| Feed parse / file refresh / stored-feed search | PR #19 head 969ab09 | Merged as main 9586f6e after separate authorization. |
| Native HTTP feeds / transport safety | PR #20 head 5da9fc831b7fac6d08c796d97847bb7c735d57a5 | Parent's independent source/fixture/dependency/CI review found no blocker; normal authorized merge as main 96519c13350dfc35dab7847d932565fb24f4403e. Review did not rerun native tests. |
| Provider common contract / normal DDG | PR #21 head 77a97a7990d8b00dd74d7cffbb7444662a28dec9 | Independent repair review resolved unquoted URL delimiter finding; authorized normal merge as main 2b8720c8cef6431490ded8b645acc62e297f05de. Reviewer ran 5 Python delimiter models, no native rerun. |
| SearXNG / Brave / Jina normal JSON adapters | PR #22 head 23369e8c1b3119a27d028825f870b88322285310 | P1 repaired with cross-origin safe-header allowlist; independent parent predicate/source/fixture/CI confirmation, author native/TLS evidence. Normal authorized merge as main fc8db85fb0d0505899f410ba9d0b4455eb2b9df3. |
| JSON/config/Unicode edges | codex/rust-provider-edge-parity | Independent worktree follows main fc8db85; 271 additional library and 275 paired localhost CLI cases after the P2 discard-order repair, nine config boundaries including one native-only policy check; final acceptance pending. |

Before #20 merged, a provider PR would have used codex/rust-http-feed-parity as its stacked base and named both head SHAs, rather than silently including #20 in a main-based feature diff. HTTP review and integration were handled first. Subsequent provider publication uses main 96519c1 and must verify feature-only diff / exact heads. Future unmerged dependencies follow the same explicit stacked-base ledger, repair-first order and retarget/retest gate. No forcepush, main direct edit, or inherited merge authorization.

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
| 9 | Doctor, deterministic eval, nine-tool MCP server | All native commands; FTS probe/config posture, threshold/exit behavior, legacy Content-Length plus NDJSON, partial/invalid frames, notifications/error codes/stdout purity. |
| 10 | Complete storage migration/release/platform gate | All commands; known schema versions/legacy variants, synthetic-copy crash interruption/restart/rollback, signals/broken pipe, locked reproducible Mac/Windows/Linux target runs, licenses/notices/package validation. Other hosts currently unauthorized and unverified. |
| 11 | Optional research improvements | Separate commit/PR after full reference baseline comparison; parent supplies paper review; adopt only measured evaluation gains within existing cost/network limits. No inferred speed claim. |

Stages can be split into reviewable vertical PRs. The golden matrix is in golden-matrix.json; every pending row blocks a complete-migration claim. An adapter trait or an offline parser alone never marks a provider/command complete. Final acceptance requires native CLI/library/storage/report/error behavior, real target execution evidence, explicit approved intentional differences, no Python runtime dependency, and all pending rows closed. Live provider certification is tracked separately; it remains unverified unless narrowly authorized. No automatic production cutover follows acceptance.

## Reproducibility, recording and cost

Rust/MSRV 1.96.0 and Cargo.lock are fixed. Existing CI public-runner matrix is unchanged; Rust gates are local aarch64 macOS evidence. One CPU/build job at a time. The recording cap is min(10% starting free space, 2 GiB) for source/fixtures/logs; monitor build storage separately. Inspect sizes before a new build, reuse a single owned target with sequential builds, retain compact fixtures/commit evidence, avoid cumulative raw logs/downloads, and remove only recoverable self-generated build cache when idle. Never remove user archives, credentials or someone else's cache/dirty files. Provider fixtures reject unscripted requests; localhost fixtures bind only loopback. Official registry dependencies only, zero paid API/model/live search calls, no OS/network/auth configuration changes.

Three-OS execution remains pending; the existing Python-only CI is explicitly distinguished from native target evidence. Cost-bounded proposal: [platform-gates.md](platform-gates.md).


Remaining-provider checkpoint 7a implements GitHub code only in the separate codex/rust-remaining-provider-parity worktree. Dependency PR #23 repaired head c728562 remains unmerged; a feature PR uses codex/rust-provider-edge-parity as stacked base and discloses both heads. Repair-first dependency review, approved main retarget and affected native gates precede integration. GitHub repo subprocess fallback, OpenAlex and meta remain the next native providers. Every final acceptance row remains pending.

PR #23 repaired c728562 and #24 2f67545 passed independent source/fixture/CI review and explicitly authorized normal integration as main 6fce86e then 5a2ee67. Retarget tree equivalence was confirmed; native/TLS evidence remains author-only. The next-provider worktree starts at integrated main5a2ee67. All final acceptance/OS/live/cutover gates remain pending.

Slice 7b now implements native GitHub repository Unix gh-to-REST fallback with owned subprocess fixtures; 51 adapter/30 CLI cases and 5 raw/8 safety process checks pass. Two providers, OpenAlex and meta, remain. Scoped evidence is recorded without closing final acceptance; Windows process implementation, Linux execution, full signal/data/downstream/release gates remain pending.

PR #25 repaired eda15e2 was normally authorized/merged as main e91513bc0516b328d6432ba73d293343b8b3af42, with tree equivalence and fresh exact head/base/protection/threads/CI readback. Slice 7c follows that main and implements native OpenAlex search (95 transcript/13 identifier/34 CLI cases) plus frozen language facts. It does not implement graph/cache. Meta remains the last component provider; downstream features and all final storage/report/platform/release gates remain. Every pending acceptance row now names reasons; scoped passed cases and final scope are separate.

Local slice 7d starts on Draft #26 exact91da387. Native Meta component/fusion/worker/ledger code has controlled offline evidence; CLI remains gated. Meta contract lists combined-provider CLI/config/archive/error/signal/panic/history/model acceptance still required. Matrix has 13 scoped passing records and 35 pending final rows. This checkpoint is local and has no separate PR/release or integration authorization.

Current slice 7d follows normally merged #26 repaired5dffce0/main186511a. Native Meta
CLI is enabled for the measured normal scope, including four-worker fanout, fusion and
selected health ledger. Combined37 pairs/signal4 executions/output-schema5 pairs pass;
controlled262 component inputs/33 transcripts and native policies remain applicable.
Detailed CLI coverage records167 leaf pairs + one root version pair; native MCP0/9.
Every one of35 final rows now lists specific missing assertions, proposed test IDs/files
(execution_evidence=false), passed scopes and a closure condition. No final row closes
from aggregate pass counts. Next native feature is direct/Jina/auto read with FetchError
fallback and selected cache writes, then collect/enrichment/report dependencies.
Ledger commit/panic, total-resource caps and actual OS/release/storage gates remain
separate mandatory work. Paper-driven changes remain a separately evaluated commit.

Direct-reader slice follows maincb79a8a (#27 normal8940c integration).51 response
fixtures,36 normal CLI pairs,six scoped cache/error pairs and two owned HTTP-wait
SIGINT executions pass. Real SQLite writer-lock and TEMP-abort preservation pass;
commit/crash/OS gates stay open. Next dependency is Jina reader and FetchError-only
auto fallback, then positive enrichment/collect/report and MCP adapters. Actual
MCP inventory is9 tools/native0; old7-tool prose is corrected, not a schema change.

Jina/auto reader slice now follows repaired #28 head75e7980, with93 request/response
transcripts,44 paired CLI cases,7 separate byte-policy assertions and2 actual HTTP-wait
SIGINT executions. All9 MCP tool dependencies account for all35 rows,0 native tools.
Output cap before cache write and trusted/untrusted target policy are explicit gates.
Next native dependencies are positive search enrichment, collect evidence/report,
then brief/investigate/eval and MCP adapters; graph/cache/repo/issues ingestion remain
parallel final command requirements. No final row is closed by the reader preview.


#28 repaired75e7980 and #29 exact0e9c5de were independently reviewed and normally
merged to main08052376 thencc086afb. Trees match their approved heads. The next
separate enrichment slice follows integratedcc086afb, enabling sequential direct/
Jina/auto before signed slicing with57 Python raw transcripts and52 paired feed/
SearXNG CLI cases plus2 owned HTTP-wait SIGINT executions. No archive write is added.
Collect is next: native store_run/report still missing, and Python failed-capture
upsert can overwrite a successful cached page. Review that concrete retention policy
before implementation; preserve run/page commit boundaries rather than claim whole-
command atomic rollback. All35 final rows remain pending; native MCP0/9.


PR30 P2 repair supersedes the preceding runtime-enrichment checkpoint. Provider-
derived URLs crossed into trusted local reader/network behavior. Positive CLI
enrichment now fails before provider/reader/archive I/O; algorithm API is concrete
OfflineTransport only. No runtime network entry point or native enrichment completion
claim. Derive/pin/validate public targets and redirect/proxy/DNS plus Jina transmission
policy in a separate reviewed slice before enabling search, collect or investigate.

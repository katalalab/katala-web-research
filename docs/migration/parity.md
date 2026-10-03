# Rust migration contract and completion gate

Reference: public repository ID 1251159956, main e66e449cc210bd80ecb25a00391091e72abd9c2b (2026-10-03). Dedicated clone; no existing checkout edited. Open PR collection was empty; five remote branches contained no Rust branch. App thread inventory showed no second active Rust migration. AGENTS.md and CONTRIBUTING.md apply; no repository .agents/skills found. Recording budget: min(10% starting free space, 2 GiB), currently 2 GiB; build targets are monitored separately and reused. No credentials, real archive, company repository, other host, paid provider, or live search used.

`python-contract.json` is generated from all 22 leaf commands, argparse defaults and choices, dataclass fields, handler JSON literals/exit branches, every environment reference, all SQLite DDL (tables, indexes, FTS shadow tables, triggers), and all nine MCP tool schemas. Regenerate with `PYTHONPATH=src python3 scripts/migration/inventory.py`. It supplements this behavioral ledger; AST literals are not a complete execution trace.

| Surface | Python contract | Rust gate / current status |
|---|---|---|
| version / parser | kwr 0.1.0; argparse error 2, runtime error 1, success 0; UTF-8 sorted indent-2 JSON | Native CLI foundation; parser/help wording may differ and must be recorded |
| plan | collapsed whitespace, baseline/official/primary/critique/freshness, ordered dedup, existing nonpositive max returns first step | Native implemented; differential and committed golden fixtures |
| sources list/match | bundled JSON, overlay KWR_SOURCE_REGISTRY_OVERLAY keyed by domain/type/name; exact normalized host; prefix path boundary; trust/name ordering | Native implemented; boundary/overlay differential tests |
| query | pages FTS5, quoted whitespace tokens with quotes stripped, AND semantics, bm25/snippet, empty results | Native implemented; shared SQL schema and differential ranking |
| repos query | FTS5 six columns, context weighting, inline repo:/path:, explicit filters win, escaped LIKE | Native query implemented; scanner remains pending |
| feeds query | FTS5 summary snippets with source/published/fetched fields | Native query implemented; normal RSS/Atom/JSONFeed file/HTTP(S) refresh implemented; parser/transport edge parity pending |
| feeds add | upsert source without resetting health or added_at, empty strings preserved in CLI payload | Native implemented; differential archive writes |
| feeds refresh | source selection/order, RSS/Atom/JSONFeed, per-source error health, upsert without deleting absent old items | Native file/HTTP(S) refresh, environment proxy, common charset, TLS and error retention fixture gates; deliberate safety bounds in http-contract.md; OS proxy/full codec/URL edges pending |
| issues query | FTS5 title snippets, labels JSON, computed item_key | Native implemented |
| issues ingest/report | synthetic --from-json parsing, priority/status/phase ordering, Markdown radar; live gh search | Pending |
| engines | last N/provider, nearest-rank p95, rounded rates/health, weak engine routing flag | Native implemented |
| read | HTTP(S) only; auto Jina then direct on FetchError only; charset header/meta sniff; cache upsert/refresh | Native direct/cache hit/miss/refresh preview; auto/Jina fallback and full URL/codec/lifecycle/OS/live parity pending |
| search | ddg/feed/github/github_code/jina/searxng/brave/openalex/meta; query filters, candidate oversampling, enrichment, highlights | Native normal paths for all nine providers, including Unix gh/op and Meta fanout/fusion/ledger; positive enrichment, malformed/transport/lifecycle/OS/live final assertions pending |
| collect | run/results + selected pages, errors stored as source=error; optional UTF-8 evidence report | Pending |
| repos scan | bounded traversal, skip artifacts/private data, encoding candidates, incremental size/mtime/hash/context | Pending |
| brief / investigate | plan expansion, quality ranking, local/feed evidence, selected captures, provenance/checklist/report output | Pending |
| doctor | provider configuration posture plus actual SQLite FTS5 probe; optional SearXNG preflight | Pending |
| openalex expand | ID/DOI normalization; direction references/citing/both, bounded 50, cursor paging/cache reader | Pending |
| eval | deterministic 80 threshold, source/plan/rank/domain metrics, Markdown report, failing exit 1 | Pending; baseline suite retained |
| mcp | 2025-11-25, nine tools, initialize/list/call, JSON-RPC error codes, Content-Length UTF-8 byte framing CRLF | Pending; preserve legacy Content-Length framing and add official NDJSON compatibility explicitly; test notifications, partial/invalid frames, stdout cleanliness |
| migration | Python user_version=0; implicit repo columns/context FTS upgrade on open | Implemented copy-only migration; source read-only, version/fingerprint checks, atomic transaction, validation/rollback |

## Storage and security constraints

Default archive is **relative** `.katala-web-research/archive.sqlite`, not the home directory examples in README. `KWR_ARCHIVE` routes feed/meta health in library calls; CLI selected archive temporarily overrides it. No tilde expansion occurs for the archive argument in Python. WAL mode; four external-content FTS5 indexes and insert/delete/update triggers; UNIQUE keys for pages URL, repo(path,relpath), feed(source,url), project(kind,repo,number). Engine ledger prunes to 500/provider. SearchResult metadata is deliberately not persisted by store_run. Exact DDL and public JSON model fields are in the generated contract.

HTTP default timeout 20 seconds, optional positive KWR_HTTP_TIMEOUT_SECONDS; gh repo search timeout 30 seconds, op read 10 seconds; meta workers at most four. No general automatic HTTP retries in Python. Provider-specific fallback (gh to REST, github_code query repair, Jina reader to direct, meta partial successes) must remain observable. URL userinfo/secret query keys are redacted before diagnostics. Rust must also avoid reflecting credential-bearing error bodies/redirect URLs. Credentials remain environment-only; OPENALEX_API_KEY op:// support needs a bounded subprocess implementation, never credential inspection during tests.

All environment variable names and occurrences are enumerated, including registry overlay and provider localization/date/bool filters. HTTP(S)_PROXY/ALL_PROXY/NO_PROXY behavior is a platform dependency and requires synthetic tests before networking migration is accepted.

## Cross-platform design

Pin an already-installed Rust toolchain and MSRV with Cargo.lock; use native Path/OsString for filesystem paths and UTF-8 for persisted text/output. Bundle SQLite with FTS5 to remove OS SQLite variation. TLS must verify certificates, allow standard corporate proxy trust without disabling verification, and have synthetic timeout/proxy tests. Bounded threads (four meta workers); default retry zero to preserve requests/cost, explicit provider retry only with fixtures. Handle Ctrl-C and broken pipes without corrupting transactions; MCP framing counts UTF-8 bytes and writes CRLF only in headers. Preserve timestamp format seconds plus +00:00. Windows/Linux are design targets, **unverified** until actual runs; this work uses only the authorized local Mac.

## Completion conditions

A complete migration requires every pending row implemented natively, no Python runtime invocation, command/JSON/exit/report/provider differential gates, matching schema/content/index/cache semantics, offline reference suite coverage and deterministic evaluation, bounded networking/security/fallback tests, copy migration version rejection/dry-run/idempotence/interruption/rollback, and actual Mac/Windows/Linux build/test evidence. Live providers are separately marked unverified until authorized checks. Do not replace installed CLI, switch real archives, remove Python reference, or claim full migration while any row remains pending. A preview slice may enter main only after explicit integration authorization, independent review and exact-head required checks; that does not satisfy the complete-migration gate. Research-driven features get a separate evaluated commit.

Execution order/dependency heads: [roadmap.md](roadmap.md). Machine-readable final acceptance inventory: [golden-matrix.json](golden-matrix.json), checked by `python3 scripts/migration/check_matrix.py`. Every final row remains pending; current preview evidence does not close the final gate.

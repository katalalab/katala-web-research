# Meta migration contract and completion gates

Reference: `providers.py:MetaSearch`, `_run_meta_provider`, `_meta_*`, `fusion.py`,
`engine_health.py`, and `archive.py:record_engine_runs/engine_runs` at
`91da3879ee84e8226f858da7d812e0ccb2d898e3` (Python implementation unchanged).
Current native CLI slice follows integrated main `186511a102d241dd207d9b616c00b94bfd16537e`
(PR #26 repaired head `5dffce09d2a04c1281dc36c1149b44823d80902e`).
The earlier component checkpoint below records its historical CLI refusal.

## Required parity

- Seven profiles; unknown/blank profile becomes broad. Explicit comma-separated
  `KWR_META_PROVIDERS` trims Python whitespace, excludes meta/unknown names, preserves
  duplicates and order. Empty explicit value uses profile defaults.
- Only `KWR_ARCHIVE` enables the health ledger in the library. CLI passes its selected
  archive. Read the last 50 runs per provider; route around weak engines only after
  five samples and retain the original names if every engine would be removed.
- Rewrites depend on profile/provider. Each engine gets `max(2, min(limit, 8))`,
  including zero/negative outer limits. At most four simultaneous engine jobs.
  Completion order influences equal-rank representatives; do not impose a new tie rule.
- Provider errors become empty engine results with class-only `error_kind` and zero
  health. Successful empty results have status empty/health 0.35. Rounded elapsed
  milliseconds and 1/2/5 second health penalties retain the reference thresholds.
- Annotate engine results; weighted reciprocal rank fusion uses denominator 60+rank,
  canonical URL keys, minimum ranks, maximum per-source health, and 6-place Python
  rounding. Then run existing lexical/quality/freshness/diversity ranking on the
  original query and apply Python signed slicing. Profile/provider/run metadata is
  attached after ranking; run annotations are sorted by provider, stably for duplicates.
- Record run completion order in one transaction, common timestamp, prune to 500 rows
  per provider. Other seven user tables and FTS data remain intact. Errors opening,
  routing, or recording an explicitly selected ledger propagate. Existing Rust
  schema-version refusal/copy migration is an explicit safety policy, not Python parity.

## Scoped CLI enablement gates

1. Python-generated profile/rewrite/health/fusion goldens with complete result metadata,
   duplicate sources/URLs, fallback ranks, Unicode, signed limits and discard gates.
2. Strict scripted engine completion transcripts with exact requests/order/call counts;
   no fixture may fall through to network or installed executables.
3. Bounded native concurrency, all-jobs-drained behavior, and completion tie tests using
   owned fixtures. Timing values are measured; controlled clocks compare the algorithm,
   real clocks are not asserted byte-equal between two separate processes.
4. Synthetic archive differential tests: 50-row routing, all-weak fallback, duplicate
   providers, 500-row prune, selected archive only, preserved unrelated data, transaction
   failure/rollback, schema refusal, SQLite integrity, and no silent write-failure success.
5. Paired CLI JSON/text/options/exit/error tests using only loopback services and owned
   process fixtures; redacted failures and absent configuration must be verified.
6. fmt/clippy/locked offline native tests and affected inherited goldens, reproducible
   build, ledger/matrix update. Native Mac evidence only; Windows/Linux native execution,
   live providers, real archive cutover, graph/cache/downstream commands and complete
   migration remain pending.

The ordinary preview CLI is now enabled with the combined evidence below. These gates
do not close full contract acceptance: commit/panic/representation/OS/live assertions
remain concrete in the matrix. Pure components are evidence only for their functions.

## Historical local component checkpoint (7e6f3b8)

The native component layer implements profiles/rewrites, engine annotations, health
weights, fusion/rank/signed slicing, exact offline completion adapters, bounded scoped
workers and transactional ledger writes. The existing CLI still refuses Meta; it cannot
silently access native engines through this checkpoint. No release or PR publication of
this partial slice is claimed.

Executed on the author's aarch64 macOS: 60 profile/rewrite, 168 health boundary,
32 fusion input and two annotation oracles (each fusion input additionally compares six
limits); 33 deterministic full-search transcripts, exact request/completion/ledger call
counts; strict fixture refusals; native four-worker bound and all-eight-jobs drain after
an engine error; completion order controlled by a private after-send observation, with
no sleep-based ordering assumption or production fault knob; synthetic archive 500-row
prune/50-row routing/transaction rollback/seven-table preservation and FTS query/integrity.
Both oracle generators replay byte-identically. All locked offline native tests and
warnings-denied all-target clippy pass. Scoped matrix evidence records these cases while
every final acceptance row remains pending.

At that checkpoint still required: combined provider/CLI loopback fixtures, archive
selection/environment parity, no-write-without-library-ledger behavior, CLI text/JSON and
partial/all-error exits, graceful interruption and worker-panic semantics, nonwritable
ledger/version refusal policy cases, broader history-window/threshold/duplicate/ordering
and unusual floating-string/model representations. Real elapsed times and completion
order are measurable inputs, not two-process byte-equality promises. Native scoped
thread panics currently propagate; they are not ordinary provider error results. No
Windows/Linux execution or live service evidence exists.

## Combined native preview and oracle boundary

The normal native `search --provider meta` path uses the existing adapters, at most
four scoped workers, completion-order fusion and transactional engine ledger. It never
executes Python. Explicit CLI archive selection is passed without changing global env;
the library uses KWR_ARCHIVE only if present/nonempty. No library ledger path creates
an implicit archive. Empty CLI archive is accepted as Path("") = current directory,
then fails on directory open as Python does; it cannot become an anonymous SQLite DB.
Known full version-0 schema is accepted; future version 2 and pre-context legacy schema
are refused unchanged, with legacy copy migration required.

Author Mac evidence: 37 paired combined CLI/library cases and four owned signal
executions (SIGINT/SIGTERM in Python and native), plus five separately measured output
schema pairs/26 native returned rows across all eight component sources. JSON/text,
profiles/options, duplicates, partial/all errors and empty results, thresholds/recent
history/pruning, selected/unselected eight-table archives, FTS/integrity and explicit
schema/path refusals are exercised. All native tests and warnings-denied clippy pass;
218 inherited offline CLI comparisons pass at this source. This aggregate allocates
167 observed leaf cases plus one root --version case; 50 other assertions are not
inflated into per-command coverage. Native MCP remains 0/7. These are author-only
actual aarch64 macOS observations, not native Linux/Windows or live service evidence.

Two real executions have different clocks/completion order. The reference child runs
unchanged Python CLI/provider code while a test-only recorder saves its raw component
results and requested provider/query/limit vector. Each execution's SQL ledger timing
and order are supplied to a no-I/O Python replay. The replay independently checks the
exact worker bound/submitted requests/completion multiset and status/result-count/error
classes, recomputes health from recorded latency, reannotates raw **Python** results,
and executes Python fusion/ranking/CLI rendering. Full native JSON/text, health, score,
rank and metadata must equal that replay; no native result is used as expected content.
HTTP URL/header trace multisets and expected ledger providers are also checked. Only
timestamps/latencies are normalized in secondary ledger comparisons after full output
checks; elapsed inputs are bounded by each child fixture deadline.

Freshness is local to each compare: a new synthetic archive and reference transcript
are created, native executes once with identical input fixture configuration, no saved
native outputs or previous oracle transcripts are loaded. Exact production content
hash is recorded with coverage. The unchanged reference src tree is compared with
integrated main. Independent controlled goldens check timing penalties/rounding and
completion representatives, and the native channel/four-worker tests check execution
behavior. Replay does not prove identical OS scheduling or wall-clock speed. It only
observes returned fused rows, so dropped pre-fusion result/model edges rely on component
transcripts and remain open where untested. Duplicate providers in these loopback cases
have identical raw requests/results; differing duplicate completions use fixed goldens.
Weak routing and archive writes are checked on actual child databases, not by replay's
no-I/O replacements. No benchmark or performance gain is inferred.

Worker-time interruption returns native 130/143 versus Python subprocess -2/-15,
matching shell signal exit semantics. Fixture stdout is empty, all archive contents stay
unchanged, and owned descendant heartbeats stop. This is an explicit raw-exit difference
pending policy acceptance. Busy SQLite/commit-window signals, worker panic payload
redaction, ignored/custom dispositions, SIGKILL/power loss/detached descendants remain
unverified. Checks before ledger writes cannot prove an interrupt arriving during commit
leaves no committed runs. Per-response 8 MiB is not a total-result/abstract allocation
bound. Named missing assertions/proposed files for every final row are in the matrix;
proposed tests have execution_evidence=false and cannot count as passed.

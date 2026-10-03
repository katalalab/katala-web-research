# Meta migration contract and completion gates

Reference: `providers.py:MetaSearch`, `_run_meta_provider`, `_meta_*`, `fusion.py`,
`engine_health.py`, and `archive.py:record_engine_runs/engine_runs` at
`91da3879ee84e8226f858da7d812e0ccb2d898e3` (Python implementation unchanged).
This slice starts on Draft PR #26; it must be integrated after that exact base is reviewed.

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

## Acceptance before enabling the CLI

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

No Meta CLI support is claimed until all six gates are recorded. Pure component tests
are evidence for their named functions only, not final acceptance of the Meta command.

## Local component checkpoint

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

Still required before enabling Meta: combined provider/CLI loopback fixtures, archive
selection/environment parity, no-write-without-library-ledger behavior, CLI text/JSON and
partial/all-error exits, graceful interruption and worker-panic semantics, nonwritable
ledger/version refusal policy cases, broader history-window/threshold/duplicate/ordering
and unusual floating-string/model representations. Real elapsed times and completion
order are measurable inputs, not two-process byte-equality promises. Native scoped
thread panics currently propagate; they are not ordinary provider error results. No
Windows/Linux execution or live service evidence exists.

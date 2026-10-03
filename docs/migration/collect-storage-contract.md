# Collect storage slice (saved before implementation)

Starts from integrated main83f2cf83 after PR30. This first slice implements only the
native Archive store_run primitive with controlled clock and synthetic copies; native
collect CLI, derived page capture and report/event writers remain unimplemented.
Use existing schema/Archive/SQLite; no migration, dependency or environment changes.

Python Archive.store_run inserts one runs row(query,provider,UTC created_at), then
search_results in input order, storing run_id/rank/score/title/url/snippet/source/
published_at. Result metadata is not persisted. It does not rerank/deduplicate or
validate URL/provider. A zero-result run still commits and returns its rowid.
Each successful call commits once; repeat calls append different run/result rows.
Separate page upserts/report creation are not part of this transaction.

Native stores the same columns and returns SQLite rowid. Explicit transaction RAII
rolls back the entire new run/result batch on insertion failure before returning.
Python can retain an uncommitted partial batch on the open connection after an
exception; Archive.close rolls it back. Document this immediate-rollback difference;
compare persistent source preservation after close, not pending uncommitted state.
Do not treat SQL abort/lock tests as SIGKILL/power-loss recovery evidence.

Acceptance for this scoped primitive:unchanged-Python sequential run/result oracles,
empty/repeat/duplicate/Unicode/null-versus-empty/publication/rank/score boundaries,
clock called once, input metadata ignored, original eight synthetic tables/schema/
version/FTS integrity maintained. Test actual competing writer and TEMP trigger
failure on a later result, whole batch rollback, unchanged previous runs/pages and
same connection usable after rollback. Copy-only reopen verifies durable success.

Collect orchestration is later:run/result commit first, each successful page commit
separately, archive close, then report write. A report error does not roll back already
committed data. Capture failure must not change any existing page, including an older
error row:retain the failure separately in report/event evidence. Parent recommends
this concrete retention policy; field/redaction/event/report behavior still requires
a separately tested implementation and named Python difference. No schema change or
existing-page overwrite is authorized by this primitive.

Derived capture remains fail-closed until derived-target-policy-roadmap.md gates are
implemented. This slice adds no runtime network or credential call, installed CLI/
archive cutover, complete collect acceptance or performance claim.

## Native primitive checkpoint

Archive::store_run/store_run_with_clock write one new run/result transaction and
return its SQLite rowid. Each successful call commits independently; errors roll back
before return. Native collect/capture/report/event callers are not enabled. The probe
is an owned differential example, not a shipped capture command. Cargo adds only test/
example declarations; dependency/lock/toolchain/schema/workflows stay unchanged.
Source SHA256af7994bab2e31fba30061a5811ba31945e81b3a41cb6bab68993183c3f56291d.

Author aarch64 macOS evidence:28 unchanged-Python sequences/57 commits with exact
rows/rowids/order, once clock, empty/duplicate/repeat/Unicode/NUL/null-or-empty dates,
i64/finite-score boundaries/ignored metadata and durable reopen. Default clock also
proves UTC seconds shape. Fixture92b1e6239cf454965704652bc911e1f08402bf793ba0b2e94667155e19e72631
regenerates byte-identically. Real competing writer and later-result TEMP-trigger
abort roll back the new batch, preserve earlier runs/pages/FTS and allow same-connection
retry. These are SQL lock/abort tests, not process-kill/power-loss recovery evidence.

Twenty-eight paired success sequences +2 paired SQL-abort sequences use eight-table
populated copies, exact user rows/schema/version, four FTS rank1 integrity/positive
MATCH controls, old-row prefixes/expected committed counts and untouched other archive.
Python closes its failed connection; native rollback is immediate. No equivalence of
uncommitted Python connection state is claimed. First fixture used evidence for a
project row containing old; corrected to old while retaining the nonempty control.
Committed-count/prefix checks were added and all30 paired sequences reran. Expected
values are never derived from native output.

Pinned fmt/all-target clippy/all native tests/218 existing CLI pairs, required Python
167/benchmark/smoke/artifact/gitleaks and locked offline debug/release pass; the final
default-clock assertion is also executed separately. All35 final rows remain pending.
Malformed/nonfinite/size/caller-nested transaction/read-only/busy-commit/actual signals/
crash/platform/downstream/real data and full collect/report/event scope remains open.

# Feed collect and pure report slice (saved before implementation)

Starts from integrated main2717b2f after PR31. Native collect supports only
`--provider feed --read-top 0` (negative read-top also skips capture). Preserve
Python defaults ddg/read-top3 so a default invocation fails explicitly; all positive
read-top values and other providers fail before registry, archive, report, process,
credential or transport work. Help describes this partial scope. No derived target
policy, permission bypass, reader call or capture/event/page write is introduced.

Feed retrieval uses the original query and signed limit, without search-command
oversampling, query building or enrichment. Use the selected archive rather than
KWR_ARCHIVE. Store run/results once, close the archive, then optionally write a
report. Preserve receipt fields/run_id/result metadata, JSON and text outputs;
empty report argument means no report. Zero-result/repeated runs still commit.
Existing pages and the other six user tables are unchanged on success or report
failure. Run/results already committed survive report failure; failed commands
emit no success receipt. Error diagnostics include the committed run id.

Pure report rendering preserves unchanged Python Markdown line order, literal
query/fields, score spelling, empty publication/snippet fallback, page scalar700
excerpt with newline-to-space then Python whitespace strip, and one final newline.
Controlled clocks permit exact offline oracles. Pure page fixtures do not enable
runtime capture. Public typed/scalar/nonfinite and aggregate resource gates remain
pending; native preview is not complete collect parity.

Named difference report_noclobber: Python write_text replaces existing paths,
including the selected archive if supplied as --report. User forbids original-data
overwrite. Native reports therefore publish a synced temporary UTF-8 file with
persist_noclobber in the destination directory, rejecting any existing destination
(also symlinks). Missing parents may be created. No delete/overwrite of old reports
or archives; report errors happen after run commit as Python. This is intentional
preview behavior requiring final policy acceptance, not claimed Python parity or
cross-platform/power-loss durability. Report path display follows lexical Path
normalization for tested UTF-8 paths; Windows/native non-UTF8 paths remain unverified.
The temporary-file permission mode is retained (0600 on the tested Unix host),
where Python creates files according to its process umask; this is part of the named
publication-policy difference, not a file-permission parity claim.

Scoped acceptance: independent Python report goldens; paired feed CLI on populated
synthetic copies for signed limits, original-query/duplicate/Unicode/JSON/text/empty
report/repetition/UTC timestamps; compare all eight user tables, schema/version,
four FTS rank1 integrity and positive MATCH, earlier rows and unselected archive.
Report success and directory failure preserve commit boundaries. Existing report,
archive collision and symlink tests prove named no-clobber behavior. Refusals prove
zero runtime files with invalid provider/network settings and empty executable PATH.
No live API, real archive, private network probe or other-host test is used.

All35 final acceptance rows, native MCP0/9 and migration cutover remain pending.

## Native checkpoint evidence

Source d4c486eca806f23b12259120754a39f38903f533bfc91b70cd547adbe4bca71c implements
only the scoped feed/no-capture CLI and pure report/new-publication API.96 Python
renderer goldens regenerate byte-identically (SHA256d131812bbc5881034c1b45ccd2544fd3386b4b96f2b25efbbec60b7f8f8e36d0).
48 strict paired CLI cases plus2 paired actual SQL-trigger/report-directory failures,
80 pre-I/O refusals and4 publication-policy cases pass. JSON/text/repeated receipts,
old good/error pages/all8 tables/schema/version/four FTS indexes are asserted.
File-mode0600 is verified on this Unix host. Invalid network/registry/helper settings
cannot bypass capture/non-feed guards; focused help creates no runtime file.

Pinned fmt/clippy/all native/218 existing CLI comparisons, required Python167/
benchmark/smoke/artifact/gitleaks and locked offline release pass on author aarch64
Mac only. No schema/dependency/lock/toolchain/workflow/permission/cost change; no
native capture/event/MCP/other-provider collect/full parity or actual crash/other-OS
claim. All35 final rows remain pending with concrete missing assertions and tests.

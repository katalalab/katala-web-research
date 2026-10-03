# Enrichment and collect boundaries

Next independent slice starts from integrated main cc086afb (#29). This contract
is saved before implementation. No real archive, credential or live provider is used.

## Search enrichment

Python workflow.enrich_search_results returns its input unchanged when read_top<=0
or the input is empty, without validating reader or reranking. Positive enrichment
reads the first read_top candidates sequentially in their initial order, including
duplicate URLs that ranking may later discard. It never reads or writes the archive.
Use the existing native reader/Transport and shared ranking; do not duplicate providers.
Redirected page URLs do not replace result URLs or provider source/publication fields.

On success copy metadata, set read_status/read_source/read_status_code, use the page
title only for an empty result title, and replace snippet only with nonempty page
content collapsed with Python whitespace rules and truncated to 700 Unicode scalars.
Do not HTML-unescape this plain content. Existing read_error_kind is retained.
On Exception copy metadata and set read_status=error/read_error_kind to the class
name; retain old title/snippet/read_source/read_status_code. Diagnostic messages are
not persisted. BaseException/actual signal termination is not an ordinary read error.
Finally rerank every result with the original query, not the built provider query.

CLI order: build query; search with candidate limit; annotate all candidates;
enrich; signed result slice; cached highlights and rerank; another signed slice;
render. Zero/negative final limits do not suppress positive candidate reads.
No parallel reads/retries or new cache write is implied. Reader output cap belongs
to the read CLI and does not bound aggregate search/enrichment memory or stdout.

Acceptance requires Python-generated raw input/read transcript goldens, strict request
order/clock/error-kind checks, Unicode700 boundaries, no-op cases, duplicate/discard
order and stale metadata, plus paired CLI candidate/signed slice/category/highlight
cases. Synthetic selected/unselected archives must retain all eight populated tables,
schema/version, MATCH results and FTS rank1 integrity. Invalid reader is lazy when
no page is read. Owned HTTP-wait signal tests remain separate from mocked exceptions.

## Collect is a later slice

Python cmd_collect searches the original query with the direct limit; it does not
use enrichment, query building or candidate oversampling. store_run commits runs
and search_results first. Each subsequent page upsert commits independently.
The archive closes before optional report parent mkdir and UTF8 write. A report
failure can leave a committed run and pages. Whole-command atomic rollback is not
the Python contract. Native store_run and collect are currently unimplemented.

Python catches ordinary read exceptions and upserts an error PageSnapshot with
`Read failed: {exc}`, potentially overwriting a previously successful cached page.
This conflicts with preserving successful data on failed fetch. Before implementation,
review a concrete policy: retain failure evidence in payload/report/run while keeping
the successful page; do not silently label this changed behavior as Python parity.
No real archive mutation or installed CLI/data cutover is authorized.

Report excerpt is content[:700].replace(newline,space).strip(), unlike enrichment's
whitespace collapse. Preserve Markdown order/empty defaults and Python float spelling;
test UTF8/Unicode700, score formatting, error redaction and generated timestamp shape.
Copy-only fixtures must test run/result transaction abort, per-page commit boundaries,
repeat runs, report permission/write failures and actual before/during/after-commit
interrupt/restart. Fault-injected SQL rollback does not prove crash recovery.

## URL transmission policy

Python-compatible Jina reader quotes the complete target URL, including query,
fragment and userinfo, into a request to r.jina.ai. Masked diagnostics do not authorize
that disclosure. This trusted opt-in CLI contract must not become the default for
untrusted MCP input or confidential URLs. Before those surfaces are enabled, require
explicit transmission policy plus initial/resolved-address/redirect/proxy authorization.
Native MCP remains 0/9; no untrusted adapter or live Jina validation is enabled here.

Full migration remains pending across all35 acceptance rows, other OS targets,
resource/release/security gates and live providers. No speed claim is made.

## Enrichment implementation checkpoint

Native workflow::enrich reuses reader::read_with and shared rank, and CLI search now
enriches before the first signed slice. No dependency/version/lock/toolchain change;
Cargo.toml adds only the workflow test target. Python remains an oracle only.
Source content SHA256:0930d484d0858a299732b34cfc75f3b02ac5d3ca7a047495820ef630a9024485.

Author aarch64 macOS evidence:57 raw Python workflow/reader/rank/request/clock/error
transcripts; fixture SHA256:7c1958a92f1ca10cd9c02b5ea5b7097ae40d5bf4114f836390be8369ef48afbb.
Forty paired feed→reader CLI cases and12 additional SearXNG→reader cases pass, including
JSON/text, direct/Jina/auto, oversampling/signed limits, failure/fallback, category,
domain and cached highlights. Synthetic seed timestamps are fixed; result fields,
rank/score/metadata/URL/source/render/request traces compare exactly.
All eight synthetic user tables, schema/version/pages MATCH/rank1 integrity and
unselected archive remain unchanged. Two actual owned TLS HTTP-wait SIGINT executions
return the reference raw signal code with empty stdout and unchanged synthetic data.

Initial combined fixture mistakes selected its old seeded feed, collapsed distinct
URLs at provider dedup, and treated an invalid CLI reader as a lazy library value.
Correction removes only owned synthetic feed rows before each execution, supplies
two loopback hosts, and respects existing CLI parser choices. The57 library cases
still cover lazy invalid-reader behavior. No native output was used as an oracle.
Forty successful pairs/signals were retained; only12 added network-search cases ran.
The old uncounted positive-enrichment refusal assertion is superseded by these
implementation comparisons; the218 counted baseline comparisons remain unchanged.

All-provider combined enrichment, adversarial typed/ranking inputs, per-command
aggregate resource caps, actual Windows/Linux/live execution and full lifecycle
remain pending. Collect/storage/report implementation and policy review are separate.

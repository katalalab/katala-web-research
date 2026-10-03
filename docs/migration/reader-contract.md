# Native direct reader vertical contract

This separate branch starts at fixed Meta #27 head8940c1f; that head is unchanged.
Priority from actual code: MCP has **nine** tools, not seven. `read`, `investigate`,
search enrichment and collect require read_url; eval and brief also have unfinished
native dependencies. Therefore direct read/selected cache is the smallest useful
vertical slice before completing all MCP adapters. Inventory and coverage already
contain nine exact schemas; historical prose 0/7 is corrected to native 0/9.

Implement direct HTTP(S) validation before network, existing Accept/header/response
codec/meta charset sniff (first4096 bytes), existing HTML extractor/plain strip,
redirect response URL and seven PageSnapshot fields. Uncached read never opens an
archive. Cache hit retains original reader-agnostic behavior; direct miss/refresh
upserts by returned URL, commits atomically and emits cached=false or cache:miss.
Preserve seven unrelated tables/schema/FTS/integrity and previous content on failure.
Auto/Jina network paths remain explicitly refused until their FetchError-only fallback
contract is implemented; no wrapper, dropped functionality or complete-read claim.

Scoped gates: Python raw-response/request/clock goldens; loopback CLI JSON/text,
charset/redirect/cache hit/miss/refresh/error and selected/unselected archives;
transaction abort against an owned TEMP trigger is injection evidence only. Owned
CLI delayed-response SIGINT with source snapshot is an actual worker-time test,
not evidence for signals during SQLite busy/commit. A future commit/crash test must
control an owned real process with real SQLite locks/transaction boundaries and
verify source/version/FTS recovery after restart; a mocked commit cannot close it.
No real data, credential/API key, installed CLI or live Jina/network access.
Native Mac evidence only; all35 final acceptance rows remain pending.

Existing HTTP safety differences/codecs and shared malformed HTML limits are inherited,
not silently certified. Unknown Python codecs unsupported by encoding_rs, malformed
URL/UTF8/HTML branches, busy/commit/panic/broken pipe and actual OS/live remain pending.
No PDF extraction is present in the reference direct reader: non-HTML bytes use the
ordinary response text codec. Broader reader/enrichment work will follow separately.

## Executed scoped evidence

Author aarch64 Mac:51 Python raw-response/request/error/clock fixtures and byte-identical
oracle regeneration pass. Direct normal CLI36 pairs pass (JSON/text, six response
variants, uncached/cache miss/refresh). Scoped six cache hit/failure pairs pass after
test expectations are corrected to Python cache-hit and error-body behavior; native
HTTP body-free diagnostics are an inherited safety difference, not exact Python text
parity. Fixtures preserve seven unrelated populated tables/schema/version/unselected
full archive, pages FTS and integrity. Other FTS data are not independently dumped
in this fixture, so full index corruption coverage remains pending.

Two owned SIGINT executions during actual delayed HTTP request preserve archive
contents and stdout; default raw -2 exit agrees with Python. Actual competing SQLite
writer lock and owned TEMP-trigger transaction abort preserve old page/pages FTS and
integrity. The latter is fault injection; neither proves commit-window cancellation.
Prior passed Meta/provider stages remain inherited at their exact source hashes.
All35 final rows remain pending and native MCP remains0/9.

## Independent P3 index-proof repair

The old external-content SELECT/integrity_check alone did not prove inverted index
entries. An owned negative control removes one existing index entry while page/FTS
external-content SELECT still returns the same data. The old state helper fails to
reject it; repaired helper runs FTS integrity-check with rank1 and MATCH result
snapshots, and rejects this inconsistent index. Two focused paired cache miss/refresh
cases assert new atomic MATCH count1 and old-term removal0 for the fetched URL.
Production Rust/fixtures51/previous42 expectations are unchanged; only these focused
new assertions are executed on the immutable9451 binary. Full other-index/commit
crash/OS gates remain open. No all-feature rerun or direct-reader new feature here.

Trusted network-opt-in CLI may read local/private URLs; a future untrusted MCP adapter
needs a distinct initial/resolved-address/redirect/proxy target authorization policy.
Do not infer untrusted permission from CLI acceptance. This is gate:network final work.

# Native Jina/auto reader slice and target boundary

Dedicated branch starts from repaired #28 head75e7980. No prior direct feature rewrite.
The actual9 MCP names are mapped in mcp-tool-dependencies.json to all35 existing
acceptance rows (including non-MCP command rows). check_matrix.py requires exact
reference schema names,9 tools, all35 rows accounted for and native0/9. This mapping
is not protocol/tool execution evidence; each row retains concrete final assertions.

Jina GET uses r.jina.ai plus quote(target,safe=""), Accept:text/plain, no new key/auth.
Keep original target URL/source jina-reader even when Jina redirects; direct fallback
uses final direct response URL/source direct. Trim content; first nonempty Markdown
line uses strip("# ").strip() then160 Unicode scalars. Recognize only JSON object
error payloads with status/code integer>=400, name containing Error and message key.
Auto catches FetchError only, then direct; other errors stop and explicit jina never
falls back. Failed fetch/refresh never upserts or replaces an existing successful
cache. Real CLI fixtures assert success/error/source/URL/cache/FTS preservation.
Error bodies/reasons and credential-bearing target URLs must not enter native failure
diagnostics. Successful content is user-requested data, not sanitized error text.

Existing CLI read is explicitly network opt-in and supports private/loopback/local
HTTP(S) targets for the user's local research use. This is the trusted CLI contract.
Future MCP/tool URLs may be untrusted: before exposing a native reader, gate:network
must enforce a separate target policy at initial target and every redirect/proxy hop,
including DNS rebinding, IPv4/IPv6 loopback/private/link-local, metadata addresses,
userinfo/credentials, host allowlists/explicit local authorization and resolved-address
connect validation. No untrusted MCP adapter is enabled here. No new auth/network
settings or implicit broad target authorization are introduced. A URL accepted by
trusted CLI is not automatic permission for untrusted tool access.

The quoted Jina target includes the complete query, fragment and userinfo. Diagnostic
masking does not authorize transmitting those values to r.jina.ai. Confidential URLs
and untrusted MCP inputs need a separately reviewed transmission policy before use;
do not adopt this Python-compatible opt-in CLI behavior as their default.

Response-byte cap8MiB is inherited from transport. Tests must exercise exact cap and
one over on owned loopback, source attribution on fallback/redirect, no silent partial
success and original successful cache unchanged after failed fetch/over-cap. Native CLI read output is separately bounded to8MiB including UTF8 JSON/text/newline.
Rendering is buffered within that cap before any cache upsert or stdout publication;
over-cap errors retain prior cache and emit no partial stdout. This new named
reader_stdout_byte_limit policy differs from unbounded Python, pending final acceptance.
Decoded text/aggregate/library-MCP output still lacks a complete reviewed combined
budget; neither per-response nor CLI stdout cap closes total-search/memory gates. No live Jina,
paid API/model, credentials or real archive is tested.

Final actual tests still required: owned process with real SQLite writer lock interrupted
while blocked; controlled before/during/after transaction commit and restart with source/
version/index checks; worker panic/redaction, SIGTERM/SIGKILL/power-loss/descendant and
broken-pipe behavior; actual authorized target runs. Mocked commit/panic or worker-time
signal evidence does not close commit/crash gates. Preserve proposed test statuses and
35 pending final rows. Native MCP0/9 remains unchanged.

## Executed author scope

Exact production content SHA256:
4bf2ce644b69da67b65d58245f3fe92201c296b1aee023b5f0cf02bfbd95d488.
93 Python request/response/error/clock transcripts pass and regenerate byte-identically.
RawValue preserves integer spelling beyond machine bounds without changing shared
Value behavior; only existing serde_json raw_value feature is enabled (MIT OR Apache2,
no new packages/versions/checksums/lock). Unquoted Python NaN/Infinity constants are
replaced for this predicate only; message presence and non-integer classification
are preserved. ASCII Error identity is decoded without losing surrogate-boundary
predicate behavior. Body/domain text is retained unchanged.

44 paired CLI cases:38 normal source/URL/query/fragment/redirect/cache and6 error/
timeout/old-success preservation. Native Jina transport diagnostics redact the entire
opaque target-bearing error URL and all body/reason text; direct errors retain inherited
redacted URL/body-free policy. Successful user-requested URL/content retain reference
fields; diagnostic redaction is not content transformation. Seven separate cap policy
cases (text/JSON/UTF8 exact/one-over, HTTP body over) preserve prior cache and no partial
stdout on refusal. Two actual TLS HTTP-wait SIGINT executions retain old cache.

The first real fixture wrongly expected raw response timeout to fall back; Python
propagates TimeoutError, so native correctly stops. Expectations were corrected from
source/actual Python, not changed native output. Successful30 normal/5 error/cap/signal
evidence was retained; only remaining7 and added UTF8/query cases ran. Normal rendered
fields are exact apart from checked-format timestamps. All native tests pass once
because shared serde_json feature changed; clippy/debug/locked offline release and
affected inherited cache method pass. Broader prior TLS/provider/218-wide cases remain
inherited at their hashes. Actual Mac only, no speed/three-OS/live claim.

MCP mapping is dependency evidence only:9 exact names/all35 rows accounted for,0 native
tools. FTS proof uses parent P3 helper including rank1 and MATCH; other indexes/final
data writers/commit/crash still require actual synthetic-copy execution. No schema
change, real data/credentials/installed CLI/network/OS setup or paid API/model call.

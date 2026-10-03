# Native HTTP feed checkpoint

Base main: `9586f6e8614d7331ece5485c8d2f64b372914420` (feed PR #19 merged). This slice extends native `feeds refresh` to unauthenticated HTTP/HTTPS. Network search providers and network `read` remain pending. There is no Python runtime subprocess; Python is only the offline comparison oracle.

| Contract | Evidence / boundary |
| --- | --- |
| GET, user agent, feed Accept, identity encoding, final URL/body | Local stdlib server compares Python and native results; ordinary 10-hop redirects retain reference behavior. |
| Charset | Reference goldens for UTF-8/BOM, UTF-8-sig, ASCII, Latin-1, Windows-1252, UTF-16 variants, valid Shift-JIS, unknown codec fallback. Full Python codec aliases/malformed multibyte semantics remain pending. |
| Proxy | Environment uppercase/lowercase precedence, CGI uppercase HTTP suppression, empty lowercase override, NO_PROXY host/suffix/port/star, HTTP forwarding, HTTPS CONNECT. Native macOS/Windows OS proxy discovery and unusual proxy schemes remain pending. |
| TLS | Native OS roots with rustls, no verification-disable option. Ephemeral fixture CA verifies positive trust, untrusted certificates, wrong hostname, CONNECT, and process-only SSL_CERT_FILE. No global trust change. |
| Failure | Status, redirect loops, header/body timeout, truncated response; no automatic retry. Feed refresh retains prior items and records compatible error kinds. |
| Secrets | Errors omit response bodies and low-level transport messages, redact known query keys/userinfo, and remove fragments. These diagnostic differences are intentional safety changes; reference error-body previews are not reproduced. |
| Settings | Existing KWR_HTTP_TIMEOUT_SECONDS and environment proxy values. Native rejects non-finite/unrepresentable timeout values and invalid UTF-8 settings with generic errors. No real credential/proxy values enter fixtures or logs. |

Safety bounds are a separate implementation change: default 8 MiB response bytes (Content-Length preflight plus counted reads), at most 10 redirects, one positive finite deadline across client setup/redirects/body, HTTPS downgrade and URL userinfo rejection, and removal of Authorization/Cookie/Proxy-Authorization on cross-origin redirects. No CLI/environment switch disables these bounds. The default deadline is 20 seconds; KWR_HTTP_TIMEOUT_SECONDS adjusts it. Python has no byte bound and its socket timeout can reset between operations. Drip bodies and individually fast redirects explicitly succeed under the reference but time out in Rust; policy checks are counted separately from parity. Diagnostics remove error-body previews/fragments even when status errors contain synthetic secret markers. Current sequential feed refresh has concurrency one and no retries.

Remaining HTTP edges: URL normalization and unusual Location/header encodings, full Python codecs, OS proxy discovery, socks/authenticated proxy compatibility, interruption/broken pipe, and Windows/Linux execution. Location and legacy URI redirects have normal-input fixtures. All live providers are unverified. Fixture certificates/keys are temporary synthetic data; fixture sockets use loopback only. OpenSSL must already be available to run TLS fixtures; the verifier does not install it. Blocking DNS and synchronous native trust/client initialization cannot be forcibly interrupted; the deadline is checked afterward, while network/body I/O is timed. Resolver/platform-level cancellation remains a gate.

The locked reqwest feature set disables HTTP/2 and HTTP/3. Future feature changes enabling either protocol must explicitly disable and fixture-check protocol-level retries before retaining the zero-retry claim; do not infer it solely from the absence of a loop in this wrapper.

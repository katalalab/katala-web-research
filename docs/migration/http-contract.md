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

Safety bounds are tracked as a separate implementation change: bounded response bytes, one deadline across redirects/body, redirect count, downgrade/userinfo rejection and sensitive-header handling. Their intentional Python differences require separate fixture expectations, rather than being counted as parity.

Remaining HTTP edges: URL normalization and unusual Location/header encodings, URI redirect header, full Python codecs, OS proxy discovery, socks/authenticated proxy compatibility, interruption/broken pipe, and Windows/Linux execution. All live providers are unverified. Fixture certificates/keys are temporary synthetic data; fixture sockets use loopback only. OpenSSL must already be available to run TLS fixtures; the verifier does not install it.

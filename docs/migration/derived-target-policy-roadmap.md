# Derived URL authorization roadmap (not implemented)

PR30 normally integrated offline calculation and positive-enrichment refusal only.
Provider/feed/repository/search result URLs are derived input, including URLs passed
to future collect/investigate. Explicit user-selected read retains its existing local
target contract. A network opt-in command is not blanket authorization for every
returned address or for disclosing the complete URL to Jina. MCP0/9 is not a defense.
Runtime derived fetch stays disabled until the following separately reviewed gates pass.
No additional permissions, budgets, credentials or network settings are requested here.

## 1. Pure policy and type boundary, with no sockets

Proposed separate ExplicitTarget/DerivedTarget origins and a privately constructed
AuthorizedTarget/address set. An offline fake resolver and recording connector must
prove derived adapters cannot call trusted reader/EnvTransport or construct an
authorized target from an unchecked string. Production must have no loopback allow
flag, test environment override, generic-transport bypass or implicit fixture mode.
Registry trust/source quality and a URL's title/authority are not fetch authorization.

Table-driven synthetic URL/address vectors:HTTP(S) only, userinfo, empty/invalid
authority, numeric IPv4 spellings, IPv6/mapped addresses/zones, localhost variants,
loopback/private/link-local/metadata aliases, reserved/multicast/unspecified ranges,
public-only and mixed public/nonpublic resolver answers. Freeze the complete address
classification from authoritative data when implementing it; no ad-hoc keyword rule.
Reject unsafe answer sets rather than trusting one public answer among unsafe ones.
No real metadata/internal/public host is queried in these tests.

## 2. Bind authorization to the actual connection and each hop

Proposed resolver API returns immutable validated socket addresses under one operation
budget. Connect only to that set while preserving the original host for TLS/SNI and
Host; validate the chosen peer. A preflight DNS check followed by uncontrolled
re-resolution is insufficient. Fake resolver/connector tests must simulate changing
answers, TTL expiry, dual-stack fallback and connection retries without opening sockets.
Audit the locked HTTP client APIs before selecting an implementation or dependency.
Resolver cancellation remains a known common-transport gap, not solved by this plan.

Every redirect gets fresh origin/target/address authorization before a connection,
including public→private/metadata, relative URLs, authority/port changes and downgrade.
Pin allowed addresses for that hop and preserve inherited bounded body/redirect/time
and cross-origin header rules. No automatic retry or silent partial capture.

Initially proposed derived policy rejects a selected proxy unless a separately tested
proxy transport proves equivalent target/peer authorization. Never silently change
the user's proxy/environment or widen a proxy allowlist to make a test pass. Fake
CONNECT/proxy-resolution tests must cover proxy-local resolution and address changes.
Explicit read's existing proxy behavior remains a separate compatibility surface.

## 3. Third-party URL disclosure and fallback

Proposed default derived policy denies Jina transmission, including complete query,
fragment and userinfo. Diagnostic masking is not transmission authorization. Review
an explicit disclosure policy before enabling any derived Jina reader; do not assume
a public host makes path/query/fragment nonconfidential. Pure request-recorder fixtures
must prove denied inputs produce no Jina request and no sensitive error/event text.

Auto fallback must not switch from a restricted third-party request to trusted direct
fetch. Each fallback target/redirect needs the same derived authorization, pinned
connection and operation budget. Permission/transmission denial is not a FetchError
that can be bypassed by fallback. Keep ordinary reader payload/transport distinction.

## 4. Integration, resources and release gates

Keep initial policy fixtures offline. Any later connection test must use an owned
synthetic fixture with no real metadata/internal service, and must not introduce a
production private-target exception. Independently review the test-only transport
boundary before using a loopback socket to exercise the connection implementation.
Specify decoded/aggregate/statement/stdout/evidence budgets before runtime enablement;
the common8MiB per-response limit is not an aggregate bound. Maintain sequential
enrichment order, bounded fallback/time, cancellation and no cache write on failures.

Prove all derived call sites use the restricted path, including future collect and
investigate; retain explicit local-read regressions. Record intentional differences
from Python, Windows/Linux/MSRV/release and actual signal/crash validation separately.
Only independently reviewed exact-source gates can authorize runtime enablement.
This roadmap adds no implementation or final acceptance evidence.

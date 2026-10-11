from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPDefaultErrorHandler,
    HTTPErrorProcessor,
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    OpenerDirector,
    Request,
    UnknownHandler,
    urlopen,
)

DEFAULT_USER_AGENT = "katala-web-research/0.1 (+local research tool)"
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_PUBLIC_BODY_BYTES = 8 * 1024 * 1024

# Query parameters that carry a credential. OpenAlex only accepts its key as `api_key=`,
# so the secret cannot be moved into a header -- it has to be stripped on the way out.
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "key",
    "subscription_token",
    "token",
}


@dataclass(slots=True)
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        charset = "utf-8"
        if "charset=" in content_type:
            charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        try:
            return self.body.decode(charset or "utf-8", errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


class FetchError(RuntimeError):
    pass


def redact_url(url: str) -> str:
    """Strip credentials from a URL before it reaches an error message or a log line."""
    parsed = urlsplit(url)
    query = urlencode(
        [
            (key, "REDACTED" if key.lower() in SECRET_QUERY_KEYS else value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        ]
    )
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = "REDACTED@" + netloc.rsplit("@", 1)[1]
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        # IPv4 reachable through a v6 wrapper must pass the v4 check too.
        if any(ip in net for net in _DENIED_V6):
            return False
        embedded = ip.ipv4_mapped or ip.sixtofour
        if ip in _NAT64:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if embedded is not None and not embedded.is_global:
            return False
    return ip.is_global  # ponytail: Teredo (2001::/32) is not unwrapped; add if it ever matters


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
# Deprecated IPv4-compatible (::/96) and site-local (fec0::/10) ranges: never legitimate public targets.
_DENIED_V6 = (ipaddress.ip_network("::/96"), ipaddress.ip_network("fec0::/10"))


def public_addresses(host: str, port: int) -> list[str]:
    """Resolve host and return its addresses; refuse if any of them is not publicly routable."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"cannot resolve {host}: {exc}") from exc
    addresses = [str(info[4][0]) for info in infos]
    if not addresses:
        raise FetchError(f"cannot resolve {host}")
    for address in addresses:
        if not _is_public(ipaddress.ip_address(address.split("%", 1)[0])):
            raise FetchError(f"refusing to fetch {host}: resolves to a non-public address")
    return addresses


def require_public_url(url: str) -> None:
    """Fail fast (before a URL is sent to any third party) when the target is not public."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError("URL must be http(s) with a host")
    public_addresses(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))


def _connect_public(host: str, port: int, timeout) -> socket.socket:
    # Validation and connect share one resolution, so DNS rebinding cannot swap the address in between.
    last: OSError | None = None
    for address in public_addresses(host, port):
        try:
            return socket.create_connection((address, port), timeout)
        except OSError as exc:
            last = exc
    raise last or FetchError(f"cannot connect to {host}")


class _PublicHTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = _connect_public(self.host, self.port, self.timeout)


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def connect(self) -> None:
        sock = _connect_public(self.host, self.port, self.timeout)
        self.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)


class _CappedBody:
    """HTTPRedirectHandler drains the redirect body with an unbounded read(); bound it."""

    def __init__(self, fp, limit: int = 64 * 1024) -> None:
        self._fp, self._limit = fp, limit

    def read(self, *_args) -> bytes:
        return self._fp.read(self._limit)

    def close(self) -> None:
        self._fp.close()


class _PublicRedirectHandler(HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        return super().http_error_302(req, _CappedBody(fp), code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


class _PublicHTTPHandler(HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPSHandler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PublicHTTPSConnection, req)


def _public_open(request: Request, *, timeout: float):
    # No proxy/file/ftp handlers: every hop, redirects included, goes through the checked connection.
    opener = OpenerDirector()
    for handler in (
        _PublicHTTPHandler(),
        _PublicHTTPSHandler(),
        _PublicRedirectHandler(),
        HTTPDefaultErrorHandler(),
        HTTPErrorProcessor(),
        UnknownHandler(),
    ):
        opener.add_handler(handler)
    return opener.open(request, timeout=timeout)


def fetch_url(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    public_only: bool = False,
) -> HttpResponse:
    """`public_only` is for URLs an untrusted party chose: only public addresses, no proxy, capped body."""
    merged = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged.update(headers)
    request = Request(url, headers=merged)
    timeout_seconds = _resolve_timeout(timeout)
    try:
        opener = _public_open if public_only else urlopen
        with opener(request, timeout=timeout_seconds) as response:
            body = response.read(MAX_PUBLIC_BODY_BYTES + 1) if public_only else response.read()
            if public_only and len(body) > MAX_PUBLIC_BODY_BYTES:
                raise FetchError(f"response too large for {redact_url(url)}")
            return HttpResponse(
                url=response.geturl(),
                status=getattr(response, "status", 200),
                headers={k.lower(): v for k, v in response.headers.items()},
                body=body,
            )
    except HTTPError as exc:
        body = exc.read(200)  # only 200 bytes are reported; never drain a hostile body
        raise FetchError(f"HTTP {exc.code} for {redact_url(url)}: {body[:200]!r}") from exc
    except URLError as exc:
        raise FetchError(f"fetch failed for {redact_url(url)}: {exc.reason}") from exc


def _resolve_timeout(timeout: float | None) -> float:
    if timeout is not None:
        if timeout <= 0:
            raise FetchError("timeout must be greater than 0 seconds")
        return timeout
    raw = os.environ.get("KWR_HTTP_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise FetchError("KWR_HTTP_TIMEOUT_SECONDS must be a number greater than 0") from exc
    if value <= 0:
        raise FetchError("KWR_HTTP_TIMEOUT_SECONDS must be a number greater than 0")
    return value

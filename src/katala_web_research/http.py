from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

DEFAULT_USER_AGENT = "katala-web-research/0.1 (+local research tool)"
DEFAULT_TIMEOUT_SECONDS = 20.0

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


def fetch_url(url: str, *, headers: dict[str, str] | None = None, timeout: float | None = None) -> HttpResponse:
    merged = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        merged.update(headers)
    request = Request(url, headers=merged)
    timeout_seconds = _resolve_timeout(timeout)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return HttpResponse(
                url=response.geturl(),
                status=getattr(response, "status", 200),
                headers={k.lower(): v for k, v in response.headers.items()},
                body=response.read(),
            )
    except HTTPError as exc:
        body = exc.read()
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

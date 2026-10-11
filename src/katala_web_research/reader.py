from __future__ import annotations

import codecs
import json
import re
from json import JSONDecodeError
from urllib.parse import quote, urlparse

from .http import FetchError, fetch_url, require_public_url
from .models import PageSnapshot, utc_now_iso
from .text import SimpleHTMLTextExtractor

_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_-]+)""", re.IGNORECASE)


def read_url(url: str, *, reader: str = "auto") -> PageSnapshot:
    _require_http_url(url)
    if reader not in {"auto", "jina", "direct"}:
        raise ValueError("reader must be one of: auto, jina, direct")
    require_public_url(url)
    if reader in {"auto", "jina"}:
        try:
            return read_with_jina(url)
        except FetchError:
            if reader == "jina":
                raise
    return read_direct(url)


def read_with_jina(url: str) -> PageSnapshot:
    jina_url = "https://r.jina.ai/" + quote(url, safe="")
    response = fetch_url(jina_url, headers={"Accept": "text/plain"})
    content = response.text.strip()
    _raise_for_jina_error_payload(content, url)
    title = _title_from_markdown(content) or url
    return PageSnapshot(
        url=url,
        title=title,
        content=content,
        source="jina-reader",
        fetched_at=utc_now_iso(),
        status_code=response.status,
        content_type=response.headers.get("content-type"),
    )


def read_direct(url: str) -> PageSnapshot:
    response = fetch_url(url, headers={"Accept": "text/html, text/plain;q=0.9, */*;q=0.5"}, public_only=True)
    content_type = response.headers.get("content-type", "")
    text = response.text
    if "charset=" not in content_type.lower():
        sniffed = _sniff_meta_charset(response.body)
        if sniffed:
            text = response.body.decode(sniffed, errors="replace")
    if "html" in content_type.lower() or "<html" in text[:500].lower():
        parser = SimpleHTMLTextExtractor()
        parser.feed(text)
        title = parser.title or url
        content = parser.content
    else:
        title = url
        content = text.strip()
    return PageSnapshot(
        url=response.url,
        title=title,
        content=content,
        source="direct",
        fetched_at=utc_now_iso(),
        status_code=response.status,
        content_type=content_type,
    )


def _sniff_meta_charset(body: bytes) -> str | None:
    match = _META_CHARSET_RE.search(body[:4096])
    if not match:
        return None
    charset = match.group(1).decode("ascii", errors="ignore")
    try:
        codecs.lookup(charset)
    except LookupError:
        return None
    return charset


def _require_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("only http and https URLs are supported")


def _title_from_markdown(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip("# ").strip()
        if stripped:
            return stripped[:160]
    return ""


def _raise_for_jina_error_payload(content: str, url: str) -> None:
    stripped = content.lstrip()
    if not stripped.startswith("{"):
        return
    try:
        payload = json.loads(stripped)
    except JSONDecodeError:
        return
    if not isinstance(payload, dict) or not _looks_like_jina_error(payload):
        return
    reason = payload.get("readableMessage") or payload.get("message") or content[:120]
    raise FetchError(f"jina reader returned an error payload for {url}: {reason}")


def _looks_like_jina_error(payload: dict[str, object]) -> bool:
    status = payload.get("status")
    code = payload.get("code")
    name = payload.get("name")
    has_failure_status = any(isinstance(value, int) and value >= 400 for value in (status, code))
    has_error_identity = isinstance(name, str) and (name.endswith("Error") or "Error" in name)
    has_jina_message = "readableMessage" in payload or "message" in payload
    return has_failure_status and has_error_identity and has_jina_message

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

REGISTRY_PATH = Path(__file__).with_name("data") / "source_registry.json"
OVERLAY_ENV = "KWR_SOURCE_REGISTRY_OVERLAY"


@dataclass(slots=True, frozen=True)
class SourceRegistryEntry:
    name: str
    domain: str
    source_type: str
    query_types: tuple[str, ...]
    url: str
    hosts: tuple[str, ...]
    url_prefixes: tuple[str, ...]
    best_for: str
    freshness: str
    trust_score: int
    bias_caveat: str
    update_cadence: str
    avoid_for: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: dict) -> SourceRegistryEntry:
        return cls(
            name=str(raw["name"]),
            domain=str(raw["domain"]),
            source_type=str(raw["source_type"]),
            query_types=tuple(raw.get("query_types", [])),
            url=str(raw["url"]),
            hosts=tuple(_normalize_host(host) for host in raw.get("hosts", [])),
            url_prefixes=tuple(raw.get("url_prefixes", [])),
            best_for=str(raw.get("best_for", "")),
            freshness=str(raw.get("freshness", "")),
            trust_score=int(raw.get("trust_score", 50)),
            bias_caveat=str(raw.get("bias_caveat", "")),
            update_cadence=str(raw.get("update_cadence", "")),
            avoid_for=tuple(raw.get("avoid_for", [])),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class SourceRegistry:
    sources: tuple[SourceRegistryEntry, ...]

    def recommend(self, *, domain: str | None = None, query_type: str | None = None, limit: int = 5) -> list[SourceRegistryEntry]:
        selected = []
        for source in self.sources:
            if domain and source.domain != domain:
                continue
            if query_type and query_type not in source.query_types:
                continue
            selected.append(source)
        selected.sort(key=lambda source: (-source.trust_score, source.domain, source.name))
        return selected[: max(limit, 0)]

    def match_url(self, url: str) -> SourceRegistryEntry | None:
        normalized = _normalize_url(url)
        parsed = urlparse(normalized)
        host = _normalize_host(parsed.netloc)
        if not host:
            return None

        prefix_matches = [
            source
            for source in self.sources
            if any(_matches_url_prefix(parsed, host, prefix) for prefix in source.url_prefixes)
        ]
        if prefix_matches:
            return _highest_trust(prefix_matches)

        host_matches = [
            source
            for source in self.sources
            if host in source.hosts and _allows_host_fallback(source)
        ]
        if host_matches:
            return _highest_trust(host_matches)
        return None

    def to_dict(self) -> dict:
        return {"sources": [source.to_dict() for source in self.sources]}

    def merged(self, overlay: SourceRegistry) -> SourceRegistry:
        merged: dict[tuple[str, str, str], SourceRegistryEntry] = {}
        for source in self.sources:
            merged[_source_key(source)] = source
        for source in overlay.sources:
            merged[_source_key(source)] = source
        return SourceRegistry(sources=tuple(merged.values()))


@lru_cache(maxsize=1)
def default_source_registry() -> SourceRegistry:
    return load_source_registry(REGISTRY_PATH)


@lru_cache(maxsize=8)
def source_registry(overlay_path: str | None = None) -> SourceRegistry:
    registry = default_source_registry()
    selected_overlay = overlay_path or os.environ.get(OVERLAY_ENV)
    if not selected_overlay:
        return registry
    return registry.merged(load_source_registry(selected_overlay))


def load_source_registry(path: str | Path) -> SourceRegistry:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    sources = tuple(SourceRegistryEntry.from_dict(item) for item in raw.get("sources", []))
    return SourceRegistry(sources=sources)


def source_registry_metadata(url: str) -> dict[str, str | int] | None:
    source = source_registry().match_url(url)
    if source is None:
        return None
    return {
        "registry_source": source.name,
        "registry_domain": source.domain,
        "registry_source_type": source.source_type,
        "registry_freshness": source.freshness,
        "registry_update_cadence": source.update_cadence,
        "registry_trust_score": source.trust_score,
        "bias_caveat": source.bias_caveat,
    }


def registry_lines(url: str) -> list[str]:
    metadata = source_registry_metadata(url)
    if metadata is None:
        return []
    return [
        f"- registry_source: {metadata['registry_source']}",
        f"- registry_domain: {metadata['registry_domain']}",
        f"- registry_freshness: {metadata['registry_freshness']}",
        f"- registry_update_cadence: {metadata['registry_update_cadence']}",
        f"- registry_trust_score: {metadata['registry_trust_score']}",
        f"- bias_caveat: {metadata['bias_caveat']}",
    ]


def _highest_trust(sources: list[SourceRegistryEntry]) -> SourceRegistryEntry:
    return sorted(sources, key=lambda source: (-source.trust_score, source.name))[0]


def _source_key(source: SourceRegistryEntry) -> tuple[str, str, str]:
    return (source.domain, source.source_type, source.name)


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url}"
    return url


def _normalize_host(host: str) -> str:
    return host.lower().removeprefix("www.")


def _matches_url_prefix(parsed_url, host: str, prefix: str) -> bool:
    parsed_prefix = urlparse(_normalize_url(prefix))
    if host != _normalize_host(parsed_prefix.netloc):
        return False
    prefix_path = parsed_prefix.path.rstrip("/")
    url_path = parsed_url.path.rstrip("/")
    if not prefix_path:
        return True
    return url_path == prefix_path or url_path.startswith(prefix_path + "/")


def _allows_host_fallback(source: SourceRegistryEntry) -> bool:
    if not source.url_prefixes:
        return True
    return any(urlparse(_normalize_url(prefix)).path in {"", "/"} for prefix in source.url_prefixes)

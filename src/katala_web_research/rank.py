from __future__ import annotations

import re
from collections import Counter
from math import ceil
from urllib.parse import urlparse

from .models import SearchResult

TOKEN_RE = re.compile(r"[A-Za-z0-9_+-]{2,}|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]{1,}")


def query_tokens(query: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(query)}


def rank_results(query: str, results: list[SearchResult]) -> list[SearchResult]:
    from .source_quality import classify_url, source_quality_score

    seen: set[str] = set()
    ranked: list[SearchResult] = []
    for result in results:
        normalized = _dedupe_key(result.url)
        if not normalized or normalized in seen:
            continue
        if not _passes_search_gates(result):
            continue
        seen.add(normalized)
        if result.rank and "provider_rank" not in result.metadata:
            result.metadata["provider_rank"] = result.rank
        source_weight = 0.25 if result.source in {"github", "jina"} else 0.0
        fusion_weight = min(float(result.metadata.get("rrf_score", 0.0)) * 20, 0.75)
        consensus_weight = min(max(0, int(result.metadata.get("source_count", 1)) - 1) * 0.2, 0.6)
        result.score = round(
            source_quality_score(query, result)
            + source_weight
            + fusion_weight
            + consensus_weight
            + max(0, 20 - result.rank) / 100,
            3,
        )
        ranked.append(result)
    ranked.sort(key=lambda item: (-item.score, item.rank, item.url))
    ranked = _select_with_katala_diversity(ranked, classify_url)
    for idx, result in enumerate(ranked, start=1):
        result.rank = idx
    return ranked


def _dedupe_key(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _passes_search_gates(result: SearchResult) -> bool:
    if not result.url or not result.title:
        return False
    return "retracted=true" not in result.snippet.lower()


def _select_with_katala_diversity(results: list[SearchResult], classifier) -> list[SearchResult]:
    if len(results) <= 2:
        return results
    k = len(results)
    host_cap = max(1, ceil(k * 0.4))
    type_cap = max(1, ceil(k * 0.55))
    selected: list[SearchResult] = []
    host_count: Counter[str] = Counter()
    type_count: Counter[str] = Counter()

    for result in results:
        host = urlparse(result.url).netloc.lower().removeprefix("www.")
        source_type, _quality = classifier(result.url)
        if host_count[host] >= host_cap:
            continue
        if type_count[source_type] >= type_cap:
            continue
        selected.append(result)
        host_count[host] += 1
        type_count[source_type] += 1

    return selected

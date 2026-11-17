from __future__ import annotations

import re
from contextlib import closing
from pathlib import Path

from .archive import Archive
from .models import SearchResult
from .rank import query_tokens, rank_results

SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def apply_archive_highlights(
    query: str,
    results: list[SearchResult],
    *,
    archive_path: str | Path,
    highlight_top: int = 0,
    max_chars: int = 700,
) -> list[SearchResult]:
    if highlight_top <= 0 or not results:
        return results

    with closing(Archive(archive_path)) as archive:
        highlighted: list[SearchResult] = []
        for index, result in enumerate(results):
            if index >= highlight_top:
                highlighted.append(result)
                continue
            page = archive.page_by_url(result.url)
            if page is None:
                highlighted.append(_copy_result(result, metadata=_highlight_metadata(result, "miss")))
                continue
            snippet = build_highlight(query, page.content, max_chars=max_chars)
            if not snippet:
                highlighted.append(_copy_result(result, metadata=_highlight_metadata(result, "empty")))
                continue
            metadata = _highlight_metadata(result, "ok")
            metadata["highlight_source"] = page.source
            metadata["highlight_fetched_at"] = page.fetched_at
            highlighted.append(_copy_result(result, snippet=snippet, metadata=metadata))

    return rank_results(query, highlighted)


def build_highlight(query: str, content: str, *, max_chars: int = 700, max_sentences: int = 4) -> str:
    tokens = query_tokens(query)
    if not tokens:
        return ""
    candidates = []
    for order, sentence in enumerate(_sentences(content)):
        cleaned = " ".join(sentence.split())
        if len(cleaned) < 20:
            continue
        score = _sentence_score(cleaned, tokens)
        if score <= 0:
            continue
        candidates.append((score, order, cleaned))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], item[1]))
    selected = sorted(candidates[:max_sentences], key=lambda item: item[1])
    text = " ".join(sentence for _score, _order, sentence in selected)
    return text[:max_chars].strip()


def _sentences(content: str) -> list[str]:
    return [part.strip() for part in SENTENCE_RE.split(content) if part.strip()]


def _sentence_score(sentence: str, tokens: set[str]) -> int:
    lowered = sentence.lower()
    return sum(1 for token in tokens if token in lowered)


def _highlight_metadata(result: SearchResult, status: str) -> dict:
    metadata = dict(result.metadata)
    metadata["highlight_status"] = status
    return metadata


def _copy_result(
    result: SearchResult,
    *,
    snippet: str | None = None,
    metadata: dict | None = None,
) -> SearchResult:
    return SearchResult(
        title=result.title,
        url=result.url,
        snippet=result.snippet if snippet is None else snippet,
        source=result.source,
        published_at=result.published_at,
        rank=result.rank,
        score=result.score,
        metadata=dict(result.metadata) if metadata is None else metadata,
    )

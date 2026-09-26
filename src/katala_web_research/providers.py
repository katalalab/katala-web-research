from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol
from urllib.parse import quote, urlencode

from .archive import DEFAULT_ARCHIVE, Archive
from .engine_health import EngineHealthStat, summarize_engine_runs, weak_engines
from .fusion import fuse_and_rank
from .http import FetchError, fetch_url, redact_url
from .models import SearchResult
from .provider_parsing import (
    _abstract_from_inverted_index as _abstract_from_inverted_index,
)
from .provider_parsing import (
    _add_openalex_location_metadata as _add_openalex_location_metadata,
)
from .provider_parsing import (
    _DuckDuckGoHTMLParser as _DuckDuckGoHTMLParser,
)
from .provider_parsing import (
    _github_code_fragment as _github_code_fragment,
)
from .provider_parsing import (
    _github_code_snippet as _github_code_snippet,
)
from .provider_parsing import (
    _github_code_title as _github_code_title,
)
from .provider_parsing import (
    _github_license_name as _github_license_name,
)
from .provider_parsing import (
    _github_license_url as _github_license_url,
)
from .provider_parsing import (
    _github_metadata as _github_metadata,
)
from .provider_parsing import (
    _github_rest_item as _github_rest_item,
)
from .provider_parsing import (
    _github_snippet as _github_snippet,
)
from .provider_parsing import (
    _openalex_metadata as _openalex_metadata,
)
from .provider_parsing import (
    _openalex_snippet as _openalex_snippet,
)
from .provider_parsing import (
    _openalex_url as _openalex_url,
)
from .provider_parsing import (
    _year_as_date as _year_as_date,
)
from .rank import rank_results

# Keep CLI subprocesses above the 20s HTTP fetch timeout so a slow-but-live
# network call is not cut off, while still bounding a hung gh/op process.
GH_TIMEOUT = 30
OP_TIMEOUT = 10


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        ...


class DuckDuckGoSearch:
    name = "ddg"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
        response = fetch_url(url, headers={"Accept": "text/html"})
        parser = _DuckDuckGoHTMLParser()
        parser.feed(response.text)
        parser.close()
        results = parser.results[:limit]
        for idx, result in enumerate(results, start=1):
            result.rank = idx
        return rank_results(query, results)


class GitHubRepoSearch:
    name = "github"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        if shutil.which("gh"):
            gh_results = self._search_with_gh(query, limit)
            if gh_results:
                return rank_results(query, gh_results)
        return rank_results(query, self._search_with_rest(query, limit))

    def _search_with_gh(self, query: str, limit: int) -> list[SearchResult]:
        cmd = [
            "gh",
            "search",
            "repos",
            query,
            "--limit",
            str(limit),
            "--json",
            "fullName,description,url,stargazersCount,updatedAt,isFork",
        ]
        try:
            completed = subprocess.run(
                cmd, text=True, capture_output=True, check=False, timeout=GH_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            return []
        if completed.returncode != 0:
            return []
        items = json.loads(completed.stdout or "[]")
        return [
            SearchResult(
                title=item.get("fullName") or item.get("url") or "",
                url=item.get("url") or "",
                snippet=_github_snippet(item),
                source=self.name,
                published_at=item.get("updatedAt"),
                rank=idx,
                metadata=_github_metadata(item),
            )
            for idx, item in enumerate(items, start=1)
            if item.get("url")
        ]

    def _search_with_rest(self, query: str, limit: int) -> list[SearchResult]:
        url = "https://api.github.com/search/repositories?" + urlencode(
            {"q": query, "sort": "stars", "order": "desc", "per_page": min(limit, 30)}
        )
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
        response = fetch_url(url, headers=headers)
        payload = _parse_json(response.text, url)
        results: list[SearchResult] = []
        for idx, item in enumerate(payload.get("items", []), start=1):
            normalized = _github_rest_item(item)
            results.append(
                SearchResult(
                    title=item.get("full_name") or item.get("html_url") or "",
                    url=item.get("html_url") or "",
                    snippet=_github_snippet(normalized),
                    source=self.name,
                    published_at=item.get("updated_at"),
                    rank=idx,
                    metadata=_github_metadata(normalized),
                )
            )
        return results


class GitHubCodeSearch:
    name = "github_code"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        if not token:
            raise FetchError("GITHUB_TOKEN is required for GitHub code search")
        requested = max(limit, 0)
        if requested == 0:
            return []
        per_page = 100
        max_pages = 10
        pages = min(max_pages, max(1, (requested + per_page - 1) // per_page))
        results: list[SearchResult] = []
        for page in range(1, pages + 1):
            url = "https://api.github.com/search/code?" + urlencode(
                _github_code_params(query, page=page, per_page=per_page)
            )
            try:
                response = fetch_url(
                    url,
                    headers=_github_code_headers(token),
                )
            except FetchError as exc:
                if _github_code_invalid_query(exc):
                    return []
                raise
            payload = _parse_json(response.text, url)
            page_items = payload.get("items", [])
            if not page_items:
                break
            for item in page_items:
                if len(results) >= requested:
                    break
                repo = item.get("repository") or {}
                fragment = _github_code_fragment(item.get("text_matches"))
                path = str(item.get("path") or item.get("name") or "")
                repo_name = str(repo.get("full_name") or "")
                results.append(
                    SearchResult(
                        title=_github_code_title(repo_name, path, item.get("html_url")),
                        url=item.get("html_url") or "",
                        snippet=_github_code_snippet(repo, path, fragment),
                        source=self.name,
                        rank=len(results) + 1,
                        metadata={
                            "repository": repo_name,
                            "repository_url": repo.get("html_url") or "",
                            "path": path,
                            "file_name": item.get("name") or "",
                            "fragment": fragment,
                        },
                    )
                )
            if len(results) >= requested:
                break
        return rank_results(query, results)


class FeedSearch:
    name = "feed"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        archive = Archive(os.environ.get("KWR_ARCHIVE", str(DEFAULT_ARCHIVE)))
        try:
            hits = archive.query_feeds(query, limit=limit)
        finally:
            archive.close()
        results = [
            SearchResult(
                title=hit.title,
                url=hit.url,
                snippet=hit.snippet,
                source=self.name,
                published_at=hit.published_at,
                rank=idx,
                metadata={
                    "source_url": hit.source_url,
                    "source_title": hit.source_title,
                    "fetched_at": hit.fetched_at,
                    "archive_rank": hit.rank,
                },
            )
            for idx, hit in enumerate(hits, start=1)
        ]
        return rank_results(query, results)


class JinaSearch:
    name = "jina"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        token = os.environ.get("JINA_API_KEY")
        if not token:
            raise FetchError("JINA_API_KEY is required for Jina search")
        url = "https://s.jina.ai/?" + urlencode({"q": query})
        response = fetch_url(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        payload = _parse_json(response.text, url)
        data = payload.get("data", payload if isinstance(payload, list) else [])
        results: list[SearchResult] = []
        for idx, item in enumerate(data[:limit], start=1):
            results.append(
                SearchResult(
                    title=item.get("title") or item.get("url") or "",
                    url=item.get("url") or "",
                    snippet=item.get("description") or item.get("content") or "",
                    source=self.name,
                    published_at=item.get("publishedTime") or item.get("published_at"),
                    rank=idx,
                )
            )
        return rank_results(query, results)


class SearxngSearch:
    name = "searxng"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        base_url = os.environ.get("KWR_SEARXNG_URL", "").rstrip("/")
        if not base_url:
            raise FetchError("KWR_SEARXNG_URL is required for SearXNG search")
        requested = max(limit, 0)
        if requested == 0:
            return []
        page_size = 20
        pages = max(1, (requested + page_size - 1) // page_size)
        results: list[SearchResult] = []
        for page in range(1, pages + 1):
            url = base_url + "/search?" + urlencode(_searxng_params(query, page=page))
            response = fetch_url(url, headers={"Accept": "application/json"})
            payload = _parse_json(response.text, url)
            page_results = payload.get("results", [])
            if not page_results:
                break
            for item in page_results:
                if len(results) >= requested:
                    break
                results.append(
                    SearchResult(
                        title=item.get("title") or item.get("url") or "",
                        url=item.get("url") or "",
                        snippet=item.get("content") or "",
                        source=self.name,
                        published_at=item.get("publishedDate"),
                        rank=len(results) + 1,
                    )
                )
            if len(results) >= requested:
                break
        return rank_results(query, results)


class BraveSearch:
    name = "brave"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        token = os.environ.get("BRAVE_SEARCH_API_KEY")
        if not token:
            raise FetchError("BRAVE_SEARCH_API_KEY is required for Brave search")
        requested = max(limit, 0)
        if requested == 0:
            return []
        page_size = 20
        max_pages = 10
        pages = min(max_pages, max(1, (requested + page_size - 1) // page_size))
        results: list[SearchResult] = []
        for page in range(pages):
            url = "https://api.search.brave.com/res/v1/web/search?" + urlencode(
                _brave_params(query, limit=page_size, offset=page)
            )
            response = fetch_url(
                url,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": token,
                },
            )
            payload = _parse_json(response.text, url)
            web_results = (payload.get("web") or {}).get("results", [])
            if not web_results:
                break
            for item in web_results:
                if len(results) >= requested:
                    break
                results.append(
                    SearchResult(
                        title=item.get("title") or item.get("url") or "",
                        url=item.get("url") or "",
                        snippet=item.get("description") or "",
                        source=self.name,
                        published_at=item.get("age"),
                        rank=len(results) + 1,
                    )
                )
            if len(results) >= requested:
                break
        return rank_results(query, results)


class OpenAlexSearch:
    name = "openalex"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        requested = max(limit, 0)
        if requested == 0:
            return []
        cursor = "*"
        results: list[SearchResult] = []
        while len(results) < requested:
            params = _openalex_params(query, limit=min(100, requested - len(results)), cursor=cursor)
            url = "https://api.openalex.org/works?" + urlencode(params)
            response = fetch_url(url, headers={"Accept": "application/json"})
            payload = _parse_json(response.text, url)
            page_items = payload.get("results", [])
            if not page_items:
                break
            for item in page_items:
                if len(results) >= requested:
                    break
                results.append(
                    SearchResult(
                        title=item.get("display_name") or item.get("title") or item.get("id") or "",
                        url=_openalex_url(item),
                        snippet=_openalex_snippet(item),
                        source=self.name,
                        published_at=item.get("publication_date") or _year_as_date(item.get("publication_year")),
                        rank=len(results) + 1,
                        metadata=_openalex_metadata(item),
                    )
                )
            cursor = _openalex_next_cursor(payload)
            if not cursor:
                break
        return rank_results(query, results)


OPENALEX_EXPAND_MAX = 50


def openalex_expand(
    seed: str, *, direction: str = "both", limit: int = 10
) -> dict[str, list[SearchResult]]:
    """Follow an OpenAlex work's citation edges.

    `limit` is per direction and is clamped to OPENALEX_EXPAND_MAX: an expansion that is
    allowed to grow with the graph turns one command into a crawl.
    """
    if direction not in {"referenced", "citing", "both"}:
        raise ValueError("direction must be one of: referenced, citing, both")
    bounded = max(0, min(limit, OPENALEX_EXPAND_MAX))
    if bounded == 0:
        return {}
    work = _openalex_work(_openalex_work_id(seed))
    expanded: dict[str, list[SearchResult]] = {}
    if direction in {"referenced", "both"}:
        referenced = [
            _openalex_work_id(value) for value in work.get("referenced_works", [])[:bounded]
        ]
        expanded["referenced"] = _openalex_works_by_id(referenced)
    if direction in {"citing", "both"}:
        expanded["citing"] = _openalex_filtered_works(
            f"cites:{_openalex_work_id(work.get('id', ''))}", limit=bounded
        )
    return expanded


def _openalex_work_id(value: str) -> str:
    """Reduce a DOI URL, an openalex.org URL, or a bare id to the id OpenAlex indexes on."""
    trimmed = (value or "").strip()
    if not trimmed:
        raise ValueError("an OpenAlex work id, DOI, or URL is required")
    if trimmed.startswith(("https://openalex.org/", "https://api.openalex.org/works/")):
        return trimmed.rsplit("/", 1)[-1]
    if trimmed.startswith(("https://doi.org/", "http://doi.org/")):
        return trimmed
    if trimmed.startswith("10."):
        return f"https://doi.org/{trimmed}"
    return trimmed


def _openalex_work(work_id: str) -> dict:
    params: dict[str, str | int] = {}
    _add_openalex_credentials(params)
    url = f"https://api.openalex.org/works/{quote(work_id, safe='')}"
    if params:
        url += "?" + urlencode(params)
    response = fetch_url(url, headers={"Accept": "application/json"})
    payload = _parse_json(response.text, url)
    if not isinstance(payload, dict) or not payload.get("id"):
        raise FetchError(f"no OpenAlex work for {work_id}")
    return payload


def _openalex_works_by_id(work_ids: list[str]) -> list[SearchResult]:
    if not work_ids:
        return []
    return _openalex_filtered_works("openalex_id:" + "|".join(work_ids), limit=len(work_ids))


def _openalex_filtered_works(filter_value: str, *, limit: int) -> list[SearchResult]:
    params: dict[str, str | int] = {
        "filter": filter_value,
        "per_page": min(limit, OPENALEX_EXPAND_MAX),
        "select": OPENALEX_SELECT,
    }
    _add_openalex_credentials(params)
    url = "https://api.openalex.org/works?" + urlencode(params)
    response = fetch_url(url, headers={"Accept": "application/json"})
    payload = _parse_json(response.text, url)
    return [
        SearchResult(
            title=item.get("display_name") or item.get("title") or item.get("id") or "",
            url=_openalex_url(item),
            snippet=_openalex_snippet(item),
            source="openalex",
            published_at=item.get("publication_date") or _year_as_date(item.get("publication_year")),
            rank=idx,
            metadata=_openalex_metadata(item),
        )
        for idx, item in enumerate(payload.get("results", [])[:limit], start=1)
    ]


def _add_openalex_credentials(params: dict[str, str | int]) -> None:
    token = _secret_env("OPENALEX_API_KEY").strip()
    if token:
        params["api_key"] = token
    mailto = os.environ.get("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto


class MetaSearch:
    name = "meta"

    def search(self, query: str, *, limit: int = 10) -> list[SearchResult]:
        profile = _meta_profile()
        provider_names = [name for name in _meta_provider_names(profile) if name in PROVIDERS]
        provider_names = _route_around_weak_engines(provider_names)
        if not provider_names:
            return []
        result_lists: list[list[SearchResult]] = []
        runs: list[_MetaEngineRun] = []
        per_engine_limit = max(2, min(limit, 8))
        with ThreadPoolExecutor(max_workers=min(len(provider_names), 4)) as executor:
            futures = {
                executor.submit(
                    _run_meta_provider,
                    name,
                    _rewrite_query_for_provider(query, provider=name, profile=profile),
                    per_engine_limit,
                ): name
                for name in provider_names
            }
            for future in as_completed(futures):
                try:
                    results, run = future.result()
                except Exception as exc:
                    run = _MetaEngineRun(
                        provider=futures[future],
                        status="error",
                        latency_ms=0,
                        result_count=0,
                        health_score=0.0,
                        error_kind=exc.__class__.__name__,
                    )
                    results = []
                runs.append(run)
                if results:
                    result_lists.append(results)
        _record_engine_runs(runs)
        ranked = fuse_and_rank(
            query,
            result_lists,
            limit=limit,
            engine_health={run.provider: run.health_score for run in runs},
        )
        return [
            _annotate_meta_result(
                result,
                profile=profile,
                provider_names=provider_names,
                runs=runs,
            )
            for result in ranked
        ]


@dataclass(slots=True, frozen=True)
class _MetaEngineRun:
    provider: str
    status: str
    latency_ms: int
    result_count: int
    health_score: float
    error_kind: str = ""

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


META_PROFILES: dict[str, tuple[str, ...]] = {
    "broad": ("ddg", "github", "openalex", "searxng"),
    "docs": ("ddg", "searxng", "github", "jina"),
    "scholarly": ("openalex", "searxng", "ddg"),
    "code": ("github_code", "github", "searxng", "ddg"),
    "fresh": ("ddg", "searxng", "brave"),
    "local": ("feed", "ddg", "github"),
    "monitoring": ("feed", "ddg", "github"),
}


PROVIDERS: dict[str, SearchProvider] = {
    "brave": BraveSearch(),
    "ddg": DuckDuckGoSearch(),
    "feed": FeedSearch(),
    "github": GitHubRepoSearch(),
    "github_code": GitHubCodeSearch(),
    "meta": MetaSearch(),
    "openalex": OpenAlexSearch(),
    "jina": JinaSearch(),
    "searxng": SearxngSearch(),
}


def _run_meta_provider(
    provider: str, rewritten_query: str, limit: int
) -> tuple[list[SearchResult], _MetaEngineRun]:
    started = time.perf_counter()
    try:
        results = get_provider(provider).search(rewritten_query, limit=limit)
        latency_ms = _elapsed_ms(started)
        status = "ok" if results else "empty"
        run = _MetaEngineRun(
            provider=provider,
            status=status,
            latency_ms=latency_ms,
            result_count=len(results),
            health_score=_meta_engine_health_score(
                status=status,
                result_count=len(results),
                latency_ms=latency_ms,
                requested=limit,
            ),
        )
        return [_annotate_engine_result(result, run) for result in results], run
    except Exception as exc:
        latency_ms = _elapsed_ms(started)
        run = _MetaEngineRun(
            provider=provider,
            status="error",
            latency_ms=latency_ms,
            result_count=0,
            health_score=0.0,
            error_kind=exc.__class__.__name__,
        )
        return [], run


def _health_ledger_path() -> str:
    # Only the caller that named an archive gets health tracking. A search should not start
    # writing a database into whatever directory it happens to be invoked from, and the CLI
    # already exports KWR_ARCHIVE for every command that owns an archive.
    return os.environ.get("KWR_ARCHIVE", "")


def _route_around_weak_engines(provider_names: list[str]) -> list[str]:
    path = _health_ledger_path()
    if not path or not provider_names:
        return provider_names
    archive = Archive(path)
    try:
        weak = set(weak_engines(summarize_engine_runs(archive.engine_runs())))
    finally:
        archive.close()
    kept = [name for name in provider_names if name not in weak]
    # Never route around every engine: a fleet-wide outage would then read as "no results"
    # instead of "everything is failing", which is the harder bug to notice.
    return kept or provider_names


def _record_engine_runs(runs: list[_MetaEngineRun]) -> None:
    path = _health_ledger_path()
    if not path:
        return
    archive = Archive(path)
    try:
        archive.record_engine_runs([run.to_dict() for run in runs])
    finally:
        archive.close()


def engine_health(*, per_provider: int = 50) -> list[EngineHealthStat]:
    path = _health_ledger_path()
    if not path:
        return []
    archive = Archive(path)
    try:
        return summarize_engine_runs(archive.engine_runs(per_provider=per_provider))
    finally:
        archive.close()


def _annotate_engine_result(result: SearchResult, run: _MetaEngineRun) -> SearchResult:
    metadata = dict(result.metadata)
    metadata["engine_health_score"] = run.health_score
    metadata["engine_latency_ms"] = run.latency_ms
    metadata["engine_result_count"] = run.result_count
    return replace(result, metadata=metadata)


def _annotate_meta_result(
    result: SearchResult,
    *,
    profile: str,
    provider_names: list[str],
    runs: list[_MetaEngineRun],
) -> SearchResult:
    metadata = dict(result.metadata)
    metadata["meta_profile"] = profile
    metadata["meta_providers"] = list(provider_names)
    metadata["meta_engine_runs"] = [
        run.to_dict() for run in sorted(runs, key=lambda item: item.provider)
    ]
    return replace(result, metadata=metadata)


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _meta_engine_health_score(
    *,
    status: str,
    result_count: int,
    latency_ms: int,
    requested: int,
) -> float:
    if status == "error":
        return 0.0
    if status == "empty":
        return 0.35
    useful_ratio = min(result_count / max(requested, 1), 1.0)
    score = 0.75 + 0.25 * useful_ratio
    if latency_ms >= 5_000:
        score -= 0.25
    elif latency_ms >= 2_000:
        score -= 0.15
    elif latency_ms >= 1_000:
        score -= 0.05
    return round(max(0.1, min(score, 1.0)), 3)


def get_provider(name: str) -> SearchProvider:
    if name not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown provider {name!r}; expected one of: {known}")
    return PROVIDERS[name]


def search(
    query: str,
    *,
    provider: str = "ddg",
    limit: int = 10,
    archive_path: str | None = None,
) -> list[SearchResult]:
    if archive_path is None:
        return get_provider(provider).search(query, limit=limit)
    old_archive = os.environ.get("KWR_ARCHIVE")
    os.environ["KWR_ARCHIVE"] = archive_path
    try:
        return get_provider(provider).search(query, limit=limit)
    finally:
        if old_archive is None:
            os.environ.pop("KWR_ARCHIVE", None)
        else:
            os.environ["KWR_ARCHIVE"] = old_archive


def provider_status() -> list[dict[str, str]]:
    return [
        {"provider": "ddg", "status": "ok", "detail": "no-key HTML search fallback"},
        {
            "provider": "feed",
            "status": "ok",
            "detail": "local RSS/Atom/JSON Feed archive; set KWR_ARCHIVE to override path",
        },
        {"provider": "github", "status": "ok", "detail": "gh CLI or GitHub REST; GITHUB_TOKEN optional"},
        {
            "provider": "github_code",
            "status": "ok" if os.environ.get("GITHUB_TOKEN") else "off",
            "detail": "GitHub REST code search with text-match metadata; requires GITHUB_TOKEN",
        },
        {
            "provider": "jina",
            "status": "ok" if os.environ.get("JINA_API_KEY") else "off",
            "detail": "JINA_API_KEY optional; reader does not require it",
        },
        {
            "provider": "searxng",
            "status": "ok" if os.environ.get("KWR_SEARXNG_URL") else "off",
            "detail": "KWR_SEARXNG_URL optional; uses /search?q=...&format=json",
        },
        {
            "provider": "brave",
            "status": "ok" if os.environ.get("BRAVE_SEARCH_API_KEY") else "off",
            "detail": "BRAVE_SEARCH_API_KEY optional; uses Brave Web Search API",
        },
        {
            "provider": "openalex",
            "status": "ok",
            "detail": "official scholarly works API; OPENALEX_API_KEY and OPENALEX_MAILTO optional",
        },
        {
            "provider": "meta",
            "status": "ok",
            "detail": f"health-aware metasearch fan-out; profile={_meta_profile()} providers={','.join(_meta_provider_names(_meta_profile()))}",
        },
    ]


def searxng_preflight(query: str = "katala") -> dict[str, str | int]:
    base_url = os.environ.get("KWR_SEARXNG_URL", "").rstrip("/")
    if not base_url:
        raise FetchError("KWR_SEARXNG_URL is required for SearXNG preflight")
    url = base_url + "/search?" + urlencode(_searxng_params(query))
    response = fetch_url(url, headers={"Accept": "application/json"})
    payload = _parse_json(response.text, url)
    results = payload.get("results")
    if not isinstance(results, list):
        raise FetchError(f"SearXNG JSON response from {url} has no results list")
    return {
        "provider": "searxng",
        "status": "ok",
        "url": response.url,
        "status_code": response.status,
        "result_count": len(results),
    }


def _meta_profile() -> str:
    value = os.environ.get("KWR_META_PROFILE", "broad").strip().lower()
    return value if value in META_PROFILES else "broad"


def _meta_provider_names(profile: str) -> list[str]:
    raw = os.environ.get("KWR_META_PROVIDERS", "").strip()
    if raw:
        return [name.strip() for name in raw.split(",") if name.strip() and name.strip() != "meta"]
    return list(META_PROFILES.get(profile, META_PROFILES["broad"]))


def _rewrite_query_for_provider(query: str, *, provider: str, profile: str) -> str:
    if provider == "openalex":
        if profile == "scholarly":
            return f"{query} paper benchmark evaluation"
        if profile == "broad":
            return f"{query} scholarly research"
    if provider == "github" and profile == "code":
        return f"{query} implementation library"
    if provider in {"ddg", "searxng"} and profile == "docs":
        return f"{query} official documentation"
    if provider in {"ddg", "searxng", "brave"} and profile == "fresh":
        return f"{query} latest"
    return query


def _searxng_params(query: str, *, page: int = 1) -> dict[str, str]:
    params = {"q": query, "format": "json"}
    if page > 1:
        params["pageno"] = str(page)
    env_to_param = {
        "KWR_SEARXNG_CATEGORIES": "categories",
        "KWR_SEARXNG_ENGINES": "engines",
        "KWR_SEARXNG_LANGUAGE": "language",
        "KWR_SEARXNG_TIME_RANGE": "time_range",
        "KWR_SEARXNG_SAFESEARCH": "safesearch",
    }
    for env_name, param_name in env_to_param.items():
        value = os.environ.get(env_name, "").strip()
        if value:
            _validate_searxng_param(env_name, param_name, value)
            params[param_name] = value
    return params


def _validate_searxng_param(env_name: str, param_name: str, value: str) -> None:
    if param_name == "time_range" and value not in {"day", "week", "month", "year"}:
        raise FetchError(f"{env_name} must be one of: day, week, month, year")
    if param_name == "safesearch":
        if not value.isdigit():
            raise FetchError(f"{env_name} must be an integer from 0 to 2")
        level = int(value)
        if level < 0 or level > 2:
            raise FetchError(f"{env_name} must be an integer from 0 to 2")


def _parse_json(text: str, url: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"non-JSON response from {redact_url(url)}: {exc}") from exc


def _github_code_params(query: str, *, page: int, per_page: int) -> dict[str, str | int]:
    return {"q": query, "sort": "indexed", "per_page": min(per_page, 100), "page": page}


def _github_code_headers(token: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github.text-match+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_code_invalid_query(exc: FetchError) -> bool:
    return str(exc).startswith("HTTP 422 ")


def _brave_params(query: str, *, limit: int, offset: int = 0) -> dict[str, str | int]:
    params: dict[str, str | int] = {"q": query, "count": min(limit, 20)}
    if offset:
        params["offset"] = offset
    for env_name, param_name in (
        ("BRAVE_SEARCH_COUNTRY", "country"),
        ("BRAVE_SEARCH_LANG", "search_lang"),
        ("BRAVE_UI_LANG", "ui_lang"),
    ):
        value = os.environ.get(env_name, "").strip()
        if value:
            params[param_name] = value
    freshness = _brave_freshness(os.environ.get("BRAVE_FRESHNESS", ""))
    if freshness:
        params["freshness"] = freshness
    safesearch = _brave_safesearch(os.environ.get("BRAVE_SAFESEARCH", ""))
    if safesearch:
        params["safesearch"] = safesearch
    return params


def _brave_freshness(value: str) -> str:
    freshness = value.strip()
    if not freshness:
        return ""
    mapped = {
        "day": "pd",
        "week": "pw",
        "month": "pm",
        "year": "py",
        "past_day": "pd",
        "past_week": "pw",
        "past_month": "pm",
        "past_year": "py",
    }.get(freshness.lower(), freshness)
    if mapped in {"pd", "pw", "pm", "py"} or _brave_date_range(mapped):
        return mapped
    raise FetchError("BRAVE_FRESHNESS must be day/week/month/year, pd/pw/pm/py, or YYYY-MM-DDtoYYYY-MM-DD")


def _brave_date_range(value: str) -> bool:
    start, sep, end = value.partition("to")
    return (
        sep == "to"
        and len(start) == 10
        and len(end) == 10
        and start[4] == "-"
        and start[7] == "-"
        and end[4] == "-"
        and end[7] == "-"
        and start.replace("-", "").isdigit()
        and end.replace("-", "").isdigit()
    )


def _brave_safesearch(value: str) -> str:
    safesearch = value.strip().lower()
    if not safesearch:
        return ""
    if safesearch in {"off", "moderate", "strict"}:
        return safesearch
    raise FetchError("BRAVE_SAFESEARCH must be off, moderate, or strict")


def _secret_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.startswith("op://"):
        return value
    if not shutil.which("op"):
        return ""
    try:
        completed = subprocess.run(
            ["op", "read", value], text=True, capture_output=True, check=False, timeout=OP_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


OPENALEX_SELECT = ",".join(
    [
        "id",
        "doi",
        "title",
        "display_name",
        "publication_year",
        "publication_date",
        "type",
        "cited_by_count",
        "is_retracted",
        "open_access",
        "primary_location",
        "best_oa_location",
        # `content_url` (singular) is not a select field and OpenAlex rejects the whole
        # request with HTTP 400, so every live openalex search failed while the fixtures
        # kept passing. The API returns an object of per-format URLs under `content_urls`.
        "content_urls",
        "abstract_inverted_index",
    ]
)


def _openalex_params(query: str, *, limit: int, cursor: str = "*") -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "search": query,
        "per_page": min(limit, 100),
        "cursor": cursor,
        "sort": "relevance_score:desc",
        "select": OPENALEX_SELECT,
    }
    _add_openalex_credentials(params)
    filters = [
        value
        for value in (
            _openalex_language_filter(os.environ.get("OPENALEX_LANGUAGE", "")),
            _openalex_year_filter(os.environ.get("OPENALEX_YEAR", "")),
            _openalex_date_filter("from_publication_date", os.environ.get("OPENALEX_FROM_DATE", "")),
            _openalex_date_filter("to_publication_date", os.environ.get("OPENALEX_TO_DATE", "")),
            _openalex_bool_filter("has_content.pdf", os.environ.get("OPENALEX_HAS_PDF", "")),
            _openalex_bool_filter("has_abstract", os.environ.get("OPENALEX_HAS_ABSTRACT", "")),
        )
        if value
    ]
    if filters:
        params["filter"] = ",".join(filters)
    return params


def _openalex_next_cursor(payload: dict) -> str:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return ""
    cursor = meta.get("next_cursor")
    return str(cursor) if cursor else ""


def _openalex_language_filter(value: str) -> str:
    language = value.strip()
    if not language or language.lower() == "all":
        return ""
    iso2 = language.split("-", 1)[0].split("_", 1)[0].lower()
    if len(iso2) == 2 and iso2.isalpha():
        return f"language:{iso2}"
    return ""


def _openalex_year_filter(value: str) -> str:
    year = value.strip()
    if len(year) == 4 and year.isdigit():
        return f"publication_year:{year}"
    return ""


def _openalex_date_filter(name: str, value: str) -> str:
    date = value.strip()
    if not date:
        return ""
    if _iso_date(date):
        return f"{name}:{date}"
    raise FetchError(f"{name.upper()} must use YYYY-MM-DD")


def _openalex_bool_filter(name: str, value: str) -> str:
    raw = value.strip().lower()
    if not raw:
        return ""
    if raw in {"1", "true", "yes", "on"}:
        return f"{name}:true"
    if raw in {"0", "false", "no", "off"}:
        return f"{name}:false"
    raise FetchError(f"{name.upper()} must be true or false")


def _iso_date(value: str) -> bool:
    return (
        len(value) == 10
        and value[4] == "-"
        and value[7] == "-"
        and value.replace("-", "").isdigit()
    )

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .archive import DEFAULT_ARCHIVE, Archive
from .brief import build_brief
from .evaluation import build_eval_report, run_eval
from .investigation import build_investigation_report, sort_web_candidates
from .models import PageSnapshot, SearchResult
from .planner import SearchPlanStep, build_search_plan
from .providers import PROVIDERS, search
from .reader import read_url
from .workflow import search_with_plan

PROTOCOL_VERSION = "2025-11-25"
ARCHIVE_ROOT_ENV = "KWR_MCP_ARCHIVE_ROOT"
ARCHIVE_SUFFIXES = {".sqlite", ".sqlite3", ".db"}
PROVIDER_NAMES = sorted(PROVIDERS)


def _provider_schema(default: str = "ddg") -> dict[str, object]:
    return {"type": "string", "default": default, "enum": PROVIDER_NAMES}


TOOLS = [
    {
        "name": "kwr.plan",
        "description": "Decompose a research question into bounded search queries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_subqueries": {"type": "integer", "default": 4},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kwr.search",
        "description": "Search the web with a configured katala-web-research provider.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "provider": _provider_schema(),
                "limit": {"type": "integer", "default": 5},
                "archive": {"type": "string", "default": str(DEFAULT_ARCHIVE)},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kwr.eval",
        "description": "Run deterministic research-quality benchmark cases.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_score": {"type": "integer", "default": 80},
                "max_subqueries": {"type": "integer", "default": 4},
            },
        },
    },
    {
        "name": "kwr.read",
        "description": "Read a URL into clean text using Jina Reader with direct HTTP fallback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "reader": {"type": "string", "default": "auto"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "kwr.query",
        "description": "Search archived web page content in the local SQLite archive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "terms": {"type": "string"},
                "archive": {"type": "string", "default": str(DEFAULT_ARCHIVE)},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["terms"],
        },
    },
    {
        "name": "kwr.repos_query",
        "description": "Search indexed local Git repository documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "terms": {"type": "string"},
                "archive": {"type": "string", "default": str(DEFAULT_ARCHIVE)},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["terms"],
        },
    },
    {
        "name": "kwr.feeds_query",
        "description": "Search archived RSS/Atom/JSON feed items in the local SQLite archive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "terms": {"type": "string"},
                "archive": {"type": "string", "default": str(DEFAULT_ARCHIVE)},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["terms"],
        },
    },
    {
        "name": "kwr.brief",
        "description": "Build a combined research brief from web candidates and local repository evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "archive": {"type": "string", "default": str(DEFAULT_ARCHIVE)},
                "provider": _provider_schema(),
                "web_limit": {"type": "integer", "default": 5},
                "repo_limit": {"type": "integer", "default": 5},
                "feed_limit": {"type": "integer", "default": 0},
                "expand_queries": {"type": "boolean", "default": False},
                "max_subqueries": {"type": "integer", "default": 4},
                "no_web": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kwr.investigate",
        "description": "Run web search, local repo lookup, selected URL capture, and return an investigation report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "archive": {"type": "string", "default": str(DEFAULT_ARCHIVE)},
                "provider": _provider_schema(),
                "reader": {"type": "string", "default": "auto"},
                "web_limit": {"type": "integer", "default": 8},
                "repo_limit": {"type": "integer", "default": 6},
                "feed_limit": {"type": "integer", "default": 0},
                "read_top": {"type": "integer", "default": 3},
                "expand_queries": {"type": "boolean", "default": False},
                "max_subqueries": {"type": "integer", "default": 4},
                "no_web": {"type": "boolean", "default": False},
            },
            "required": ["query"],
        },
    },
]


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    try:
        if method == "initialize":
            return result_response(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "katala-web-research", "version": "0.1.0"},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return result_response(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = request.get("params") or {}
            return result_response(request_id, call_tool(str(params.get("name") or ""), params.get("arguments") or {}))
        return error_response(request_id, -32601, f"method not found: {method}")
    except Exception as exc:
        return error_response(request_id, -32000, str(exc))


def _archive_arg(arguments: dict[str, Any]) -> str:
    """The `archive` tool argument comes from the model, so it may only name a database inside the root.

    The root is the default archive's directory, or KWR_MCP_ARCHIVE_ROOT when the operator sets it.
    Relative paths keep their meaning (relative to the working directory); symlinks and `..` are
    resolved before the check, so neither can step outside.
    """
    raw = arguments.get("archive")
    if raw is None:
        return str(DEFAULT_ARCHIVE)
    root = Path(os.environ.get(ARCHIVE_ROOT_ENV) or DEFAULT_ARCHIVE.parent).resolve()
    path = Path(str(raw)).resolve()
    if path.suffix.lower() not in ARCHIVE_SUFFIXES or not path.is_relative_to(root):
        raise ValueError(
            f"archive must be a {'/'.join(sorted(ARCHIVE_SUFFIXES))} file inside the archive root; "
            f"the operator can widen it with {ARCHIVE_ROOT_ENV}"
        )
    return str(raw)


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "kwr.plan":
        plan = build_search_plan(
            str(arguments["query"]),
            max_subqueries=int(arguments.get("max_subqueries", 4)),
        )
        return text_result(json.dumps([step.to_dict() for step in plan], ensure_ascii=False, indent=2))
    if name == "kwr.search":
        results = search(
            str(arguments["query"]),
            provider=str(arguments.get("provider", "ddg")),
            limit=int(arguments.get("limit", 5)),
            archive_path=_archive_arg(arguments),
        )
        return text_result(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
    if name == "kwr.read":
        page = read_url(str(arguments["url"]), reader=str(arguments.get("reader", "auto")))
        return text_result(page.content)
    if name == "kwr.eval":
        summary = run_eval(
            min_score=int(arguments.get("min_score", 80)),
            max_subqueries=int(arguments.get("max_subqueries", 4)),
        )
        return text_result(build_eval_report(summary))
    if name == "kwr.query":
        archive = Archive(_archive_arg(arguments))
        try:
            hits = archive.query(str(arguments["terms"]), limit=int(arguments.get("limit", 5)))
        finally:
            archive.close()
        return text_result(json.dumps([hit.to_dict() for hit in hits], ensure_ascii=False, indent=2))
    if name == "kwr.repos_query":
        archive = Archive(_archive_arg(arguments))
        try:
            repo_hits = archive.query_repos(str(arguments["terms"]), limit=int(arguments.get("limit", 5)))
        finally:
            archive.close()
        return text_result(json.dumps([hit.to_dict() for hit in repo_hits], ensure_ascii=False, indent=2))
    if name == "kwr.feeds_query":
        archive = Archive(_archive_arg(arguments))
        try:
            feed_hits = archive.query_feeds(str(arguments["terms"]), limit=int(arguments.get("limit", 5)))
        finally:
            archive.close()
        return text_result(json.dumps([hit.to_dict() for hit in feed_hits], ensure_ascii=False, indent=2))
    if name == "kwr.brief":
        query = str(arguments["query"])
        archive_path = _archive_arg(arguments)
        web_results: list[SearchResult] = []
        search_plan: list[SearchPlanStep] = []
        if not bool(arguments.get("no_web", False)):
            web_results, search_plan = search_with_plan(
                query,
                provider=str(arguments.get("provider", "ddg")),
                limit=int(arguments.get("web_limit", 5)),
                expand_queries=bool(arguments.get("expand_queries", False)),
                max_subqueries=int(arguments.get("max_subqueries", 4)),
                archive_path=archive_path,
            )
        feed_limit = int(arguments.get("feed_limit", 0))
        archive = Archive(archive_path)
        try:
            repo_hits = archive.query_repos(query, limit=int(arguments.get("repo_limit", 5)))
            feed_hits = archive.query_feeds(query, limit=feed_limit) if feed_limit > 0 else []
        finally:
            archive.close()
        return text_result(
            build_brief(
                query=query,
                web_results=web_results,
                repo_hits=repo_hits,
                archive_path=archive_path,
                search_plan=search_plan,
                feed_hits=feed_hits,
            )
        )
    if name == "kwr.investigate":
        query = str(arguments["query"])
        archive_path = _archive_arg(arguments)
        provider = str(arguments.get("provider", "ddg"))
        web_results = []
        search_plan = []
        if not bool(arguments.get("no_web", False)):
            web_results, search_plan = search_with_plan(
                query,
                provider=provider,
                limit=int(arguments.get("web_limit", 8)),
                expand_queries=bool(arguments.get("expand_queries", False)),
                max_subqueries=int(arguments.get("max_subqueries", 4)),
                archive_path=archive_path,
            )
        feed_limit = int(arguments.get("feed_limit", 0))
        archive = Archive(archive_path)
        pages: list[PageSnapshot] = []
        try:
            repo_hits = archive.query_repos(query, limit=int(arguments.get("repo_limit", 6)))
            feed_hits = archive.query_feeds(query, limit=feed_limit) if feed_limit > 0 else []
            if web_results:
                archive.store_run(query, provider, web_results)
            for result in sort_web_candidates(web_results)[: max(int(arguments.get("read_top", 3)), 0)]:
                try:
                    page = read_url(result.url, reader=str(arguments.get("reader", "auto")))
                except Exception as exc:
                    page = PageSnapshot(
                        url=result.url,
                        title=result.title,
                        content=f"Read failed: {exc}",
                        source="error",
                        fetched_at="",
                    )
                pages.append(page)
                archive.upsert_page(page)
        finally:
            archive.close()
        return text_result(
            build_investigation_report(
                query=query,
                provider=provider,
                archive_path=archive_path,
                web_results=web_results,
                repo_hits=repo_hits,
                pages=pages,
                search_plan=search_plan,
                feed_hits=feed_hits,
            )
        )
    raise ValueError(f"unknown tool: {name}")


def result_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def text_result(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def main() -> int:
    while True:
        try:
            message = read_framed_message(sys.stdin.buffer)
        except (ValueError, UnicodeDecodeError):
            # A single malformed frame must not kill the long-lived server.
            continue
        if message is None:
            return 0
        response = handle_request(message)
        if response is not None:
            write_framed_message(sys.stdout.buffer, response)


def read_framed_message(stream) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if line == b"":
            return None
        line = line.decode("ascii", errors="replace").strip()
        if not line:
            break
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    return json.loads(stream.read(length).decode("utf-8"))


def write_framed_message(stream, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


if __name__ == "__main__":
    raise SystemExit(main())

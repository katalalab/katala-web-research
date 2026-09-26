"""Pure provider response normalization; no credentials or network access."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

from .models import SearchResult
from .text import collapse_space, normalize_url


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._in_title = False
        self._in_snippet = False
        self._snippet_tag = ""
        self._current_title: list[str] = []
        self._current_url = ""
        self._current_snippet: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._flush()
            self._in_title = True
            self._current_url = normalize_url(attr.get("href") or "")
        elif "result__snippet" in classes:
            self._in_snippet = True
            self._snippet_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        # Close only on the snippet's own opening tag so a nested </a> or </b>
        # inside the snippet does not truncate it.
        if self._in_snippet and tag == self._snippet_tag:
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        title = collapse_space(" ".join(self._current_title))
        if title and self._current_url:
            self.results.append(
                SearchResult(
                    title=title,
                    url=self._current_url,
                    snippet=collapse_space(" ".join(self._current_snippet)),
                    source="ddg",
                )
            )
        self._current_title = []
        self._current_url = ""
        self._current_snippet = []

def _github_snippet(item: dict) -> str:
    parts = []
    if item.get("language"):
        parts.append(f"language={item['language']}")
    if item.get("description"):
        parts.append(str(item["description"]))
    if item.get("stargazersCount") is not None:
        parts.append(f"stars={item['stargazersCount']}")
    if item.get("updatedAt"):
        parts.append(f"updated={item['updatedAt']}")
    license_name = _github_license_name(item.get("license"))
    if license_name:
        parts.append(f"license={license_name}")
    topics = item.get("topics") or []
    if topics:
        parts.append("topics=" + ",".join(str(topic) for topic in topics[:6]))
    if item.get("isFork"):
        parts.append("fork=true")
    return " | ".join(parts)

def _github_metadata(item: dict) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    mappings = {
        "package_name": "name",
        "maintainer": "ownerLogin",
        "language": "language",
        "homepage": "homepage",
        "source_code_url": "cloneUrl",
    }
    for out_key, item_key in mappings.items():
        value = item.get(item_key)
        if value:
            metadata[out_key] = value
    if item.get("stargazersCount") is not None:
        metadata["stars"] = item["stargazersCount"]
    topics = item.get("topics") or []
    if topics:
        metadata["topics"] = list(topics)
    license_name = _github_license_name(item.get("license"))
    if license_name:
        metadata["license_name"] = license_name
    license_url = _github_license_url(item.get("license"))
    if license_url:
        metadata["license_url"] = license_url
    return metadata

def _github_rest_item(item: dict) -> dict[str, Any]:
    owner = item.get("owner") or {}
    return {
        "name": item.get("name"),
        "description": item.get("description"),
        "stargazersCount": item.get("stargazers_count"),
        "updatedAt": item.get("updated_at"),
        "isFork": item.get("fork"),
        "language": item.get("language"),
        "topics": item.get("topics") or [],
        "license": item.get("license"),
        "homepage": item.get("homepage"),
        "cloneUrl": item.get("clone_url"),
        "ownerLogin": owner.get("login"),
    }

def _github_license_name(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("spdx_id") or "").strip()
    return ""

def _github_license_url(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    spdx_id = str(value.get("spdx_id") or "").strip()
    if not spdx_id or spdx_id.upper() == "NOASSERTION":
        return ""
    return f"https://spdx.org/licenses/{spdx_id}.html"

def _github_code_fragment(value: object) -> str:
    if not isinstance(value, list):
        return ""
    fragments: list[str] = []
    for match in value:
        if not isinstance(match, dict):
            continue
        if match.get("object_type") != "FileContent" or match.get("property") != "content":
            continue
        fragment = collapse_space(str(match.get("fragment") or ""))
        if fragment:
            fragments.append(fragment)
    return " ... ".join(fragments[:3])

def _github_code_title(repo_name: str, path: str, url: object) -> str:
    if repo_name and path:
        return f"{repo_name} - {path}"
    if path:
        return path
    return str(url or "")

def _github_code_snippet(repo: dict, path: str, fragment: str) -> str:
    parts = []
    description = repo.get("description")
    if description:
        parts.append(str(description))
    if path:
        parts.append(f"path={path}")
    language = repo.get("language")
    if language:
        parts.append(f"language={language}")
    if fragment:
        parts.append(fragment[:420])
    return " | ".join(parts)

def _openalex_url(item: dict) -> str:
    primary_location = item.get("primary_location") or {}
    if primary_location.get("landing_page_url"):
        return str(primary_location["landing_page_url"])
    best_oa_location = item.get("best_oa_location") or {}
    if best_oa_location.get("landing_page_url"):
        return str(best_oa_location["landing_page_url"])
    if item.get("doi"):
        return str(item["doi"])
    return str(item.get("id") or "")

def _openalex_metadata(item: dict) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    mappings = {
        "openalex_id": "id",
        "doi": "doi",
        "work_type": "type",
        "publication_year": "publication_year",
        "cited_by_count": "cited_by_count",
    }
    for out_key, item_key in mappings.items():
        value = item.get(item_key)
        if value is not None and value != "":
            metadata[out_key] = value
    content_urls = item.get("content_urls")
    if isinstance(content_urls, dict) and content_urls.get("pdf"):
        metadata["content_url"] = content_urls["pdf"]
    _add_openalex_location_metadata(metadata, "primary", item.get("primary_location"))
    _add_openalex_location_metadata(metadata, "best_oa", item.get("best_oa_location"))
    open_access = item.get("open_access") or {}
    if isinstance(open_access, dict):
        for key in ("is_oa", "oa_status"):
            value = open_access.get(key)
            if value is not None and value != "":
                metadata[f"open_access_{key}"] = value
    return metadata

def _add_openalex_location_metadata(metadata: dict[str, Any], prefix: str, value: object) -> None:
    if not isinstance(value, dict):
        return
    for key in ("landing_page_url", "pdf_url", "is_oa", "license", "version"):
        field_value = value.get(key)
        if field_value is not None and field_value != "":
            metadata[f"{prefix}_{key}"] = field_value
    source = value.get("source")
    if isinstance(source, dict):
        for key in ("id", "display_name", "type"):
            field_value = source.get(key)
            if field_value is not None and field_value != "":
                metadata[f"{prefix}_source_{key}"] = field_value

def _openalex_snippet(item: dict) -> str:
    parts = []
    abstract = _abstract_from_inverted_index(item.get("abstract_inverted_index"))
    if abstract:
        parts.append(abstract[:420])
    if item.get("publication_year"):
        parts.append(f"year={item['publication_year']}")
    if item.get("type"):
        parts.append(f"type={item['type']}")
    if item.get("cited_by_count") is not None:
        parts.append(f"citations={item['cited_by_count']}")
    if item.get("is_retracted"):
        parts.append("retracted=true")
    open_access = item.get("open_access") or {}
    if open_access.get("is_oa") is not None:
        parts.append(f"oa={str(open_access.get('is_oa')).lower()}")
    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") or {}
    if source.get("display_name"):
        parts.append(f"source={source['display_name']}")
    return " | ".join(parts)

def _abstract_from_inverted_index(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in value.items():
        if not isinstance(word, str) or not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int):
                positions.append((index, word))
    return " ".join(word for _idx, word in sorted(positions))

def _year_as_date(value: object) -> str | None:
    if isinstance(value, int):
        return f"{value}-01-01"
    return None

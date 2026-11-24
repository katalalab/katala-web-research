from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    published_at: str | None = None
    rank: int = 0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PageSnapshot:
    url: str
    title: str
    content: str
    source: str
    fetched_at: str
    status_code: int | None = None
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArchiveHit:
    url: str
    title: str
    snippet: str
    rank: float
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FeedSource:
    url: str
    title: str = ""
    kind: str = ""
    added_at: str = ""
    last_fetched_at: str = ""
    status: str = "pending"
    health_score: float = 0.0
    error_kind: str = ""
    last_item_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FeedItem:
    source_url: str
    url: str
    title: str
    summary: str = ""
    source_title: str = ""
    published_at: str | None = None
    fetched_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FeedHit:
    url: str
    title: str
    snippet: str
    rank: float
    source_url: str
    source_title: str
    published_at: str | None
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProjectItem:
    kind: str
    repository: str
    number: int
    title: str
    url: str
    state: str
    updated_at: str
    labels: list[str] = field(default_factory=list)
    priority: str = "p3"
    status: str = ""
    source: str = "github"

    @property
    def item_key(self) -> str:
        return f"{self.repository}#{self.number}:{self.kind}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"item_key": self.item_key}


@dataclass(slots=True)
class ProjectHit:
    kind: str
    repository: str
    number: int
    title: str
    url: str
    state: str
    updated_at: str
    labels: list[str]
    priority: str
    status: str
    source: str
    rank: float
    snippet: str

    @property
    def item_key(self) -> str:
        return f"{self.repository}#{self.number}:{self.kind}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"item_key": self.item_key}


@dataclass(slots=True)
class RepoDocument:
    repo_path: str
    repo_name: str
    rel_path: str
    title: str
    content: str
    kind: str
    indexed_at: str
    context: str = ""
    file_size: int = 0
    file_mtime_ns: int = 0
    content_sha256: str = ""

    @property
    def document_url(self) -> str:
        return f"repo://{self.repo_name}/{self.rel_path}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"document_url": self.document_url}


@dataclass(slots=True)
class RepoHit:
    repo_path: str
    repo_name: str
    rel_path: str
    title: str
    snippet: str
    kind: str
    rank: float
    indexed_at: str

    @property
    def document_url(self) -> str:
        return f"repo://{self.repo_name}/{self.rel_path}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"document_url": self.document_url}

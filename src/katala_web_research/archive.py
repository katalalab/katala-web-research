from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import (
    ArchiveHit,
    FeedHit,
    FeedItem,
    FeedSource,
    PageSnapshot,
    ProjectHit,
    ProjectItem,
    RepoDocument,
    RepoHit,
    SearchResult,
    utc_now_iso,
)

DEFAULT_ARCHIVE = Path(".katala-web-research/archive.sqlite")


class Archive:
    def __init__(self, path: str | Path = DEFAULT_ARCHIVE) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY,
              query TEXT NOT NULL,
              provider TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_results (
              id INTEGER PRIMARY KEY,
              run_id INTEGER NOT NULL REFERENCES runs(id),
              rank INTEGER NOT NULL,
              score REAL NOT NULL,
              title TEXT NOT NULL,
              url TEXT NOT NULL,
              snippet TEXT NOT NULL,
              source TEXT NOT NULL,
              published_at TEXT
            );
            CREATE TABLE IF NOT EXISTS pages (
              id INTEGER PRIMARY KEY,
              url TEXT NOT NULL UNIQUE,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              source TEXT NOT NULL,
              fetched_at TEXT NOT NULL,
              status_code INTEGER,
              content_type TEXT
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts
              USING fts5(title, content, url UNINDEXED, content='pages', content_rowid='id');
            CREATE TABLE IF NOT EXISTS repo_documents (
              id INTEGER PRIMARY KEY,
              repo_path TEXT NOT NULL,
              repo_name TEXT NOT NULL,
              rel_path TEXT NOT NULL,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              kind TEXT NOT NULL,
              indexed_at TEXT NOT NULL,
              context TEXT NOT NULL DEFAULT '',
              file_size INTEGER NOT NULL DEFAULT 0,
              file_mtime_ns INTEGER NOT NULL DEFAULT 0,
              content_sha256 TEXT NOT NULL DEFAULT '',
              UNIQUE(repo_path, rel_path)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS repo_documents_fts
              USING fts5(repo_name, rel_path, title, context, content, kind UNINDEXED, content='repo_documents', content_rowid='id');
            CREATE TABLE IF NOT EXISTS feed_sources (
              id INTEGER PRIMARY KEY,
              url TEXT NOT NULL UNIQUE,
              title TEXT NOT NULL DEFAULT '',
              kind TEXT NOT NULL DEFAULT '',
              added_at TEXT NOT NULL,
              last_fetched_at TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'pending',
              health_score REAL NOT NULL DEFAULT 0,
              error_kind TEXT NOT NULL DEFAULT '',
              last_item_count INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS feed_items (
              id INTEGER PRIMARY KEY,
              source_url TEXT NOT NULL REFERENCES feed_sources(url),
              url TEXT NOT NULL,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              source_title TEXT NOT NULL DEFAULT '',
              published_at TEXT,
              fetched_at TEXT NOT NULL,
              UNIQUE(source_url, url)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS feed_items_fts
              USING fts5(title, summary, source_title, url UNINDEXED, source_url UNINDEXED, content='feed_items', content_rowid='id');
            CREATE TABLE IF NOT EXISTS project_items (
              id INTEGER PRIMARY KEY,
              kind TEXT NOT NULL,
              repository TEXT NOT NULL,
              number INTEGER NOT NULL,
              title TEXT NOT NULL,
              url TEXT NOT NULL,
              state TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              labels_json TEXT NOT NULL,
              labels_text TEXT NOT NULL,
              priority TEXT NOT NULL DEFAULT 'p3',
              status TEXT NOT NULL DEFAULT '',
              source TEXT NOT NULL DEFAULT 'github',
              UNIQUE(kind, repository, number)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS project_items_fts
              USING fts5(repository, title, labels_text, priority, status, url UNINDEXED, kind UNINDEXED, content='project_items', content_rowid='id');
            CREATE TABLE IF NOT EXISTS engine_runs (
              id INTEGER PRIMARY KEY,
              provider TEXT NOT NULL,
              status TEXT NOT NULL,
              latency_ms INTEGER NOT NULL,
              result_count INTEGER NOT NULL,
              error_kind TEXT NOT NULL DEFAULT '',
              recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS engine_runs_provider ON engine_runs(provider, id DESC);
            CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
              INSERT INTO pages_fts(rowid, title, content, url)
              VALUES (new.id, new.title, new.content, new.url);
            END;
            CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
              INSERT INTO pages_fts(pages_fts, rowid, title, content, url)
              VALUES('delete', old.id, old.title, old.content, old.url);
            END;
            CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
              INSERT INTO pages_fts(pages_fts, rowid, title, content, url)
              VALUES('delete', old.id, old.title, old.content, old.url);
              INSERT INTO pages_fts(rowid, title, content, url)
              VALUES (new.id, new.title, new.content, new.url);
            END;
            CREATE TRIGGER IF NOT EXISTS repo_documents_ai AFTER INSERT ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(rowid, repo_name, rel_path, title, context, content, kind)
              VALUES (new.id, new.repo_name, new.rel_path, new.title, new.context, new.content, new.kind);
            END;
            CREATE TRIGGER IF NOT EXISTS repo_documents_ad AFTER DELETE ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(repo_documents_fts, rowid, repo_name, rel_path, title, context, content, kind)
              VALUES('delete', old.id, old.repo_name, old.rel_path, old.title, old.context, old.content, old.kind);
            END;
            CREATE TRIGGER IF NOT EXISTS repo_documents_au AFTER UPDATE ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(repo_documents_fts, rowid, repo_name, rel_path, title, context, content, kind)
              VALUES('delete', old.id, old.repo_name, old.rel_path, old.title, old.context, old.content, old.kind);
              INSERT INTO repo_documents_fts(rowid, repo_name, rel_path, title, context, content, kind)
              VALUES (new.id, new.repo_name, new.rel_path, new.title, new.context, new.content, new.kind);
            END;
            CREATE TRIGGER IF NOT EXISTS feed_items_ai AFTER INSERT ON feed_items BEGIN
              INSERT INTO feed_items_fts(rowid, title, summary, source_title, url, source_url)
              VALUES (new.id, new.title, new.summary, new.source_title, new.url, new.source_url);
            END;
            CREATE TRIGGER IF NOT EXISTS feed_items_ad AFTER DELETE ON feed_items BEGIN
              INSERT INTO feed_items_fts(feed_items_fts, rowid, title, summary, source_title, url, source_url)
              VALUES('delete', old.id, old.title, old.summary, old.source_title, old.url, old.source_url);
            END;
            CREATE TRIGGER IF NOT EXISTS feed_items_au AFTER UPDATE ON feed_items BEGIN
              INSERT INTO feed_items_fts(feed_items_fts, rowid, title, summary, source_title, url, source_url)
              VALUES('delete', old.id, old.title, old.summary, old.source_title, old.url, old.source_url);
              INSERT INTO feed_items_fts(rowid, title, summary, source_title, url, source_url)
              VALUES (new.id, new.title, new.summary, new.source_title, new.url, new.source_url);
            END;
            CREATE TRIGGER IF NOT EXISTS project_items_ai AFTER INSERT ON project_items BEGIN
              INSERT INTO project_items_fts(rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES (new.id, new.repository, new.title, new.labels_text, new.priority, new.status, new.url, new.kind);
            END;
            CREATE TRIGGER IF NOT EXISTS project_items_ad AFTER DELETE ON project_items BEGIN
              INSERT INTO project_items_fts(project_items_fts, rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES('delete', old.id, old.repository, old.title, old.labels_text, old.priority, old.status, old.url, old.kind);
            END;
            CREATE TRIGGER IF NOT EXISTS project_items_au AFTER UPDATE ON project_items BEGIN
              INSERT INTO project_items_fts(project_items_fts, rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES('delete', old.id, old.repository, old.title, old.labels_text, old.priority, old.status, old.url, old.kind);
              INSERT INTO project_items_fts(rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES (new.id, new.repository, new.title, new.labels_text, new.priority, new.status, new.url, new.kind);
            END;
            """
        )
        self._ensure_repo_document_columns()
        self._ensure_repo_document_fts_schema()
        self.conn.commit()

    def _ensure_repo_document_columns(self) -> None:
        existing = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(repo_documents)").fetchall()
        }
        migrations = {
            "file_size": "ALTER TABLE repo_documents ADD COLUMN file_size INTEGER NOT NULL DEFAULT 0",
            "file_mtime_ns": "ALTER TABLE repo_documents ADD COLUMN file_mtime_ns INTEGER NOT NULL DEFAULT 0",
            "content_sha256": "ALTER TABLE repo_documents ADD COLUMN content_sha256 TEXT NOT NULL DEFAULT ''",
            "context": "ALTER TABLE repo_documents ADD COLUMN context TEXT NOT NULL DEFAULT ''",
        }
        for column, statement in migrations.items():
            if column not in existing:
                self.conn.execute(statement)

    def _ensure_repo_document_fts_schema(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(repo_documents_fts)").fetchall()
        }
        if "context" in columns:
            return
        self.conn.executescript(
            """
            DROP TRIGGER IF EXISTS repo_documents_ai;
            DROP TRIGGER IF EXISTS repo_documents_ad;
            DROP TRIGGER IF EXISTS repo_documents_au;
            DROP TABLE IF EXISTS repo_documents_fts;
            CREATE VIRTUAL TABLE repo_documents_fts
              USING fts5(repo_name, rel_path, title, context, content, kind UNINDEXED, content='repo_documents', content_rowid='id');
            CREATE TRIGGER repo_documents_ai AFTER INSERT ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(rowid, repo_name, rel_path, title, context, content, kind)
              VALUES (new.id, new.repo_name, new.rel_path, new.title, new.context, new.content, new.kind);
            END;
            CREATE TRIGGER repo_documents_ad AFTER DELETE ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(repo_documents_fts, rowid, repo_name, rel_path, title, context, content, kind)
              VALUES('delete', old.id, old.repo_name, old.rel_path, old.title, old.context, old.content, old.kind);
            END;
            CREATE TRIGGER repo_documents_au AFTER UPDATE ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(repo_documents_fts, rowid, repo_name, rel_path, title, context, content, kind)
              VALUES('delete', old.id, old.repo_name, old.rel_path, old.title, old.context, old.content, old.kind);
              INSERT INTO repo_documents_fts(rowid, repo_name, rel_path, title, context, content, kind)
              VALUES (new.id, new.repo_name, new.rel_path, new.title, new.context, new.content, new.kind);
            END;
            INSERT INTO repo_documents_fts(rowid, repo_name, rel_path, title, context, content, kind)
              SELECT id, repo_name, rel_path, title, context, content, kind FROM repo_documents;
            """
        )

    def store_run(self, query: str, provider: str, results: list[SearchResult]) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(query, provider, created_at) VALUES (?, ?, ?)",
            (query, provider, utc_now_iso()),
        )
        run_id: int = cur.lastrowid or 0
        self.conn.executemany(
            """
            INSERT INTO search_results(
              run_id, rank, score, title, url, snippet, source, published_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    result.rank,
                    result.score,
                    result.title,
                    result.url,
                    result.snippet,
                    result.source,
                    result.published_at,
                )
                for result in results
            ],
        )
        self.conn.commit()
        return run_id

    def upsert_page(self, page: PageSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO pages(url, title, content, source, fetched_at, status_code, content_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              title=excluded.title,
              content=excluded.content,
              source=excluded.source,
              fetched_at=excluded.fetched_at,
              status_code=excluded.status_code,
              content_type=excluded.content_type
            """,
            (
                page.url,
                page.title,
                page.content,
                page.source,
                page.fetched_at,
                page.status_code,
                page.content_type,
            ),
        )
        self.conn.commit()

    def page_by_url(self, url: str) -> PageSnapshot | None:
        row = self.conn.execute(
            """
            SELECT url, title, content, source, fetched_at, status_code, content_type
            FROM pages
            WHERE url = ?
            """,
            (url,),
        ).fetchone()
        if row is None:
            return None
        return PageSnapshot(
            url=row["url"],
            title=row["title"],
            content=row["content"],
            source=row["source"],
            fetched_at=row["fetched_at"],
            status_code=row["status_code"],
            content_type=row["content_type"],
        )

    def upsert_repo_document(self, document: RepoDocument) -> None:
        self.conn.execute(_REPO_UPSERT_SQL, _repo_upsert_params(document))
        self.conn.commit()

    def upsert_repo_documents(self, documents: list[RepoDocument], *, batch_size: int = 500) -> int:
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            self.conn.executemany(_REPO_UPSERT_SQL, [_repo_upsert_params(doc) for doc in batch])
        self.conn.commit()
        return len(documents)

    def upsert_feed_source(self, source: FeedSource) -> None:
        added_at = source.added_at or utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO feed_sources(
              url, title, kind, added_at, last_fetched_at, status, health_score,
              error_kind, last_item_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
              title=CASE WHEN excluded.title != '' THEN excluded.title ELSE feed_sources.title END,
              kind=CASE WHEN excluded.kind != '' THEN excluded.kind ELSE feed_sources.kind END,
              last_fetched_at=CASE
                WHEN excluded.last_fetched_at != '' THEN excluded.last_fetched_at
                ELSE feed_sources.last_fetched_at
              END,
              status=CASE
                WHEN excluded.last_fetched_at != '' THEN excluded.status
                ELSE feed_sources.status
              END,
              health_score=CASE
                WHEN excluded.last_fetched_at != '' THEN excluded.health_score
                ELSE feed_sources.health_score
              END,
              error_kind=CASE
                WHEN excluded.last_fetched_at != '' THEN excluded.error_kind
                ELSE feed_sources.error_kind
              END,
              last_item_count=CASE
                WHEN excluded.last_fetched_at != '' THEN excluded.last_item_count
                ELSE feed_sources.last_item_count
              END
            """,
            (
                source.url,
                source.title,
                source.kind,
                added_at,
                source.last_fetched_at,
                source.status,
                source.health_score,
                source.error_kind,
                source.last_item_count,
            ),
        )
        self.conn.commit()

    def feed_sources(self) -> list[FeedSource]:
        rows = self.conn.execute(
            """
            SELECT url, title, kind, added_at, last_fetched_at, status, health_score,
                   error_kind, last_item_count
            FROM feed_sources
            ORDER BY url
            """
        ).fetchall()
        return [
            FeedSource(
                url=row["url"],
                title=row["title"],
                kind=row["kind"],
                added_at=row["added_at"],
                last_fetched_at=row["last_fetched_at"],
                status=row["status"],
                health_score=float(row["health_score"]),
                error_kind=row["error_kind"],
                last_item_count=int(row["last_item_count"]),
            )
            for row in rows
        ]

    def upsert_feed_items(self, items: list[FeedItem]) -> int:
        self.conn.executemany(
            """
            INSERT INTO feed_items(
              source_url, url, title, summary, source_title, published_at, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_url, url) DO UPDATE SET
              title=excluded.title,
              summary=excluded.summary,
              source_title=excluded.source_title,
              published_at=excluded.published_at,
              fetched_at=excluded.fetched_at
            """,
            [
                (
                    item.source_url,
                    item.url,
                    item.title,
                    item.summary,
                    item.source_title,
                    item.published_at,
                    item.fetched_at,
                )
                for item in items
            ],
        )
        self.conn.commit()
        return len(items)

    def upsert_project_items(self, items: list[ProjectItem]) -> int:
        self.conn.executemany(
            """
            INSERT INTO project_items(
              kind, repository, number, title, url, state, updated_at, labels_json,
              labels_text, priority, status, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, repository, number) DO UPDATE SET
              title=excluded.title,
              url=excluded.url,
              state=excluded.state,
              updated_at=excluded.updated_at,
              labels_json=excluded.labels_json,
              labels_text=excluded.labels_text,
              priority=excluded.priority,
              status=excluded.status,
              source=excluded.source
            """,
            [
                (
                    item.kind,
                    item.repository,
                    item.number,
                    item.title,
                    item.url,
                    item.state,
                    item.updated_at,
                    json.dumps(item.labels, ensure_ascii=False),
                    " ".join(item.labels),
                    item.priority,
                    item.status,
                    item.source,
                )
                for item in items
            ],
        )
        self.conn.commit()
        return len(items)

    def repo_document_metadata(self) -> dict[tuple[str, str], tuple[int, int, str]]:
        rows = self.conn.execute(
            "SELECT repo_path, rel_path, file_size, file_mtime_ns, content_sha256 FROM repo_documents"
        ).fetchall()
        return {
            (row["repo_path"], row["rel_path"]): (
                int(row["file_size"]),
                int(row["file_mtime_ns"]),
                str(row["content_sha256"]),
            )
            for row in rows
        }

    def query(self, terms: str, *, limit: int = 10) -> list[ArchiveHit]:
        rows = self.conn.execute(
            """
            SELECT p.url, p.title,
                   snippet(pages_fts, 1, '[', ']', '...', 18) AS snippet,
                   bm25(pages_fts) AS rank,
                   p.fetched_at
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (_fts_query(terms), limit),
        ).fetchall()
        return [
            ArchiveHit(
                url=row["url"],
                title=row["title"],
                snippet=row["snippet"],
                rank=float(row["rank"]),
                fetched_at=row["fetched_at"],
            )
            for row in rows
        ]

    def query_repos(
        self, terms: str, *, limit: int = 10, repo: str = "", path: str = ""
    ) -> list[RepoHit]:
        parsed_terms, inline_repo, inline_path = _parse_repo_query_terms(terms)
        repo = repo or inline_repo
        path = path or inline_path
        filters, params = _repo_filters(repo=repo, path=path)
        rows = self.conn.execute(
            f"""
            SELECT d.repo_path, d.repo_name, d.rel_path, d.title,
                   snippet(repo_documents_fts, 4, '[', ']', '...', 18) AS snippet,
                   d.kind,
                   bm25(repo_documents_fts, 2.0, 1.6, 2.4, 1.8, 1.0) AS rank,
                   d.indexed_at
            FROM repo_documents_fts
            JOIN repo_documents d ON d.id = repo_documents_fts.rowid
            WHERE repo_documents_fts MATCH ?{filters}
            ORDER BY rank
            LIMIT ?
            """,
            (_fts_query(parsed_terms), *params, limit),
        ).fetchall()
        return [
            RepoHit(
                repo_path=row["repo_path"],
                repo_name=row["repo_name"],
                rel_path=row["rel_path"],
                title=row["title"],
                snippet=row["snippet"],
                kind=row["kind"],
                rank=float(row["rank"]),
                indexed_at=row["indexed_at"],
            )
            for row in rows
        ]

    def query_feeds(self, terms: str, *, limit: int = 10) -> list[FeedHit]:
        rows = self.conn.execute(
            """
            SELECT i.url, i.title,
                   snippet(feed_items_fts, 1, '[', ']', '...', 18) AS snippet,
                   bm25(feed_items_fts) AS rank,
                   i.source_url,
                   i.source_title,
                   i.published_at,
                   i.fetched_at
            FROM feed_items_fts
            JOIN feed_items i ON i.id = feed_items_fts.rowid
            WHERE feed_items_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (_fts_query(terms), limit),
        ).fetchall()
        return [
            FeedHit(
                url=row["url"],
                title=row["title"],
                snippet=row["snippet"],
                rank=float(row["rank"]),
                source_url=row["source_url"],
                source_title=row["source_title"],
                published_at=row["published_at"],
                fetched_at=row["fetched_at"],
            )
            for row in rows
        ]

    def record_engine_runs(self, runs: list[dict], *, keep_per_provider: int = 500) -> int:
        recorded_at = utc_now_iso()
        rows = [
            (
                run["provider"],
                run["status"],
                int(run["latency_ms"]),
                int(run["result_count"]),
                run.get("error_kind", ""),
                recorded_at,
            )
            for run in runs
        ]
        if not rows:
            return 0
        self.conn.executemany(
            "INSERT INTO engine_runs(provider, status, latency_ms, result_count, error_kind, recorded_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        # A health ledger that only grows turns into a slow leak nobody reads. Keep a
        # rolling window per engine; older rows cannot change a routing decision anyway.
        self.conn.execute(
            """
            DELETE FROM engine_runs WHERE id IN (
              SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY provider ORDER BY id DESC) AS position
                FROM engine_runs
              ) WHERE position > ?
            )
            """,
            (keep_per_provider,),
        )
        self.conn.commit()
        return len(rows)

    def engine_runs(self, *, per_provider: int = 50) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT provider, status, latency_ms, result_count, error_kind, recorded_at FROM (
              SELECT *, ROW_NUMBER() OVER (PARTITION BY provider ORDER BY id DESC) AS position
              FROM engine_runs
            ) WHERE position <= ?
            """,
            (per_provider,),
        ).fetchall()
        return [dict(row) for row in rows]

    def query_project_items(self, terms: str, *, limit: int = 10) -> list[ProjectHit]:
        rows = self.conn.execute(
            """
            SELECT i.kind, i.repository, i.number, i.title, i.url, i.state, i.updated_at,
                   i.labels_json, i.priority, i.status, i.source,
                   bm25(project_items_fts) AS rank,
                   snippet(project_items_fts, 1, '[', ']', '...', 18) AS snippet
            FROM project_items_fts
            JOIN project_items i ON i.id = project_items_fts.rowid
            WHERE project_items_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (_fts_query(terms), limit),
        ).fetchall()
        return [_project_hit_from_row(row) for row in rows]

    def project_items(self, *, limit: int = 100) -> list[ProjectItem]:
        rows = self.conn.execute(
            """
            SELECT kind, repository, number, title, url, state, updated_at,
                   labels_json, priority, status, source
            FROM project_items
            ORDER BY
              CASE priority
                WHEN 'p0' THEN 0
                WHEN 'p1' THEN 1
                WHEN 'p2' THEN 2
                WHEN 'p3' THEN 3
                ELSE 9
              END,
              updated_at DESC,
              repository,
              number
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            ProjectItem(
                kind=row["kind"],
                repository=row["repository"],
                number=int(row["number"]),
                title=row["title"],
                url=row["url"],
                state=row["state"],
                updated_at=row["updated_at"],
                labels=json.loads(row["labels_json"] or "[]"),
                priority=row["priority"],
                status=row["status"],
                source=row["source"],
            )
            for row in rows
        ]


def _project_hit_from_row(row: sqlite3.Row) -> ProjectHit:
    return ProjectHit(
        kind=row["kind"],
        repository=row["repository"],
        number=int(row["number"]),
        title=row["title"],
        url=row["url"],
        state=row["state"],
        updated_at=row["updated_at"],
        labels=json.loads(row["labels_json"] or "[]"),
        priority=row["priority"],
        status=row["status"],
        source=row["source"],
        rank=float(row["rank"]),
        snippet=row["snippet"],
    )


_REPO_UPSERT_SQL = """
INSERT INTO repo_documents(
  repo_path, repo_name, rel_path, title, content, kind, indexed_at, context,
  file_size, file_mtime_ns, content_sha256
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(repo_path, rel_path) DO UPDATE SET
  repo_name=excluded.repo_name,
  title=excluded.title,
  content=excluded.content,
  kind=excluded.kind,
  indexed_at=excluded.indexed_at,
  context=excluded.context,
  file_size=excluded.file_size,
  file_mtime_ns=excluded.file_mtime_ns,
  content_sha256=excluded.content_sha256
"""


def _repo_upsert_params(document: RepoDocument) -> tuple:
    return (
        document.repo_path,
        document.repo_name,
        document.rel_path,
        document.title,
        document.content,
        document.kind,
        document.indexed_at,
        document.context,
        document.file_size,
        document.file_mtime_ns,
        document.content_sha256,
    )


def _fts_query(terms: str) -> str:
    tokens = [token.replace('"', "") for token in terms.split() if token.strip()]
    if not tokens:
        return '""'
    return " ".join(f'"{token}"' for token in tokens)


def _parse_repo_query_terms(terms: str) -> tuple[str, str, str]:
    query_tokens: list[str] = []
    repo = ""
    path = ""
    for token in terms.split():
        if token.startswith("repo:") and len(token) > len("repo:"):
            repo = repo or token.split(":", 1)[1]
            continue
        if token.startswith("path:") and len(token) > len("path:"):
            path = path or token.split(":", 1)[1]
            continue
        query_tokens.append(token)
    return " ".join(query_tokens), repo, path


def _repo_filters(*, repo: str = "", path: str = "") -> tuple[str, tuple[str, ...]]:
    clauses: list[str] = []
    params: list[str] = []
    if repo:
        clauses.append(" AND d.repo_name = ?")
        params.append(repo)
    if path:
        clauses.append(" AND d.rel_path LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(path)}%")
    return "".join(clauses), tuple(params)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

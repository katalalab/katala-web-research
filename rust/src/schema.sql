CREATE TABLE IF NOT EXISTS engine_runs (
              id INTEGER PRIMARY KEY,
              provider TEXT NOT NULL,
              status TEXT NOT NULL,
              latency_ms INTEGER NOT NULL,
              result_count INTEGER NOT NULL,
              error_kind TEXT NOT NULL DEFAULT '',
              recorded_at TEXT NOT NULL
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
CREATE INDEX IF NOT EXISTS engine_runs_provider ON engine_runs(provider, id DESC);
CREATE TRIGGER IF NOT EXISTS feed_items_ad AFTER DELETE ON feed_items BEGIN
              INSERT INTO feed_items_fts(feed_items_fts, rowid, title, summary, source_title, url, source_url)
              VALUES('delete', old.id, old.title, old.summary, old.source_title, old.url, old.source_url);
            END;
CREATE TRIGGER IF NOT EXISTS feed_items_ai AFTER INSERT ON feed_items BEGIN
              INSERT INTO feed_items_fts(rowid, title, summary, source_title, url, source_url)
              VALUES (new.id, new.title, new.summary, new.source_title, new.url, new.source_url);
            END;
CREATE TRIGGER IF NOT EXISTS feed_items_au AFTER UPDATE ON feed_items BEGIN
              INSERT INTO feed_items_fts(feed_items_fts, rowid, title, summary, source_title, url, source_url)
              VALUES('delete', old.id, old.title, old.summary, old.source_title, old.url, old.source_url);
              INSERT INTO feed_items_fts(rowid, title, summary, source_title, url, source_url)
              VALUES (new.id, new.title, new.summary, new.source_title, new.url, new.source_url);
            END;
CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
              INSERT INTO pages_fts(pages_fts, rowid, title, content, url)
              VALUES('delete', old.id, old.title, old.content, old.url);
            END;
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
              INSERT INTO pages_fts(rowid, title, content, url)
              VALUES (new.id, new.title, new.content, new.url);
            END;
CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
              INSERT INTO pages_fts(pages_fts, rowid, title, content, url)
              VALUES('delete', old.id, old.title, old.content, old.url);
              INSERT INTO pages_fts(rowid, title, content, url)
              VALUES (new.id, new.title, new.content, new.url);
            END;
CREATE TRIGGER IF NOT EXISTS project_items_ad AFTER DELETE ON project_items BEGIN
              INSERT INTO project_items_fts(project_items_fts, rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES('delete', old.id, old.repository, old.title, old.labels_text, old.priority, old.status, old.url, old.kind);
            END;
CREATE TRIGGER IF NOT EXISTS project_items_ai AFTER INSERT ON project_items BEGIN
              INSERT INTO project_items_fts(rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES (new.id, new.repository, new.title, new.labels_text, new.priority, new.status, new.url, new.kind);
            END;
CREATE TRIGGER IF NOT EXISTS project_items_au AFTER UPDATE ON project_items BEGIN
              INSERT INTO project_items_fts(project_items_fts, rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES('delete', old.id, old.repository, old.title, old.labels_text, old.priority, old.status, old.url, old.kind);
              INSERT INTO project_items_fts(rowid, repository, title, labels_text, priority, status, url, kind)
              VALUES (new.id, new.repository, new.title, new.labels_text, new.priority, new.status, new.url, new.kind);
            END;
CREATE TRIGGER IF NOT EXISTS repo_documents_ad AFTER DELETE ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(repo_documents_fts, rowid, repo_name, rel_path, title, context, content, kind)
              VALUES('delete', old.id, old.repo_name, old.rel_path, old.title, old.context, old.content, old.kind);
            END;
CREATE TRIGGER IF NOT EXISTS repo_documents_ai AFTER INSERT ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(rowid, repo_name, rel_path, title, context, content, kind)
              VALUES (new.id, new.repo_name, new.rel_path, new.title, new.context, new.content, new.kind);
            END;
CREATE TRIGGER IF NOT EXISTS repo_documents_au AFTER UPDATE ON repo_documents BEGIN
              INSERT INTO repo_documents_fts(repo_documents_fts, rowid, repo_name, rel_path, title, context, content, kind)
              VALUES('delete', old.id, old.repo_name, old.rel_path, old.title, old.context, old.content, old.kind);
              INSERT INTO repo_documents_fts(rowid, repo_name, rel_path, title, context, content, kind)
              VALUES (new.id, new.repo_name, new.rel_path, new.title, new.context, new.content, new.kind);
            END;

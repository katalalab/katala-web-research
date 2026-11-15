import tempfile
import unittest
from pathlib import Path

from katala_web_research.archive import Archive
from katala_web_research.models import PageSnapshot, RepoDocument, SearchResult


class ArchiveTests(unittest.TestCase):
    def test_store_and_query_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            try:
                run_id = archive.store_run(
                    "agent research",
                    "ddg",
                    [SearchResult(title="Agent Research", url="https://example.com", source="ddg", rank=1)],
                )
                archive.upsert_page(
                    PageSnapshot(
                        url="https://example.com",
                        title="Agent Research",
                        content="A durable web research archive for agents.",
                        source="direct",
                        fetched_at="2026-05-27T00:00:00+00:00",
                    )
                )
                hits = archive.query("durable", limit=5)
            finally:
                archive.close()

            self.assertEqual(run_id, 1)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].url, "https://example.com")

    def test_store_and_query_repo_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            try:
                archive.upsert_repo_document(
                    RepoDocument(
                        repo_path="/repos/sample",
                        repo_name="sample",
                        rel_path="README.md",
                        title="Sample",
                        content="This repository improves web research access.",
                        kind="readme",
                        indexed_at="2026-05-27T00:00:00+00:00",
                        context="repo:sample\npath:README.md\nkind:readme\ntitle:Sample\nheadings:Sample",
                        file_size=51,
                        file_mtime_ns=123,
                        content_sha256="abc",
                    )
                )
                hits = archive.query_repos("web research", limit=5)
                context_hits = archive.query_repos("repo sample", limit=5)
                metadata = archive.repo_document_metadata()
            finally:
                archive.close()

            self.assertEqual(len(hits), 1)
            self.assertEqual(len(context_hits), 1)
            self.assertEqual(hits[0].repo_name, "sample")
            self.assertEqual(metadata[("/repos/sample", "README.md")], (51, 123, "abc"))

    def test_batch_upsert_repo_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            documents = [
                RepoDocument(
                    repo_path="/repos/sample",
                    repo_name="sample",
                    rel_path=f"doc{i}.md",
                    title=f"Doc {i}",
                    content="Indexed content about web research pipelines.",
                    kind="doc",
                    indexed_at="2026-05-27T00:00:00+00:00",
                )
                for i in range(5)
            ]
            try:
                written = archive.upsert_repo_documents(documents, batch_size=2)
                hits = archive.query_repos("pipelines", limit=10)
            finally:
                archive.close()

            self.assertEqual(written, 5)
            self.assertEqual(len(hits), 5)

    def test_multi_term_query_keeps_partial_matches_but_ranks_full_match_first(self):
        # Natural-language queries use OR semantics to preserve recall; the
        # similarly sized full-match fixture must rank above this partial match.
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            try:
                archive.upsert_repo_documents(
                    [
                        RepoDocument(
                            repo_path="/repos/sample",
                            repo_name="sample",
                            rel_path="both.md",
                            title="Both",
                            content="kubernetes scheduling internals",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                        RepoDocument(
                            repo_path="/repos/sample",
                            repo_name="sample",
                            rel_path="one.md",
                            title="One",
                            content="kubernetes overview only",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                    ]
                )
                hits = archive.query_repos("kubernetes scheduling", limit=10)
            finally:
                archive.close()

            rel_paths = [hit.rel_path for hit in hits]
            self.assertEqual(set(rel_paths), {"both.md", "one.md"})
            self.assertEqual(rel_paths[0], "both.md")

    def test_repo_query_weights_title_above_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            try:
                archive.upsert_repo_documents(
                    [
                        RepoDocument(
                            repo_path="/repos/sample",
                            repo_name="sample",
                            rel_path="title.md",
                            title="Needle guide",
                            content="short overview",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                        RepoDocument(
                            repo_path="/repos/sample",
                            repo_name="sample",
                            rel_path="body.md",
                            title="Body only",
                            content="needle reference",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                    ]
                )
                hits = archive.query_repos("needle", limit=10)
            finally:
                archive.close()

        self.assertEqual([hit.rel_path for hit in hits], ["title.md", "body.md"])

    def test_repo_query_can_filter_by_repo_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            try:
                archive.upsert_repo_documents(
                    [
                        RepoDocument(
                            repo_path="/repos/alpha",
                            repo_name="alpha",
                            rel_path="docs/search.md",
                            title="Search",
                            content="retrieval filter",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                        RepoDocument(
                            repo_path="/repos/beta",
                            repo_name="beta",
                            rel_path="docs/search.md",
                            title="Search",
                            content="retrieval filter",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                        RepoDocument(
                            repo_path="/repos/alpha",
                            repo_name="alpha",
                            rel_path="notes/search.txt",
                            title="Search Notes",
                            content="retrieval filter",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                    ]
                )
                hits = archive.query_repos("retrieval filter", limit=10, repo="alpha", path="docs/")
            finally:
                archive.close()

        self.assertEqual([(hit.repo_name, hit.rel_path) for hit in hits], [("alpha", "docs/search.md")])

    def test_repo_query_accepts_inline_repo_and_path_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            try:
                archive.upsert_repo_documents(
                    [
                        RepoDocument(
                            repo_path="/repos/alpha",
                            repo_name="alpha",
                            rel_path="docs/search.md",
                            title="Search",
                            content="retrieval filter",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                        RepoDocument(
                            repo_path="/repos/beta",
                            repo_name="beta",
                            rel_path="docs/search.md",
                            title="Search",
                            content="retrieval filter",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                    ]
                )
                hits = archive.query_repos("repo:alpha path:docs/ retrieval filter", limit=10)
            finally:
                archive.close()

        self.assertEqual([(hit.repo_name, hit.rel_path) for hit in hits], [("alpha", "docs/search.md")])

    def test_repo_query_flag_filters_override_inline_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.sqlite"
            archive = Archive(archive_path)
            try:
                archive.upsert_repo_documents(
                    [
                        RepoDocument(
                            repo_path="/repos/alpha",
                            repo_name="alpha",
                            rel_path="docs/search.md",
                            title="Search",
                            content="retrieval filter",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                        RepoDocument(
                            repo_path="/repos/beta",
                            repo_name="beta",
                            rel_path="docs/search.md",
                            title="Search",
                            content="retrieval filter",
                            kind="doc",
                            indexed_at="2026-05-27T00:00:00+00:00",
                        ),
                    ]
                )
                hits = archive.query_repos("repo:alpha retrieval filter", limit=10, repo="beta")
            finally:
                archive.close()

        self.assertEqual([(hit.repo_name, hit.rel_path) for hit in hits], [("beta", "docs/search.md")])


if __name__ == "__main__":
    unittest.main()

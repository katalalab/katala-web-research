import json
import os
import unittest
from unittest.mock import patch

from katala_web_research.http import FetchError, HttpResponse
from katala_web_research.models import SearchResult
from katala_web_research.providers import (
    BraveSearch,
    GitHubCodeSearch,
    GitHubRepoSearch,
    MetaSearch,
    OpenAlexSearch,
    SearxngSearch,
    searxng_preflight,
)


class ProviderTests(unittest.TestCase):
    def test_searxng_provider_parses_results(self):
        response = HttpResponse(
            url="http://localhost/search",
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"results":[{"title":"A","url":"https://example.com/a","content":"Alpha"}]}',
        )
        with patch.dict(os.environ, {"KWR_SEARXNG_URL": "http://localhost:8080"}):
            with patch("katala_web_research.providers.fetch_url", return_value=response):
                results = SearxngSearch().search("alpha")

        self.assertEqual(results[0].url, "https://example.com/a")
        self.assertEqual(results[0].source, "searxng")

    def test_non_json_response_raises_fetch_error(self):
        # A WAF / rate-limit page returns HTML; the provider must surface it as
        # a FetchError naming the URL, not a bare JSONDecodeError.
        response = HttpResponse(
            url="http://localhost/search",
            status=200,
            headers={"content-type": "text/html"},
            body=b"<html><body>rate limited</body></html>",
        )
        with patch.dict(os.environ, {"KWR_SEARXNG_URL": "http://localhost:8080"}):
            with patch("katala_web_research.providers.fetch_url", return_value=response):
                with self.assertRaises(FetchError):
                    SearxngSearch().search("alpha")

    def test_searxng_provider_passes_optional_parameters(self):
        response = HttpResponse(
            url="http://localhost/search",
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"results":[]}',
        )
        env = {
            "KWR_SEARXNG_URL": "http://localhost:8080",
            "KWR_SEARXNG_CATEGORIES": "general,it",
            "KWR_SEARXNG_ENGINES": "duckduckgo,wikipedia",
            "KWR_SEARXNG_LANGUAGE": "ja",
            "KWR_SEARXNG_TIME_RANGE": "month",
            "KWR_SEARXNG_SAFESEARCH": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response) as fetch:
                SearxngSearch().search("alpha")

        called_url = fetch.call_args.args[0]
        self.assertIn("categories=general%2Cit", called_url)
        self.assertIn("engines=duckduckgo%2Cwikipedia", called_url)
        self.assertIn("language=ja", called_url)
        self.assertIn("time_range=month", called_url)
        self.assertIn("safesearch=1", called_url)

    def test_searxng_provider_fetches_multiple_pages_for_large_limits(self):
        first_page = {
            "results": [
                {"title": f"Result {idx}", "url": f"https://example{idx}.com/{idx}", "content": "Alpha"}
                for idx in range(20)
            ]
        }
        second_page = {
            "results": [
                {"title": "Result 20", "url": "https://example20.com/20", "content": "Alpha"}
            ]
        }
        responses = [
            HttpResponse(
                url="http://localhost/search",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(first_page).encode(),
            ),
            HttpResponse(
                url="http://localhost/search",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(second_page).encode(),
            ),
        ]
        with patch.dict(os.environ, {"KWR_SEARXNG_URL": "http://localhost:8080"}, clear=False):
            with patch("katala_web_research.providers.fetch_url", side_effect=responses) as fetch:
                results = SearxngSearch().search("alpha", limit=21)

        self.assertGreater(len(results), 0)
        self.assertEqual(fetch.call_count, 2)
        first_url = fetch.call_args_list[0].args[0]
        second_url = fetch.call_args_list[1].args[0]
        self.assertNotIn("pageno=", first_url)
        self.assertIn("pageno=2", second_url)

    def test_searxng_provider_rejects_invalid_time_range(self):
        env = {
            "KWR_SEARXNG_URL": "http://localhost:8080",
            "KWR_SEARXNG_TIME_RANGE": "forever",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url") as fetch:
                with self.assertRaises(FetchError):
                    SearxngSearch().search("alpha")

        fetch.assert_not_called()

    def test_searxng_provider_rejects_invalid_safesearch(self):
        env = {
            "KWR_SEARXNG_URL": "http://localhost:8080",
            "KWR_SEARXNG_SAFESEARCH": "9",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url") as fetch:
                with self.assertRaises(FetchError):
                    SearxngSearch().search("alpha")

        fetch.assert_not_called()

    def test_searxng_preflight_checks_json_results(self):
        response = HttpResponse(
            url="http://localhost:8080/search?q=katala&format=json",
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"results":[{"title":"A","url":"https://example.com/a"}]}',
        )
        with patch.dict(os.environ, {"KWR_SEARXNG_URL": "http://localhost:8080"}, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response):
                probe = searxng_preflight()

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["result_count"], 1)
        self.assertEqual(probe["status_code"], 200)

    def test_searxng_preflight_rejects_missing_results_list(self):
        response = HttpResponse(
            url="http://localhost:8080/search?q=katala&format=json",
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"answers":[]}',
        )
        with patch.dict(os.environ, {"KWR_SEARXNG_URL": "http://localhost:8080"}, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response):
                with self.assertRaises(FetchError):
                    searxng_preflight()

    def test_brave_provider_parses_results(self):
        response = HttpResponse(
            url="https://api.search.brave.com/res/v1/web/search",
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"web":{"results":[{"title":"B","url":"https://example.com/b","description":"Beta"}]}}',
        )
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test"}, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response):
                results = BraveSearch().search("beta")

        self.assertEqual(results[0].url, "https://example.com/b")
        self.assertEqual(results[0].source, "brave")

    def test_brave_provider_passes_optional_api_parameters(self):
        response = HttpResponse(
            url="https://api.search.brave.com/res/v1/web/search",
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"web":{"results":[]}}',
        )
        env = {
            "BRAVE_SEARCH_API_KEY": "test",
            "BRAVE_SEARCH_COUNTRY": "US",
            "BRAVE_SEARCH_LANG": "en",
            "BRAVE_UI_LANG": "en-US",
            "BRAVE_FRESHNESS": "week",
            "BRAVE_SAFESEARCH": "moderate",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response) as fetch:
                BraveSearch().search("beta", limit=25)

        called_url = fetch.call_args.args[0]
        self.assertIn("count=20", called_url)
        self.assertIn("country=US", called_url)
        self.assertIn("search_lang=en", called_url)
        self.assertIn("ui_lang=en-US", called_url)
        self.assertIn("freshness=pw", called_url)
        self.assertIn("safesearch=moderate", called_url)

    def test_brave_provider_fetches_multiple_pages_for_large_limits(self):
        first_page = {
            "web": {
                "results": [
                    {"title": f"Result {idx}", "url": f"https://example{idx}.com/{idx}", "description": "Beta"}
                    for idx in range(20)
                ]
            }
        }
        second_page = {
            "web": {
                "results": [
                    {"title": "Result 20", "url": "https://example20.com/20", "description": "Beta"}
                ]
            }
        }
        responses = [
            HttpResponse(
                url="https://api.search.brave.com/res/v1/web/search",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(first_page).encode(),
            ),
            HttpResponse(
                url="https://api.search.brave.com/res/v1/web/search",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(second_page).encode(),
            ),
        ]
        with patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test"}, clear=False):
            with patch("katala_web_research.providers.fetch_url", side_effect=responses) as fetch:
                results = BraveSearch().search("beta", limit=21)

        self.assertGreater(len(results), 0)
        self.assertEqual(fetch.call_count, 2)
        first_url = fetch.call_args_list[0].args[0]
        second_url = fetch.call_args_list[1].args[0]
        self.assertNotIn("offset=", first_url)
        self.assertIn("offset=1", second_url)

    def test_brave_provider_rejects_invalid_filters_before_fetch(self):
        env = {
            "BRAVE_SEARCH_API_KEY": "test",
            "BRAVE_FRESHNESS": "forever",
            "BRAVE_SAFESEARCH": "strict",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url") as fetch:
                with self.assertRaises(FetchError):
                    BraveSearch().search("beta")

        fetch.assert_not_called()

    def test_github_rest_provider_keeps_repo_metadata(self):
        body = json.dumps(
            {
                "items": [
                    {
                        "full_name": "katala/search",
                        "name": "search",
                        "html_url": "https://github.com/katala/search",
                        "description": "Search toolkit",
                        "stargazers_count": 123,
                        "updated_at": "2026-06-15T00:00:00Z",
                        "fork": False,
                        "language": "Python",
                        "topics": ["search", "retrieval"],
                        "license": {"name": "MIT License", "spdx_id": "MIT"},
                        "homepage": "https://example.com",
                        "clone_url": "https://github.com/katala/search.git",
                        "owner": {"login": "katala"},
                    }
                ]
            }
        ).encode()
        response = HttpResponse(
            url="https://api.github.com/search/repositories",
            status=200,
            headers={"content-type": "application/json"},
            body=body,
        )
        with patch("katala_web_research.providers.shutil.which", return_value=None):
            with patch("katala_web_research.providers.fetch_url", return_value=response) as fetch:
                results = GitHubRepoSearch().search("katala search", limit=5)

        headers = fetch.call_args.kwargs["headers"]
        metadata = results[0].metadata
        self.assertEqual(headers["X-GitHub-Api-Version"], "2022-11-28")
        self.assertIn("language=Python", results[0].snippet)
        self.assertEqual(metadata["language"], "Python")
        self.assertEqual(metadata["topics"], ["search", "retrieval"])
        self.assertEqual(metadata["license_url"], "https://spdx.org/licenses/MIT.html")
        self.assertEqual(metadata["source_code_url"], "https://github.com/katala/search.git")

    def test_github_code_provider_requires_token(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}, clear=False):
            with patch("katala_web_research.providers.fetch_url") as fetch:
                with self.assertRaises(FetchError):
                    GitHubCodeSearch().search("SearchResult")

        fetch.assert_not_called()

    def test_github_code_provider_keeps_code_metadata(self):
        body = json.dumps(
            {
                "items": [
                    {
                        "name": "providers.py",
                        "path": "src/katala_web_research/providers.py",
                        "html_url": "https://github.com/katala/search/blob/main/src/providers.py",
                        "repository": {
                            "full_name": "katala/search",
                            "html_url": "https://github.com/katala/search",
                            "description": "Search toolkit",
                            "language": "Python",
                        },
                        "text_matches": [
                            {
                                "object_type": "FileContent",
                                "property": "content",
                                "fragment": "class SearchResult:\n    source: str",
                                "matches": [{"text": "SearchResult", "indices": [6, 18]}],
                            }
                        ],
                    }
                ]
            }
        ).encode()
        response = HttpResponse(
            url="https://api.github.com/search/code",
            status=200,
            headers={"content-type": "application/json"},
            body=body,
        )
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response) as fetch:
                results = GitHubCodeSearch().search("SearchResult repo:katala/search", limit=5)

        called_url = fetch.call_args.args[0]
        headers = fetch.call_args.kwargs["headers"]
        metadata = results[0].metadata
        self.assertIn("https://api.github.com/search/code?", called_url)
        self.assertIn("sort=indexed", called_url)
        self.assertIn("page=1", called_url)
        self.assertEqual(headers["Accept"], "application/vnd.github.text-match+json")
        self.assertEqual(headers["Authorization"], "Bearer test-token")
        self.assertEqual(headers["X-GitHub-Api-Version"], "2022-11-28")
        self.assertEqual(results[0].source, "github_code")
        self.assertIn("katala/search", results[0].title)
        self.assertIn("class SearchResult:", metadata["fragment"])
        self.assertEqual(metadata["repository"], "katala/search")
        self.assertEqual(metadata["path"], "src/katala_web_research/providers.py")

    def test_github_code_provider_fetches_multiple_pages_for_large_limits(self):
        def item(idx: int) -> dict:
            return {
                "name": f"file{idx}.py",
                "path": f"src/file{idx}.py",
                "html_url": f"https://github.com/katala/search/blob/main/src/file{idx}.py",
                "repository": {"full_name": "katala/search", "html_url": "https://github.com/katala/search"},
                "text_matches": [
                    {
                        "object_type": "FileContent",
                        "property": "content",
                        "fragment": f"needle {idx}",
                        "matches": [{"text": "needle", "indices": [0, 6]}],
                    }
                ],
            }

        responses = [
            HttpResponse(
                url="https://api.github.com/search/code",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"items": [item(idx) for idx in range(100)]}).encode(),
            ),
            HttpResponse(
                url="https://api.github.com/search/code",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"items": [item(100)]}).encode(),
            ),
        ]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=False):
            with patch("katala_web_research.providers.fetch_url", side_effect=responses) as fetch:
                results = GitHubCodeSearch().search("needle repo:katala/search", limit=101)

        self.assertGreater(len(results), 0)
        self.assertEqual(fetch.call_count, 2)
        first_url = fetch.call_args_list[0].args[0]
        second_url = fetch.call_args_list[1].args[0]
        self.assertIn("page=1", first_url)
        self.assertIn("page=2", second_url)

    def test_github_code_provider_returns_empty_for_invalid_query(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"}, clear=False):
            with patch(
                "katala_web_research.providers.fetch_url",
                side_effect=FetchError("HTTP 422 for https://api.github.com/search/code: b'invalid'"),
            ):
                results = GitHubCodeSearch().search("user: foo", limit=5)

        self.assertEqual(results, [])

    def test_openalex_provider_parses_work_results(self):
        body = json.dumps(
            {
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "doi": "https://doi.org/10.123/example",
                        "display_name": "Query Decomposition for RAG",
                        "publication_year": 2025,
                        "publication_date": "2025-07-01",
                        "type": "article",
                        "cited_by_count": 42,
                        "open_access": {"is_oa": True, "oa_status": "gold"},
                        "content_urls": {
                            "pdf": "https://content.openalex.org/works/W1.pdf",
                            "grobid_xml": "https://content.openalex.org/works/W1.grobid-xml",
                        },
                        "primary_location": {
                            "landing_page_url": "https://aclanthology.org/2025.acl-srw.32/",
                            "pdf_url": "https://aclanthology.org/2025.acl-srw.32.pdf",
                            "is_oa": True,
                            "license": "cc-by",
                            "version": "publishedVersion",
                            "source": {
                                "id": "https://openalex.org/S123",
                                "display_name": "ACL Anthology",
                                "type": "repository",
                            },
                        },
                        "best_oa_location": {
                            "landing_page_url": "https://example.org/oa",
                            "pdf_url": "https://example.org/oa.pdf",
                            "is_oa": True,
                            "license": "cc-by",
                            "version": "acceptedVersion",
                            "source": {"display_name": "Example Repository"},
                        },
                        "abstract_inverted_index": {"query": [0], "decomposition": [1], "retrieval": [2]},
                    }
                ]
            }
        ).encode()
        response = HttpResponse(
            url="https://api.openalex.org/works",
            status=200,
            headers={"content-type": "application/json"},
            body=body,
        )
        with patch.dict(os.environ, {"OPENALEX_API_KEY": "", "OPENALEX_MAILTO": ""}, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response) as fetch:
                results = OpenAlexSearch().search("query decomposition retrieval")

        called_url = fetch.call_args.args[0]
        self.assertNotIn("api_key=", called_url)
        self.assertNotIn("mailto=", called_url)
        self.assertIn("cursor=%2A", called_url)
        self.assertEqual(results[0].url, "https://aclanthology.org/2025.acl-srw.32/")
        self.assertIn("citations=42", results[0].snippet)
        self.assertEqual(results[0].source, "openalex")
        metadata = results[0].metadata
        self.assertEqual(metadata["openalex_id"], "https://openalex.org/W1")
        self.assertEqual(metadata["primary_pdf_url"], "https://aclanthology.org/2025.acl-srw.32.pdf")
        self.assertEqual(metadata["primary_source_display_name"], "ACL Anthology")
        self.assertEqual(metadata["best_oa_pdf_url"], "https://example.org/oa.pdf")
        self.assertEqual(metadata["content_url"], "https://content.openalex.org/works/W1.pdf")
        self.assertEqual(metadata["open_access_oa_status"], "gold")

    def test_openalex_provider_adds_optional_key_and_mailto(self):
        response = HttpResponse(
            url="https://api.openalex.org/works",
            status=200,
            headers={"content-type": "application/json"},
            body=b'{"results":[]}',
        )
        env = {
            "OPENALEX_API_KEY": "test-key",
            "OPENALEX_MAILTO": "research@example.com",
            "OPENALEX_LANGUAGE": "en-US",
            "OPENALEX_YEAR": "2025",
            "OPENALEX_FROM_DATE": "2025-01-01",
            "OPENALEX_TO_DATE": "2025-12-31",
            "OPENALEX_HAS_PDF": "true",
            "OPENALEX_HAS_ABSTRACT": "yes",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url", return_value=response) as fetch:
                OpenAlexSearch().search("query decomposition retrieval")

        called_url = fetch.call_args.args[0]
        self.assertIn("api_key=test-key", called_url)
        self.assertIn("mailto=research%40example.com", called_url)
        self.assertIn(
            "filter=language%3Aen%2Cpublication_year%3A2025%2Cfrom_publication_date%3A2025-01-01%2Cto_publication_date%3A2025-12-31%2Chas_content.pdf%3Atrue%2Chas_abstract%3Atrue",
            called_url,
        )

    def test_openalex_provider_rejects_invalid_date_filter_before_fetch(self):
        env = {
            "OPENALEX_FROM_DATE": "2025",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url") as fetch:
                with self.assertRaises(FetchError):
                    OpenAlexSearch().search("query decomposition retrieval")

        fetch.assert_not_called()

    def test_openalex_provider_rejects_invalid_boolean_filter_before_fetch(self):
        env = {
            "OPENALEX_HAS_PDF": "maybe",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.fetch_url") as fetch:
                with self.assertRaises(FetchError):
                    OpenAlexSearch().search("query decomposition retrieval")

        fetch.assert_not_called()

    def test_openalex_provider_fetches_multiple_cursor_pages_for_large_limits(self):
        def item(idx: int) -> dict:
            return {
                "id": f"https://openalex.org/W{idx}",
                "display_name": f"Paper {idx}",
                "publication_year": 2025,
                "primary_location": {"landing_page_url": f"https://example.org/paper{idx}"},
            }

        responses = [
            HttpResponse(
                url="https://api.openalex.org/works",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "meta": {"next_cursor": "next-page"},
                        "results": [item(idx) for idx in range(100)],
                    }
                ).encode(),
            ),
            HttpResponse(
                url="https://api.openalex.org/works",
                status=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "meta": {"next_cursor": None},
                        "results": [item(100)],
                    }
                ).encode(),
            ),
        ]
        with patch.dict(os.environ, {"OPENALEX_API_KEY": "", "OPENALEX_MAILTO": ""}, clear=False):
            with patch("katala_web_research.providers.fetch_url", side_effect=responses) as fetch:
                results = OpenAlexSearch().search("query decomposition retrieval", limit=101)

        self.assertGreater(len(results), 0)
        self.assertEqual(fetch.call_count, 2)
        first_url = fetch.call_args_list[0].args[0]
        second_url = fetch.call_args_list[1].args[0]
        self.assertIn("cursor=%2A", first_url)
        self.assertIn("cursor=next-page", second_url)

    def test_meta_provider_merges_and_dedupes_engines(self):
        class FakeProvider:
            def __init__(self, name, url):
                self.name = name
                self.url = url

            def search(self, query, *, limit=10):
                return [SearchResult(title=f"{self.name} result", url=self.url, source=self.name, rank=1)]

        fake_providers = {
            "a": FakeProvider("a", "https://docs.github.com/example"),
            "b": FakeProvider("b", "https://docs.github.com/example/"),
            "c": FakeProvider("c", "https://arxiv.org/abs/2510.18633"),
            "meta": MetaSearch(),
        }
        with patch.dict(os.environ, {"KWR_META_PROVIDERS": "a,b,c"}, clear=False):
            with patch("katala_web_research.providers.PROVIDERS", fake_providers):
                results = MetaSearch().search("query decomposition", limit=5)

        self.assertEqual(len(results), 2)
        self.assertIn("https://arxiv.org/abs/2510.18633", {result.url for result in results})

    def test_meta_provider_records_engine_health(self):
        class OkProvider:
            name = "ok"

            def search(self, query, *, limit=10):
                return [SearchResult(title="Ok result", url="https://example.com/ok", source=self.name, rank=1)]

        class EmptyProvider:
            name = "empty"

            def search(self, query, *, limit=10):
                return []

        class FailingProvider:
            name = "boom"

            def search(self, query, *, limit=10):
                raise RuntimeError("provider failed")

        fake_providers = {
            "ok": OkProvider(),
            "empty": EmptyProvider(),
            "boom": FailingProvider(),
            "meta": MetaSearch(),
        }
        with patch.dict(os.environ, {"KWR_META_PROVIDERS": "ok,empty,boom"}, clear=False):
            with patch("katala_web_research.providers.PROVIDERS", fake_providers):
                results = MetaSearch().search("alpha", limit=5)

        self.assertEqual(len(results), 1)
        metadata = results[0].metadata
        runs = {row["provider"]: row for row in metadata["meta_engine_runs"]}
        self.assertEqual(runs["ok"]["status"], "ok")
        self.assertGreater(runs["ok"]["health_score"], 0)
        self.assertEqual(runs["empty"]["status"], "empty")
        self.assertEqual(runs["boom"]["status"], "error")
        self.assertEqual(runs["boom"]["error_kind"], "RuntimeError")
        self.assertEqual(metadata["engine_health"], {"ok": runs["ok"]["health_score"]})

    def test_meta_profile_rewrites_queries(self):
        seen_queries = {}

        class FakeProvider:
            def __init__(self, name):
                self.name = name

            def search(self, query, *, limit=10):
                seen_queries[self.name] = query
                return [SearchResult(title=f"{self.name} result", url=f"https://example.com/{self.name}", source=self.name, rank=1)]

        fake_providers = {
            "github": FakeProvider("github"),
            "searxng": FakeProvider("searxng"),
            "ddg": FakeProvider("ddg"),
            "meta": MetaSearch(),
        }
        with patch.dict(os.environ, {"KWR_META_PROFILE": "code", "KWR_META_PROVIDERS": ""}, clear=False):
            with patch("katala_web_research.providers.PROVIDERS", fake_providers):
                MetaSearch().search("browser agent", limit=3)

        self.assertEqual(seen_queries["github"], "browser agent implementation library")
        self.assertEqual(seen_queries["ddg"], "browser agent")


if __name__ == "__main__":
    unittest.main()

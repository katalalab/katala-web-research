import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from katala_web_research import cli
from katala_web_research.archive import Archive
from katala_web_research.http import FetchError
from katala_web_research.models import PageSnapshot
from katala_web_research.providers import OPENALEX_EXPAND_MAX, openalex_expand

SEED = {
    "id": "https://openalex.org/W1",
    "display_name": "Seed work",
    "referenced_works": [f"https://openalex.org/W{n}" for n in range(100, 180)],
}


def work(work_id, name):
    return {
        "id": f"https://openalex.org/{work_id}",
        "display_name": name,
        "doi": f"https://doi.org/10.1/{work_id}",
        "publication_year": 2025,
        "publication_date": "2025-03-01",
        "cited_by_count": 3,
        "is_retracted": False,
        "open_access": {"oa_status": "gold"},
    }


class Response:
    def __init__(self, payload):
        self.text = json.dumps(payload)


class FakeApi:
    def __init__(self, seed=SEED):
        self.seed = seed
        self.urls = []

    def __call__(self, url, **_kwargs):
        self.urls.append(url)
        if "/works/" in url:
            return Response(self.seed)
        if "cites%3A" in url or "cites:" in url:
            return Response({"results": [work("W900", "Citing work")]})
        return Response({"results": [work(f"W{100 + n}", f"Referenced {n}") for n in range(80)]})


class ExpandTests(unittest.TestCase):
    def expand(self, api, **kwargs):
        with patch("katala_web_research.providers.fetch_url", api):
            return openalex_expand("https://openalex.org/W1", **kwargs)

    def test_both_directions_are_followed_by_default(self):
        api = FakeApi()

        expanded = self.expand(api)

        self.assertEqual(sorted(expanded), ["citing", "referenced"])
        self.assertEqual(expanded["citing"][0].title, "Citing work")
        self.assertEqual(expanded["referenced"][0].source, "openalex")
        self.assertEqual([result.rank for result in expanded["referenced"]], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    def test_one_direction_does_not_call_the_other(self):
        api = FakeApi()

        expanded = self.expand(api, direction="referenced")

        self.assertEqual(list(expanded), ["referenced"])
        self.assertFalse(any("cites" in url for url in api.urls))

    def test_result_count_is_bounded_even_when_the_graph_is_not(self):
        api = FakeApi()

        expanded = self.expand(api, direction="referenced", limit=1_000)

        self.assertEqual(len(expanded["referenced"]), OPENALEX_EXPAND_MAX)
        self.assertEqual(self.expand(FakeApi(), limit=0), {})

    def test_the_seed_can_be_a_doi_an_openalex_url_or_a_bare_id(self):
        for seed, expected in (
            ("10.1/W1", "10.1%2FW1"),
            ("https://openalex.org/W1", "W1"),
            ("W1", "W1"),
        ):
            api = FakeApi()
            with patch("katala_web_research.providers.fetch_url", api):
                openalex_expand(seed, direction="referenced", limit=1)
            self.assertIn(expected, api.urls[0], seed)

    def test_a_work_that_does_not_resolve_fails_closed(self):
        with patch("katala_web_research.providers.fetch_url", lambda *a, **k: Response({})):
            with self.assertRaises(FetchError):
                openalex_expand("W404", direction="referenced")

    def test_unknown_direction_is_rejected_before_any_request(self):
        api = FakeApi()
        with patch("katala_web_research.providers.fetch_url", api):
            with self.assertRaises(ValueError):
                openalex_expand("W1", direction="sideways")
        self.assertEqual(api.urls, [])

    def test_the_api_key_never_reaches_an_error_message(self):
        secret = "openalex-expansion-secret"

        def not_json(url, **_kwargs):
            class Broken:
                text = "<html>rate limited</html>"

            return Broken()

        with patch.dict(os.environ, {"OPENALEX_API_KEY": secret}, clear=False):
            with patch("katala_web_research.providers.fetch_url", not_json):
                with self.assertRaises(FetchError) as caught:
                    openalex_expand("W1", direction="referenced")

        self.assertNotIn(secret, str(caught.exception))


class CachedReadTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.archive_path = str(Path(self._tmp.name) / "archive.sqlite")
        self.url = "https://example.com/doc"

    def read(self, **flags):
        argv = ["read", self.url, "--archive", self.archive_path]
        for name, value in flags.items():
            if value:
                argv.append("--" + name.replace("_", "-"))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return cli.main(argv)

    def fresh_page(self, content):
        return PageSnapshot(
            url=self.url,
            title="Doc",
            content=content,
            source="direct",
            fetched_at="2026-08-20T00:00:00+00:00",
        )

    def test_a_cache_miss_fetches_once_and_stores_the_page(self):
        calls = []

        def reader(url, *, reader="auto"):
            calls.append(url)
            return self.fresh_page("first")

        with patch("katala_web_research.cli.read_url", reader):
            self.assertEqual(self.read(cache=True), 0)
            self.assertEqual(self.read(cache=True), 0)

        self.assertEqual(calls, [self.url])
        archive = Archive(self.archive_path)
        self.addCleanup(archive.close)
        self.assertEqual(archive.page_by_url(self.url).content, "first")

    def test_refresh_refetches_and_overwrites_the_stored_page(self):
        contents = iter(["first", "second"])

        def reader(url, *, reader="auto"):
            return self.fresh_page(next(contents))

        with patch("katala_web_research.cli.read_url", reader):
            self.read(cache=True)
            self.read(cache=True, refresh=True)

        archive = Archive(self.archive_path)
        self.addCleanup(archive.close)
        self.assertEqual(archive.page_by_url(self.url).content, "second")

    def test_output_survives_a_console_that_cannot_encode_the_text(self):
        buffer = io.BytesIO()
        console = io.TextIOWrapper(buffer, encoding="cp932", errors="strict")
        page = self.fresh_page("© 2026 Example")

        with patch("katala_web_research.cli.read_url", lambda *a, **k: page):
            with patch.object(sys, "stdout", console):
                code = cli.main(["read", self.url])
        console.flush()

        self.assertEqual(code, 0)
        self.assertIn("©".encode(), buffer.getvalue())

    def test_without_cache_nothing_is_read_from_or_written_to_the_archive(self):
        calls = []

        def reader(url, *, reader="auto"):
            calls.append(url)
            return self.fresh_page("first")

        with patch("katala_web_research.cli.read_url", reader):
            self.read()
            self.read()

        self.assertEqual(calls, [self.url, self.url])
        self.assertFalse(Path(self.archive_path).exists())


if __name__ == "__main__":
    unittest.main()

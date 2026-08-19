import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from katala_web_research.http import FetchError, fetch_url, redact_url
from katala_web_research.providers import OpenAlexSearch, provider_status

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_SOURCE = (ROOT / "src" / "katala_web_research" / "providers.py").read_text(encoding="utf-8")
ENV_NAME = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
SECRET = "super-secret-openalex-key"


def env_names_read_by_providers() -> set[str]:
    return set(re.findall(r'(?:os\.environ\.get|_secret_env)\(\s*"([A-Z0-9_]+)"', PROVIDERS_SOURCE))


class UrlRedactionTests(unittest.TestCase):
    def test_credential_query_parameters_are_replaced(self):
        redacted = redact_url("https://api.openalex.org/works?search=rag&api_key=abc123&mailto=a@b.c")

        self.assertNotIn("abc123", redacted)
        self.assertIn("api_key=REDACTED", redacted)
        self.assertIn("search=rag", redacted)
        self.assertIn("mailto=a%40b.c", redacted)

    def test_basic_auth_userinfo_is_replaced(self):
        redacted = redact_url("https://user:hunter2@searx.example.com/search?q=rag")

        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("user:", redacted)
        self.assertIn("searx.example.com", redacted)

    def test_urls_without_credentials_survive_intact(self):
        url = "https://api.openalex.org/works?search=rag&per_page=10"
        self.assertEqual(redact_url(url), url)


class FetchErrorLeakTests(unittest.TestCase):
    def test_http_error_message_does_not_carry_the_query_string_credential(self):
        def raise_http(*_args, **_kwargs):
            raise HTTPError("https://x/?api_key=" + SECRET, 403, "Forbidden", {}, None)

        with patch("katala_web_research.http.urlopen", raise_http):
            with self.assertRaises(FetchError) as caught:
                fetch_url("https://api.openalex.org/works?search=rag&api_key=" + SECRET)

        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIn("api_key=REDACTED", str(caught.exception))

    def test_network_error_message_does_not_carry_the_credential(self):
        def raise_url(*_args, **_kwargs):
            raise URLError("no route to host")

        with patch("katala_web_research.http.urlopen", raise_url):
            with self.assertRaises(FetchError) as caught:
                fetch_url("https://api.openalex.org/works?api_key=" + SECRET)

        self.assertNotIn(SECRET, str(caught.exception))

    def test_openalex_non_json_response_does_not_echo_the_api_key(self):
        class Response:
            text = "<html>rate limited</html>"

        with patch.dict(os.environ, {"OPENALEX_API_KEY": SECRET}, clear=False):
            with patch("katala_web_research.providers.fetch_url", lambda *a, **k: Response()):
                with self.assertRaises(FetchError) as caught:
                    OpenAlexSearch().search("rag", limit=3)

        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIn("api_key=REDACTED", str(caught.exception))


class AdvertisedEnvTests(unittest.TestCase):
    def test_provider_status_only_names_environment_variables_the_code_reads(self):
        read = env_names_read_by_providers()
        advertised = {
            name
            for row in provider_status()
            for name in ENV_NAME.findall(row["detail"])
            if name.endswith(("_KEY", "_TOKEN", "_URL")) or name.startswith("KWR_")
        }

        self.assertTrue(advertised)
        self.assertEqual(advertised - read, set())

    def test_pyproject_only_advertises_environment_variables_the_code_reads(self):
        read = env_names_read_by_providers()
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        block = pyproject.split("[project.optional-dependencies]")[0].split(
            "# Optional provider integrations"
        )[-1]
        advertised = {
            name
            for name in ENV_NAME.findall(block)
            if name.endswith(("_KEY", "_TOKEN", "_URL")) or name.startswith("KWR_")
        }

        self.assertTrue(advertised)
        self.assertEqual(advertised - read, set())


class DependencyBoundaryTests(unittest.TestCase):
    def test_no_runtime_dependencies_and_no_vendored_searxng_source(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("dependencies = []", pyproject)
        # SearXNG is AGPL. It is reachable over HTTP through KWR_SEARXNG_URL and must never
        # be vendored into this MIT tree, which is what an import would amount to.
        for path in (ROOT / "src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("import searx", source, path.name)
            self.assertNotIn("from searx", source, path.name)


if __name__ == "__main__":
    unittest.main()

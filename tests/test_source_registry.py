import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from katala_web_research.cli import main
from katala_web_research.source_quality import classify_url
from katala_web_research.source_registry import default_source_registry, source_registry


class SourceRegistryTests(unittest.TestCase):
    def test_default_registry_covers_core_domains(self):
        registry = default_source_registry()

        domains = {source.domain for source in registry.sources}

        self.assertIn("news", domains)
        self.assertIn("medicine", domains)
        self.assertIn("security", domains)
        self.assertIn("law_jp", domains)
        self.assertTrue(any(source.bias_caveat for source in registry.sources if source.domain == "news"))

    def test_recommends_sources_by_domain_and_query_type(self):
        registry = default_source_registry()

        recommendations = registry.recommend(domain="security", query_type="exploited_vulnerability")
        names = [source.name for source in recommendations]

        self.assertIn("CISA Known Exploited Vulnerabilities Catalog", names)
        self.assertLessEqual(len(recommendations), 5)

    def test_matches_registry_source_from_url(self):
        registry = default_source_registry()

        source = registry.match_url("https://www.cisa.gov/known-exploited-vulnerabilities-catalog")

        self.assertIsNotNone(source)
        self.assertEqual(source.name, "CISA Known Exploited Vulnerabilities Catalog")

    def test_path_specific_registry_source_does_not_match_entire_host(self):
        registry = default_source_registry()

        source = registry.match_url("https://www.cisa.gov/news-events")
        label, score = classify_url("https://www.cisa.gov/news-events")

        self.assertIsNone(source)
        self.assertEqual(label, "institutional")
        self.assertLess(score, 96)

    def test_source_quality_uses_registry_scores(self):
        label, score = classify_url("https://www.cisa.gov/known-exploited-vulnerabilities-catalog")

        self.assertEqual(label, "exploited_vulnerability")
        self.assertGreaterEqual(score, 95)

    def test_cli_lists_sources_as_json(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            return_code = main(["sources", "list", "--domain", "security", "--json"])

        self.assertEqual(return_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["count"], 2)
        self.assertIn("CISA Known Exploited Vulnerabilities Catalog", [row["name"] for row in payload["sources"]])

    def test_cli_matches_source_url_as_json(self):
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            return_code = main(
                [
                    "sources",
                    "match",
                    "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
                    "--json",
                ]
            )

        self.assertEqual(return_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["matched"])
        self.assertEqual(payload["source"]["source_type"], "exploited_vulnerability")
        self.assertIn("bias_caveat", payload["source"])

    def test_overlay_sources_extend_default_registry(self):
        overlay = {
            "sources": [
                {
                    "name": "Example Regulator",
                    "domain": "regulatory_test",
                    "source_type": "primary_regulator",
                    "query_types": ["regulatory_primary"],
                    "url": "https://regulator.example/",
                    "hosts": ["regulator.example"],
                    "url_prefixes": ["https://regulator.example/"],
                    "best_for": "Testing operator overlay routing.",
                    "freshness": "official",
                    "trust_score": 99,
                    "bias_caveat": "Fixture only.",
                    "update_cadence": "official",
                    "avoid_for": ["real evidence"],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            # Windows denies a second open on a live NamedTemporaryFile handle,
            # so the overlay is closed before source_registry() reads it.
            overlay_path = Path(tmp) / "overlay.json"
            overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
            previous = os.environ.get("KWR_SOURCE_REGISTRY_OVERLAY")
            os.environ["KWR_SOURCE_REGISTRY_OVERLAY"] = str(overlay_path)
            try:
                source_registry.cache_clear()
                registry = source_registry()
            finally:
                source_registry.cache_clear()
                if previous is None:
                    os.environ.pop("KWR_SOURCE_REGISTRY_OVERLAY", None)
                else:
                    os.environ["KWR_SOURCE_REGISTRY_OVERLAY"] = previous

        match = registry.match_url("https://regulator.example/guidance")

        self.assertIsNotNone(match)
        self.assertEqual(match.name, "Example Regulator")


if __name__ == "__main__":
    unittest.main()

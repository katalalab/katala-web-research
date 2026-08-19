import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from katala_web_research.archive import Archive
from katala_web_research.engine_health import (
    percentile_ms,
    summarize_engine_runs,
    weak_engines,
)
from katala_web_research.models import SearchResult
from katala_web_research.providers import MetaSearch, engine_health


def run(provider, status="ok", latency_ms=100, result_count=5, error_kind=""):
    return {
        "provider": provider,
        "status": status,
        "latency_ms": latency_ms,
        "result_count": result_count,
        "error_kind": error_kind,
    }


class HealthSummaryTests(unittest.TestCase):
    def test_failures_latency_and_useful_rate_are_measured_per_engine(self):
        rows = [
            run("fast"),
            run("fast", latency_ms=200),
            run("slow", latency_ms=6_000),
            run("slow", latency_ms=7_000),
            run("broken", status="error", latency_ms=50, result_count=0, error_kind="FetchError"),
            run("broken", status="empty", latency_ms=50, result_count=0),
        ]

        stats = {stat.provider: stat for stat in summarize_engine_runs(rows)}

        self.assertEqual(stats["fast"].failures, 0)
        self.assertEqual(stats["fast"].useful_rate, 1.0)
        self.assertEqual(stats["fast"].p95_latency_ms, 200)
        self.assertEqual(stats["broken"].failures, 1)
        self.assertEqual(stats["broken"].failure_rate, 0.5)
        self.assertEqual(stats["broken"].useful_rate, 0.0)
        self.assertEqual(stats["broken"].last_error_kind, "FetchError")
        self.assertEqual(stats["slow"].p95_latency_ms, 7_000)

    def test_health_score_orders_healthy_above_slow_above_broken(self):
        rows = [run("fast")] + [run("slow", latency_ms=6_000)] + [
            run("broken", status="error", result_count=0)
        ]

        ordered = [stat.provider for stat in summarize_engine_runs(rows)]

        self.assertEqual(ordered, ["fast", "slow", "broken"])

    def test_percentile_reports_an_observed_sample_not_an_interpolation(self):
        self.assertEqual(percentile_ms([10, 20, 30, 40], 95), 40)
        self.assertEqual(percentile_ms([10, 20, 30, 40], 50), 20)
        self.assertEqual(percentile_ms([], 95), 0)

    def test_weak_engines_needs_history_before_demoting(self):
        occasional_failure = summarize_engine_runs(
            [run("flaky", status="error", result_count=0), run("flaky")]
        )
        self.assertEqual(weak_engines(occasional_failure), [])

        sustained_failure = summarize_engine_runs(
            [run("flaky", status="error", result_count=0) for _ in range(6)]
        )
        self.assertEqual(weak_engines(sustained_failure), ["flaky"])

    def test_weak_engines_catches_slow_and_useless_engines_too(self):
        slow = summarize_engine_runs([run("slow", latency_ms=9_000) for _ in range(6)])
        useless = summarize_engine_runs(
            [run("useless", status="empty", result_count=0) for _ in range(6)]
        )

        self.assertEqual(weak_engines(slow), ["slow"])
        self.assertEqual(weak_engines(useless), ["useless"])


class HealthLedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.archive_path = str(Path(self._tmp.name) / "archive.sqlite")

    def test_recorded_runs_come_back_grouped_per_engine(self):
        archive = Archive(self.archive_path)
        self.addCleanup(archive.close)

        self.assertEqual(archive.record_engine_runs([run("a"), run("b", status="error")]), 2)
        rows = archive.engine_runs()

        self.assertEqual({row["provider"] for row in rows}, {"a", "b"})
        self.assertEqual(len(archive.engine_runs(per_provider=1)), 2)

    def test_ledger_keeps_a_bounded_window_per_engine(self):
        archive = Archive(self.archive_path)
        self.addCleanup(archive.close)

        for _ in range(8):
            archive.record_engine_runs([run("a"), run("b")], keep_per_provider=3)

        rows = archive.engine_runs(per_provider=100)
        self.assertEqual(len(rows), 6)

    def test_meta_search_records_runs_and_then_routes_around_the_broken_engine(self):
        class OkProvider:
            name = "ok"

            def search(self, query, *, limit=10):
                return [SearchResult(title="ok", url="https://example.com/ok", source="ok", rank=1)]

        class FailingProvider:
            name = "boom"
            calls = 0

            def search(self, query, *, limit=10):
                FailingProvider.calls += 1
                raise RuntimeError("provider failed")

        providers = {"ok": OkProvider(), "boom": FailingProvider(), "meta": MetaSearch()}
        env = {"KWR_META_PROVIDERS": "ok,boom", "KWR_ARCHIVE": self.archive_path}

        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.PROVIDERS", providers):
                for _ in range(5):
                    MetaSearch().search("alpha", limit=5)
                calls_before = FailingProvider.calls
                stats = {stat.provider: stat for stat in engine_health()}
                results = MetaSearch().search("alpha", limit=5)

        self.assertEqual(calls_before, 5)
        self.assertEqual(stats["boom"].failures, 5)
        self.assertEqual(stats["ok"].failures, 0)
        self.assertEqual(weak_engines(list(stats.values())), ["boom"])
        # Once the record is long enough to judge, the next search stops paying for it.
        self.assertEqual(FailingProvider.calls, 5)
        self.assertEqual([row["provider"] for row in results[0].metadata["meta_engine_runs"]], ["ok"])

    def test_meta_search_keeps_every_engine_when_they_are_all_weak(self):
        class FailingProvider:
            def __init__(self, name):
                self.name = name

            def search(self, query, *, limit=10):
                raise RuntimeError("provider failed")

        providers = {
            "a": FailingProvider("a"),
            "b": FailingProvider("b"),
            "meta": MetaSearch(),
        }
        env = {"KWR_META_PROVIDERS": "a,b", "KWR_ARCHIVE": self.archive_path}

        with patch.dict(os.environ, env, clear=False):
            with patch("katala_web_research.providers.PROVIDERS", providers):
                for _ in range(7):
                    MetaSearch().search("alpha", limit=5)
                stats = engine_health()

        self.assertEqual(sorted(weak_engines(stats)), ["a", "b"])
        self.assertEqual({stat.runs for stat in stats}, {7})

    def test_health_tracking_stays_off_when_no_archive_is_named(self):
        class OkProvider:
            name = "ok"

            def search(self, query, *, limit=10):
                return [SearchResult(title="ok", url="https://example.com/ok", source="ok", rank=1)]

        providers = {"ok": OkProvider(), "meta": MetaSearch()}
        env = {"KWR_META_PROVIDERS": "ok"}

        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("KWR_ARCHIVE", None)
            with patch("katala_web_research.providers.PROVIDERS", providers):
                results = MetaSearch().search("alpha", limit=5)
            self.assertEqual(engine_health(), [])

        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()

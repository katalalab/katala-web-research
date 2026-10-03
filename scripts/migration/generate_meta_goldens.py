#!/usr/bin/env python3
"""Deterministic Meta fan-out transcripts; entirely synthetic provider/clock/ledger."""
import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

from katala_web_research.models import SearchResult
from katala_web_research.providers import MetaSearch, _run_meta_provider

ROOT = Path(__file__).resolve().parents[2]
cases = []

def add(name, profile="broad", explicit="ddg,github", limit=10, weak=None, reverse=False, errors=None, empty=None, latency=None, route_error=None, record_error=None):
    errors, empty, latency, weak = errors or {}, empty or [], latency or {}, weak or []
    requests, completions, recorded, calls = [], [], [], []
    class FakeProvider:
        def __init__(self, provider): self.provider = provider
        def search(self, query, *, limit):
            if self.provider in errors:
                raise type(errors[self.provider], (Exception,), {})("public-fixture-key must not leak")
            if self.provider in empty: return []
            # A common URL tests completion-order representative selection, with a
            # distinct second result for provider-specific diversity/ranking.
            return [SearchResult("alpha " + self.provider, "https://common.test/alpha", "alpha 日本語 evidence", source=self.provider, rank=1),
                    SearchResult("alpha second", "https://"+self.provider+".test/alpha", "alpha 日本語 evidence", source=self.provider, rank=2)]
    class Future:
        def __init__(self, result): self.value = result
        def result(self): return self.value
    class Pool:
        def __init__(self, max_workers): calls.append({"workers": max_workers})
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def submit(self, callback, provider, query, limit):
            requests.append({"provider": provider, "query": query, "limit": limit})
            milliseconds = latency.get(provider, 0)
            with patch("katala_web_research.providers.get_provider", return_value=FakeProvider(provider)), patch("katala_web_research.providers.time.perf_counter", side_effect=[0.0, milliseconds/1000]):
                value = _run_meta_provider(provider, query, limit)
            completions.append({"request": len(requests)-1, "latency_ms": value[1].latency_ms,
                                "results": [r.to_dict() for r in value[0]] if not value[1].error_kind else None,
                                "error_kind": value[1].error_kind or None})
            return Future(value)
    def completed(futures):
        values = list(futures)
        if reverse: values.reverse()
        return values
    def route(names):
        # The reference helper returns before archive access for an empty list.
        if not names: return names
        calls.append({"weak": True})
        if route_error: raise type(route_error, (Exception,), {})("synthetic ledger error")
        kept = [n for n in names if n not in weak]
        return kept or names
    def record(runs):
        calls.append({"record": True});recorded.extend(r.to_dict() for r in runs)
        if record_error: raise type(record_error, (Exception,), {})("synthetic ledger error")
    with patch.dict(os.environ, {"KWR_META_PROFILE": profile, "KWR_META_PROVIDERS": explicit}, clear=True), patch("katala_web_research.providers.ThreadPoolExecutor", Pool), patch("katala_web_research.providers.as_completed", completed), patch("katala_web_research.providers._route_around_weak_engines", route), patch("katala_web_research.providers._record_engine_runs", record):
        try: expected = {"results": [r.to_dict() for r in MetaSearch().search("alpha 日本語", limit=limit)]}
        except Exception as exc: expected = {"error_kind": type(exc).__name__}
    if reverse: completions.reverse()
    # Transcript stores unannotated engine results: Rust owns engine annotation.
    for completion in completions:
        if completion["results"]:
            for result in completion["results"]:
                for key in ["engine_health_score", "engine_latency_ms", "engine_result_count"]:result["metadata"].pop(key)
    cases.append({"name": name, "profile": profile, "explicit": explicit, "limit": limit, "weak": weak,
                  "requests": requests, "completions": completions, "workers": next((c["workers"] for c in calls if "workers" in c), 0),
                  "weak_calls": sum("weak" in c for c in calls), "record_calls": sum("record" in c for c in calls),
                  "route_error": route_error, "record_error": record_error, "recorded": recorded, "expected": expected})

for limit in [-10, -1, 0, 1, 2, 5, 8, 9, 10, 50]:add("limit-"+str(limit), limit=limit)
for profile in ["broad", "docs", "scholarly", "code", "fresh", "local", "monitoring", "unknown", " DOCS \u001c"]:add("profile-"+profile, profile=profile, explicit="")
add("all-providers-four-workers", explicit="ddg,github,github_code,searxng,brave,jina,openalex,feed")
add("reverse-completion", reverse=True)
add("duplicate-providers", explicit="ddg,github,ddg", reverse=True)
add("partial-errors", errors={"github": "FetchError"})
add("all-errors", errors={"ddg": "TimeoutError", "github": "ValueError"})
add("one-empty", empty=["github"])
add("all-empty", empty=["ddg", "github"])
add("health-weighted", latency={"ddg":5000,"github":1000})
add("route-one-weak", weak=["ddg"])
add("route-all-weak-retained", weak=["ddg","github"])
add("unknown-meta-removed", explicit="meta,unknown,ddg")
add("no-known-providers", explicit="meta,unknown")
add("route-error", route_error="OperationalError")
add("record-error", record_error="OperationalError")
(ROOT / "rust/tests/fixtures/meta-golden.json").write_text(json.dumps({"baseline":"91da3879ee84e8226f858da7d812e0ccb2d898e3", "cases":cases}, ensure_ascii=False, indent=2, sort_keys=True)+"\n")
print("Meta full deterministic transcripts",len(cases))

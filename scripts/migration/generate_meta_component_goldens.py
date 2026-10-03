#!/usr/bin/env python3
"""Pure Python Meta component oracles; no network/process/archive access."""
import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

from katala_web_research.fusion import fuse_and_rank, reciprocal_rank_fusion
from katala_web_research.models import SearchResult
from katala_web_research.providers import (
    PROVIDERS, _MetaEngineRun, _annotate_engine_result, _annotate_meta_result,
    _meta_engine_health_score, _meta_profile, _meta_provider_names,
    _rewrite_query_for_provider,
)

ROOT = Path(__file__).resolve().parents[2]
profiles, health, fusion, annotations = [], [], [], []
for raw in ["", "broad", " DOCS \u001c", "scholarly", "code", "fresh", "local", "monitoring", "unknown", "ß"]:
    for explicit in ["", " \u001c ", "meta,ddg,unknown, github, ddg,", "Meta,DDG,openalex", "invalid", "feed,jina,brave,github_code"]:
        with patch.dict(os.environ, {"KWR_META_PROFILE": raw, "KWR_META_PROVIDERS": explicit}, clear=True):
            profile = _meta_profile()
            names = [n for n in _meta_provider_names(profile) if n in PROVIDERS]
            profiles.append({"raw": raw, "explicit": explicit, "profile": profile, "names": names,
                             "rewrites": {n: _rewrite_query_for_provider("alpha 日本語", provider=n, profile=profile) for n in names}})
for status in ["ok", "empty", "error"]:
    for latency in [0, 999, 1000, 1999, 2000, 4999, 5000]:
        for count, requested in [(0, 2), (1, 8), (2, 8), (3, 8), (8, 8), (12, 8), (1, 0), (1, -1)]:
            health.append({"status": status, "count": count, "latency": latency, "requested": requested,
                           "score": _meta_engine_health_score(status=status, result_count=count, latency_ms=latency, requested=requested)})

def result(n=0, source="ddg", **overrides):
    value = SearchResult(title=f"alpha evidence {n}", url=f"https://fixture{n}.test/alpha", snippet="alpha 日本語 evidence", source=source, rank=n+1)
    for name, data in overrides.items():
        setattr(value, name, data)
    return value

def add(name, lists, weights=None, k=60):
    weights = weights or {}
    def outcome(callback):
        try:
            return {"results": [r.to_dict() for r in callback()]}
        except Exception as exc:
            return {"error_kind": type(exc).__name__}
    inputs = [[r.to_dict() for r in rs] for rs in lists]
    expected_fused = outcome(lambda: reciprocal_rank_fusion(copy.deepcopy(lists), rrf_k=k, engine_health=weights))
    ranked = []
    for limit in [-5, -1, 0, 1, 3, 10]:
        ranked.append({"limit": limit, "expected": outcome(lambda: fuse_and_rank("alpha 日本語", copy.deepcopy(lists), limit=limit, rrf_k=k, engine_health=weights))})
    fusion.append({"name": name, "lists": inputs, "weights": weights, "k": k, "fused": expected_fused, "ranked": ranked})

add("empty", [])
add("normal", [[result(0), result(1)], [result(0, "github"), result(2, "github")]])
add("completion-tie-ddg-first", [[result(0, title="ddg first")], [result(0, "jina", title="jina first")]])
add("completion-tie-jina-first", [[result(0, "jina", title="jina first")], [result(0, title="ddg first")]])
add("lower-rank-representative", [[result(0, rank=7)], [result(0, "github", rank=2, metadata={"own": "retained"})]])
add("zero-rank-replacement-reference-quirk", [[result(0, rank=0)], [result(1), result(0, "github", rank=1)]])
add("canonical-urls", [[result(0, url="HTTPS://EXAMPLE.TEST/alpha/;params?query=1#fragment"), result(1, url="https://example.test/alpha/")], [result(2, "github", url="https://example.test/alpha?query=2")]])
add("discard-invalid-relative-empty", [[result(0, url=""), result(1, url="relative/path"), result(2, url="repo:thing"), result(3)]])
add("empty-source-fallback", [[result(0, source="", rank=0)], [result(0, source="", rank=0)]])
add("same-source-multiple-canonical-rows", [[result(0, rank=4), result(0, rank=2), result(0, rank=3)]])
for value in [-1, 0, 0.4, 2, True, False, None, "0.2", "invalid", "NaN", "inf", "-inf"]:
    add("health-"+str(value), [[result(0)], [result(0, "github")]], {"ddg": value, "github": 0.4})
add("metadata-health-fallback", [[result(0, metadata={"engine_health_score": "0.3"}), result(1, metadata={"engine_health_score": 0.9})]])
add("health-map-overrides-metadata", [[result(0, metadata={"engine_health_score": 0.1})]], {"ddg": 0.9})
add("health-same-source-max", [[result(0, metadata={"engine_health_score": 0.1}), result(0, rank=2, metadata={"engine_health_score": 0.9})]])
add("rank-zero-negative", [[result(0, rank=0), result(1, rank=-2), result(2, rank=-3)]])
add("zero-division", [[result(0, rank=-60)]])
add("quality-diversity", [[result(i, url=url) for i, url in enumerate(["https://docs.python.org/alpha", "https://github.com/a/alpha", "https://github.com/b/alpha", "https://arxiv.org/abs/alpha", "https://doi.org/alpha", "https://other.test/alpha", "https://third.test/alpha"]) ]])
for name, overrides in [("empty-title", {"title": ""}), ("retraction", {"snippet": "retracted=true alpha"}), ("bad-year-surviving", {"published_at": "²⁰²⁶"}), ("bad-year-retracted", {"published_at": "²⁰²⁶", "snippet": "retracted=true"})]:
    add(name, [[result(0), result(1, **overrides)]])
run = _MetaEngineRun("ddg", "ok", 1000, 3, 0.794)
for runs in [[run], [run, _MetaEngineRun("brave", "error", 1, 0, 0.0, "FetchError"), _MetaEngineRun("ddg", "empty", 0, 0, 0.35)]]:
    r = result(0, metadata={"own": "preserved"})
    engine = _annotate_engine_result(r, run)
    annotations.append({"input": r.to_dict(), "run": run.to_dict(), "runs": [rr.to_dict() for rr in runs],
                        "engine": engine.to_dict(), "meta": _annotate_meta_result(engine, profile="docs", provider_names=["ddg", "brave", "ddg"], runs=runs).to_dict()})
payload = {"baseline": "91da3879ee84e8226f858da7d812e0ccb2d898e3", "profiles": profiles, "health": health, "fusion": fusion, "annotations": annotations}
(ROOT / "rust/tests/fixtures/meta-component-golden.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)+"\n")
print("Meta component oracles", {key: len(payload[key]) for key in ["profiles", "health", "fusion", "annotations"]})

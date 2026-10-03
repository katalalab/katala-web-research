#!/usr/bin/env python3
"""Unchanged Python workflow/reader/rank oracle; raw I/O is strictly in memory."""
import copy
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from katala_web_research import reader, workflow
from katala_web_research.http import FetchError, HttpResponse
from katala_web_research.models import SearchResult

ROOT = Path(__file__).resolve().parents[2]
CASES = []


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 1, 1)


def result(index, **changes):
    value = dict(title=f"Thin {index}", url=f"https://example.test/{index}",
                 snippet="old snippet", source="ddg", published_at=None,
                 rank=index, score=9.0, metadata={"marker":index})
    value.update(changes)
    return value


def add(name, inputs=None, contents=None, errors=None, mode="direct", top=1):
    inputs = inputs if inputs is not None else [result(1), result(2)]
    contents = contents if contents is not None else ["alpha 日本語 evidence"]
    errors = errors or []
    steps, clocks = [], []

    def fetch(target, **kwargs):
        index = len(steps)
        error = errors[index] if index < len(errors) else None
        content = contents[min(index, len(contents)-1)]
        response = dict(url="https://redirect.test/final", status=200,
                        headers={"content-type":"text/plain; charset=utf-8"},
                        body=list(content.encode()))
        steps.append(dict(request={"url":target,"headers":kwargs.get("headers",{})},
                          response=response, error_kind=error))
        if error:
            exc = FetchError if error == "FetchError" else type(error, (Exception,), {})
            raise exc("synthetic-private-marker")
        return HttpResponse(response["url"], response["status"], response["headers"], bytes(response["body"]))

    def clock():
        clocks.append(1)
        return "2026-01-01T00:00:00+00:00"

    with patch.object(reader, "fetch_url", fetch), patch.object(reader, "utc_now_iso", clock), \
            patch("katala_web_research.source_quality.date", FixedDate):
        expected = workflow.enrich_search_results("alpha 日本語", [SearchResult(**copy.deepcopy(r)) for r in inputs],
                                                  read_top=top, reader=mode)
    CASES.append(dict(name=name, query="alpha 日本語", results=inputs, read_top=top, reader=mode,
                      steps=steps, clock_calls=len(clocks), expected=[r.to_dict() for r in expected]))


for top in [-5, 0, 1, 2, 7]:
    for mode in ["direct", "jina", "auto", "unknown"]:
        add(f"top-{top}-{mode}", top=top, mode=mode)
for mode in ["direct", "jina", "unknown"]:
    add("empty-"+mode, inputs=[], mode=mode, top=2)
for content in ["", " \t\n\x1c\x1f ", "a\x1cb\x1dc\x1ed\x1fe", "a\u0085b\u00a0c\u2028d\u3000e",
                " &amp; <literal> content ", "日"*699+"éZ", "日"*700+"éZ", "日"*701, "e\u0301"*351]:
    add("content-"+str(len(CASES)), contents=[content])
for mode in ["direct", "jina", "auto"]:
    for error in ["FetchError", "TimeoutError", "ValueError", "RuntimeError"]:
        add("error-"+str(len(CASES)), mode=mode, errors=[error])
for mode in ["direct", "jina"]:
    add("stale-success-"+mode, inputs=[result(1, metadata={"read_error_kind":"OldError", "nested":[1,{"keep":True}]})], mode=mode)
    add("stale-error-"+mode, inputs=[result(1, metadata={"read_source":"old", "read_status_code":201})], mode=mode, errors=["FetchError"])
    add("empty-title-"+mode, inputs=[result(1,title="")], mode=mode)
add("empty-title-read-failure", inputs=[result(1,title="")], errors=["FetchError"])
add("duplicate-read-before-dedup", inputs=[result(1),result(2,url="https://example.test/1?q=x#f")],top=2)
add("retraction-read-before-discard", contents=["retracted=true alpha"])
add("rerank-unselected", inputs=[result(1), result(2,title="alpha 日本語")], contents=["unrelated"])
add("publication-source-rank", inputs=[result(9,source="jina",published_at="2026-01-02",metadata={"provider_rank":22})])
add("invalid-url-lazy", inputs=[result(1,url="file:///owned/fixture")])
add("invalid-url-noop", inputs=[result(1,url="file:///owned/fixture")],top=0)
path = ROOT / "rust/tests/fixtures/enrichment-golden.json"
path.write_text(json.dumps(CASES,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("enrichment raw workflow/reader/rank transcripts:", len(CASES))

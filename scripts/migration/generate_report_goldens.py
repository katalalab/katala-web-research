#!/usr/bin/env python3
"""Unchanged Python renderer oracles; no archive, reader or network operations."""
import json
from pathlib import Path
import random
import struct
from unittest.mock import patch
from katala_web_research.models import PageSnapshot, SearchResult
from katala_web_research.report import build_report

ROOT = Path(__file__).resolve().parents[2]
CASES = []
STAMP = "2026-01-01T00:00:00+00:00"


def result(**changes):
    row = dict(title="alpha 日本語",url="https://fixture.test/item",snippet="evidence",
               source="feed",published_at=None,rank=1,score=1.25,metadata={"ignored":[True,None]})
    row.update(changes)
    return row


def page(content, **changes):
    row = dict(title="Captured 日本語",url="https://fixture.test/page",content=content,
               source="direct",fetched_at=STAMP,status_code=200,content_type="text/plain")
    row.update(changes)
    return row


def add(name, results=None, pages=None, query="alpha 日本語", provider="feed", archive="日本語 selected.sqlite", score_text=None):
    rows = [result()] if results is None else results
    models = [SearchResult(**r) for r in rows]
    if score_text is not None:
        models[0].score = float(score_text)
    calls = []
    def clock():
        calls.append(1)
        return STAMP
    with patch("katala_web_research.report.utc_now_iso",clock):
        expected = build_report(query=query,provider=provider,results=models,
                                pages=[PageSnapshot(**p) for p in (pages or [])],archive_path=archive)
    assert calls == [1]
    CASES.append(dict(name=name,query=query,provider=provider,archive=archive,results=rows,
                      pages=pages or [],score_text=score_text,clock_calls=len(calls),expected=expected))


add("empty",results=[])
add("single")
add("empty-fields",[result(title="",url="",snippet="",source="",published_at="",rank=0)],query="",provider="",archive="")
add("duplicates-order",[result(rank=7),result(rank=-9),result(rank=0)])
add("literal-markdown",[result(title="# `title`\n日本語",snippet="&amp; \n literal\t",published_at="invalid\n",source="fixture\x00")],query="query\n## literal",archive="a`b.sqlite")
for content in ["", "\t \n\r\x1c\x1d\x1e\x1f\u0085\u00a0\u1680\u2000\u2028\u202f\u205f\u3000", "a\n\nb\r\tc &amp; <html>", "😀日本語"*300, "a"*699+"\n"+"z", "a"*699+"😀"+"z", "\x1c alpha \x1f", "a\u200bb\ufeffc"]:
    add("page-"+str(len(CASES)),pages=[page(content)])
add("multiple-pages",pages=[page("one\n\ntwo",source="jina"),page("Read failed: synthetic classification",source="error",fetched_at="",status_code=None,content_type=None,title="")])
for value in ["0.0","-0.0","1.0","-1.25","0.0001","0.00001","0.000001","1000000000000000.0","1e16","1e23","1e100","1e-100","2.2250738585072014e-308","5e-324","1.7976931348623157e308","nan","inf","-inf"]:
    add("score-"+value,score_text=value)
rng = random.Random(31)
for idx in range(64):
    value = struct.unpack(">d",rng.getrandbits(64).to_bytes(8,"big"))[0]
    add("score-bits-"+str(idx),score_text=str(value))
path = ROOT/"rust/tests/fixtures/report-golden.json"
path.write_text(json.dumps(CASES,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("Pure Python report cases:",len(CASES))

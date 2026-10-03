#!/usr/bin/env python3
"""Python Archive.store_run oracle using synthetic temporary SQLite only."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from katala_web_research.archive import Archive
from katala_web_research.models import SearchResult

ROOT = Path(__file__).resolve().parents[2]
CASES = []


def result(**changes):
    value = dict(title="alpha 日本語",url="https://fixture.test/item",snippet="evidence",
                 source="feed",published_at=None,rank=1,score=1.25,
                 metadata={"ignored":{"keep":[1,True,None]}})
    value.update(changes)
    return value


def add(name, rows, query="alpha 日本語", provider="feed", repeats=2):
    operations = [dict(query=query,provider=provider,results=rows) for _ in range(repeats)]
    expected = []
    clocks = []

    def clock():
        clocks.append(1)
        return "2026-01-01T00:00:00+00:00"

    with tempfile.TemporaryDirectory(prefix="kwr-collect-oracle-") as tmp:
        archive = Archive(Path(tmp)/"synthetic.sqlite")
        try:
            with patch("katala_web_research.archive.utc_now_iso",clock):
                for operation in operations:
                    run_id = archive.store_run(operation["query"],operation["provider"],
                                               [SearchResult(**r) for r in operation["results"]])
                    expected.append(dict(run_id=run_id,
                        runs=[dict(r) for r in archive.conn.execute("SELECT * FROM runs ORDER BY id")],
                        results=[dict(r) for r in archive.conn.execute("SELECT * FROM search_results ORDER BY id")]))
        finally:
            archive.close()
    CASES.append(dict(name=name,calls=operations,expected=expected,clock_calls=len(clocks)))


add("empty",[])
add("single",[result()])
add("empty-query-provider",[result()],query="",provider="")
add("duplicates-not-deduplicated",[result(),result(title="second",rank=9)],repeats=3)
add("input-order-retained",[result(rank=7),result(rank=-1,title="second"),result(rank=0,title="third")])
add("unicode-control",[result(title="Cafe\u0301 日本語\x00",url="file:///synthetic/日本語",snippet="a\x1cb\u2028c\n"*10,source="fixture\t",published_at="日本語")],query="\x00 α 日本語",provider="unknown\n")
for score in [0.0,-0.0,1.0,-1.25,0.001,1e100,1e-100,2.2250738585072014e-308]:
    add("score-"+str(len(CASES)),[result(score=score)])
for rank in [-9223372036854775808,-1,0,9223372036854775807]:
    add("rank-"+str(len(CASES)),[result(rank=rank)])
for published in [None,"","2026-01-02","invalid", "٢٠٢٦-01-02"]:
    add("published-"+str(len(CASES)),[result(published_at=published)])
for field in ["title","url","snippet","source"]:
    add("empty-"+field,[result(**{field:""})])
add("large-text-metadata",[result(title="日本語"*200,snippet="evidence "*200,metadata={"read_status":"error","rrf_score":9,"ignored":["nested"]})])
path = ROOT/"rust/tests/fixtures/collect-storage-golden.json"
path.write_text(json.dumps(CASES,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print("collect store_run Python sequences:",len(CASES),"committed calls:",sum(len(c["calls"]) for c in CASES))

#!/usr/bin/env python3
"""Feed-only collect vs unchanged Python on synthetic copies; never start sockets."""
from datetime import datetime, timezone
import itertools
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import collect_storage_differential as storage
import json_provider_differential as preservation
import reader_differential as seed
from katala_web_research.archive import Archive
from katala_web_research.models import FeedItem, FeedSource, PageSnapshot
from katala_web_research.providers import search
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BINARY = Path(os.environ.get("KWR_RUST_BINARY",ROOT/"target/debug/kwr-rs"))
SELECTED = "日本語 selected.sqlite"
PROVIDERS = ["brave","ddg","feed","github","github_code","jina","meta","openalex","searxng"]


def timestamp(value, before, after):
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00",value),value
    parsed = datetime.fromisoformat(value)
    assert before.replace(microsecond=0) <= parsed <= after.replace(microsecond=0),value
    return "<validated-UTC-second>"


class CollectFixture(unittest.TestCase):
    pairs = 0
    failures = 0
    refusals = 0
    policies = 0

    def seed(self, root):
        db,other = root/SELECTED,root/"unselected.sqlite"
        seed.ReaderFixture.seed(self,db,"https://fixture.test/old")
        seed.ReaderFixture.seed(self,other,"https://fixture.test/unselected")
        a = Archive(db)
        a.upsert_page(PageSnapshot("http://127.0.0.1/never-fetch","old error","old evidence error retained","error","",None,None))
        a.upsert_feed_source(FeedSource("https://fixture.test/feed","Synthetic feed","rss","fixed","fixed","ok",1.0,"",5))
        a.upsert_feed_items([
            FeedItem("https://fixture.test/feed",url,title,content,"Synthetic feed",date,"fixed")
            for url,title,content,date in [
                ("https://docs.python.org/evidence","official evidence 日本語","atomic evidence &amp; snippet","2026-01-02"),
                ("https://arxiv.org/evidence","paper evidence","atomic evidence paper","2025-12-01"),
                ("http://127.0.0.1/never-fetch","private evidence","atomic evidence literal URL only",None),
                ("https://fixture.test/old","old evidence","atomic evidence preserves cached page",""),
                ("https://fixture.test/raw?q=x#fragment","UTF-8 日本語 evidence","atomic evidence query","invalid"),
            ]])
        a.upsert_feed_source(FeedSource("https://fixture.test/duplicate","Duplicate feed","rss","fixed","fixed","ok",1.0,"",1))
        a.upsert_feed_items([FeedItem("https://fixture.test/duplicate","https://arxiv.org/evidence","duplicate evidence","atomic evidence duplicate","Duplicate feed",None,"fixed")])
        a.close()
        return db,other

    def env(self, other):
        # No inherited tokens/proxies/config, no executable helpers; local feed must work.
        return dict(PATH="",PYTHONPATH=str(ROOT/"src"),KWR_ARCHIVE=str(other),
                    KWR_HTTP_TIMEOUT_SECONDS="invalid",KWR_META_PROVIDERS="invalid",
                    KWR_SEARXNG_URL="invalid",KWR_JINA_READER_URL="invalid")

    def call(self, root, env, native, args):
        prefix = [str(BINARY)] if native else [sys.executable,"-m","katala_web_research.cli"]
        start = datetime.now(timezone.utc)
        proc = subprocess.run(prefix+["collect",*args],cwd=root,env=env,capture_output=True,text=True,encoding="utf-8",timeout=10)
        return proc,start,datetime.now(timezone.utc)

    def normalize_report(self, value, start, end):
        match = re.search(r"(?m)^- generated_at: (.+)$",value)
        self.assertIsNotNone(match)
        stamp = match.group(1)
        timestamp(stamp,start,end)
        return value[:match.start(1)]+"<validated-UTC-second>"+value[match.end(1):]

    def assert_state(self, before, after, starts, ends, run_count, row_count):
        self.assertEqual(before["schema"],after["schema"])
        self.assertEqual(before["version"],after["version"])
        self.assertEqual(before["matches"],after["matches"])
        for name in ["pages","repo_documents","feed_sources","feed_items","project_items","engine_runs"]:
            self.assertEqual(before["tables"][name],after["tables"][name],name)
        for name,count in [("runs",run_count),("search_results",row_count)]:
            old = before["tables"][name]
            self.assertEqual(after["tables"][name][:len(old)],old)
            self.assertEqual(len(after["tables"][name]),len(old)+count)
        for run,start,end in zip(after["tables"]["runs"][len(before["tables"]["runs"]):],starts,ends,strict=True):
            run["created_at"] = timestamp(run["created_at"],start,end)

    def compare(self, query="evidence", options=None, mode="success", repeats=1):
        options = ["--json"] if options is None else options
        outputs,states,reports = [],[],[]
        with tempfile.TemporaryDirectory(prefix="kwr-collect-report-") as tmp:
            for native in [False,True]:
                root = Path(tmp)/("native" if native else "python")
                root.mkdir()
                db,other = self.seed(root)
                report_option = options[options.index("--report")+1] if "--report" in options else None
                report_path = root/report_option if report_option else None
                if mode == "directory-fail":
                    (root/"reports").write_text("old file",encoding="utf-8")
                if mode == "sql-abort":
                    with sqlite3.connect(db) as conn:
                        conn.execute("CREATE TRIGGER fail_later BEFORE INSERT ON search_results WHEN new.rank=2 BEGIN SELECT RAISE(ABORT,'owned CLI fixture'); END;")
                before,untouched = storage.state(db),preservation.snapshot(other)
                starts,ends,values,texts = [],[],[],[]
                limit = int(options[options.index("--limit")+1]) if "--limit" in options else int(options[options.index("-n")+1]) if "-n" in options else 10
                # An independent unchanged Python feed lookup determines the commit
                # count even when the CLI fails before emitting a receipt.
                with patch.dict(os.environ,self.env(other),clear=True):
                    expected_results = [r.to_dict() for r in search(query,provider="feed",limit=limit,archive_path=str(db))]
                for _ in range(repeats):
                    args = [query,"--provider","feed",*([] if "--read-top" in options else ["--read-top","0"]),"--archive",SELECTED,*options]
                    proc,start,end = self.call(root,self.env(other),native,args)
                    failed = mode != "success"
                    self.assertEqual(proc.returncode,1 if failed else 0,(native,args,proc.stderr))
                    if failed:
                        self.assertEqual(proc.stdout,"")
                        if native and mode == "directory-fail":
                            self.assertIn("report failed after committed run_id=",proc.stderr)
                    else:
                        self.assertEqual(proc.stderr,"")
                        value = json.loads(proc.stdout) if "--json" in options else proc.stdout
                        if isinstance(value,dict):
                            self.assertEqual(value["pages"],[])
                            self.assertEqual(value["archive"],SELECTED)
                            self.assertEqual(value["run_id"],len(before["tables"]["runs"])+len(values)+1)
                            self.assertEqual(value["results"],expected_results)
                        else:
                            self.assertEqual(int(re.search(r"(?m)^results: (\d+)$",value).group(1)),len(expected_results))
                        values.append(value)
                        if report_path:
                            self.assertTrue(report_path.is_file())
                            texts.append(self.normalize_report(report_path.read_text(encoding="utf-8"),start,end))
                    if mode != "sql-abort":
                        starts.append(start)
                        ends.append(end)
                after = storage.state(db)
                new = after["tables"]["search_results"][len(before["tables"]["search_results"]):]
                receipt_rows = len(starts)*len(expected_results)
                if mode == "directory-fail":
                    self.assertGreater(len(new),0)
                    self.assertEqual((root/"reports").read_text(),"old file")
                self.assert_state(before,after,starts,ends,len(starts),receipt_rows)
                self.assertEqual(untouched,preservation.snapshot(other))
                self.assertFalse((root/".katala-web-research").exists())
                self.assertEqual(list(root.rglob(".kwr-report-*")),[])
                outputs.append(values)
                states.append(after)
                reports.append(texts)
            self.assertEqual(*outputs,(query,options,mode))
            self.assertEqual(*states,(query,options,mode))
            self.assertEqual(*reports,(query,options,mode))
            if mode == "success":type(self).pairs += 1
            else:type(self).failures += 1

    def test_signed_limits_queries_metadata_and_outputs(self):
        for query,limit in itertools.product(["evidence","日本語","", "notfound", "evidence\x1catomic"],[-9223372036854775808,-5,-1,0,1,3,10,9223372036854775807]):
            self.compare(query,["--limit",str(limit),"--json"])
        self.compare(options=["-n","3"])
        self.compare(options=["--limit","0"])
        self.compare(options=["--read-top","-5","--reader","jina","--json"])
        self.compare(options=["--read-top","0","--reader","direct","--json"],repeats=3)
        self.compare(options=["--report","","--json"])

    def test_new_reports_and_commit_then_report_failure(self):
        for args in [["--report","reports/日本語.md","--json"],["--report","./reports//./日本語.md"],["--report","日本語.md","--limit","0","--json"]]:
            self.compare(options=args)
        self.compare(options=["--report","reports/child.md","--json"],mode="directory-fail")
        self.compare(options=["--json"],mode="sql-abort")

    def test_refuse_capture_and_non_feed_before_any_runtime_work(self):
        cases = [["evidence","--provider",p,"--reader",r,"--limit",str(n)] for p,r,n in itertools.product(PROVIDERS,["auto","direct","jina"],[0,1])]
        cases += [["evidence","--provider",p,"--reader",r,"--read-top","-1"] for p,r in itertools.product([p for p in PROVIDERS if p != "feed"],["auto","direct","jina"])]
        cases += [["evidence"],["evidence","--provider","feed"]]
        for args in cases:
            with tempfile.TemporaryDirectory(prefix="kwr-collect-refuse-") as tmp:
                root=Path(tmp)
                env=self.env(root/"other.sqlite")|{"KWR_SOURCE_REGISTRY_OVERLAY":str(root/"invalid-registry")}
                proc,_,_=self.call(root,env,True,args+["--archive","new/archive.sqlite","--report","new/report.md","--json"])
                self.assertEqual(proc.returncode,1)
                self.assertEqual(proc.stdout,"")
                self.assertRegex(proc.stderr,"capture is disabled|supports only --provider feed")
                self.assertEqual(list(root.iterdir()),[])
                type(self).refusals += 1

    def test_named_no_clobber_keeps_committed_runs_and_existing_content(self):
        # Never execute Python's archive-collision overwrite, even on this copy.
        for mode in ["old-report","archive-collision","symlink"]:
            with tempfile.TemporaryDirectory(prefix="kwr-collect-policy-") as tmp:
                root=Path(tmp)
                db,other=self.seed(root)
                if mode == "archive-collision":report_path=db
                else:
                    report_path=root/"old.md"
                    (root/"original.md").write_text("original 日本語",encoding="utf-8")
                    if mode == "symlink":report_path.symlink_to("original.md")
                    else:report_path.write_text("old 日本語",encoding="utf-8")
                before,untouched=storage.state(db),preservation.snapshot(other)
                old_bytes=report_path.read_bytes() if mode != "archive-collision" else None
                proc,start,end=self.call(root,self.env(other),True,["evidence","--provider","feed","--read-top","0","--archive",SELECTED,"--report",report_path.name,"--json"])
                self.assertEqual(proc.returncode,1)
                self.assertEqual(proc.stdout,"")
                self.assertIn("report failed after committed run_id=2:",proc.stderr)
                after=storage.state(db)
                count=len(after["tables"]["search_results"])-len(before["tables"]["search_results"])
                self.assertGreater(count,0)
                self.assert_state(before,after,[start],[end],1,count)
                if old_bytes is not None:self.assertEqual(report_path.read_bytes(),old_bytes)
                if mode == "symlink":self.assertTrue(report_path.is_symlink())
                self.assertEqual(untouched,preservation.snapshot(other))
                self.assertEqual(list(root.rglob(".kwr-report-*")),[])
                type(self).policies += 1

    def test_help_explains_partial_scope_without_creating_archive(self):
        with tempfile.TemporaryDirectory(prefix="kwr-collect-help-") as tmp:
            root=Path(tmp)
            proc,_,_=self.call(root,self.env(root/"other.sqlite"),True,["--help"])
            self.assertEqual(proc.returncode,0)
            self.assertEqual(proc.stderr,"")
            self.assertIn("requires --provider feed --read-top 0",proc.stdout)
            self.assertIn("Positive values disabled",proc.stdout)
            self.assertIn("existing destinations are refused",proc.stdout)
            self.assertEqual(list(root.iterdir()),[])

    def test_named_existing_report_difference_against_python_copy(self):
        states=[]
        with tempfile.TemporaryDirectory(prefix="kwr-report-difference-") as tmp:
            for native in [False,True]:
                root=Path(tmp)/("native" if native else "python")
                root.mkdir()
                db,other=self.seed(root)
                path=root/"existing.md"
                path.write_text("old 日本語",encoding="utf-8")
                before,untouched=storage.state(db),preservation.snapshot(other)
                proc,start,end=self.call(root,self.env(other),native,["evidence","--provider","feed","--read-top","0","--archive",SELECTED,"--report",path.name,"--json"])
                self.assertEqual(proc.returncode,1 if native else 0)
                after=storage.state(db)
                with patch.dict(os.environ,self.env(other),clear=True):
                    expected=[r.to_dict() for r in search("evidence",provider="feed",archive_path=str(db))]
                self.assert_state(before,after,[start],[end],1,len(expected))
                if native:
                    self.assertEqual(proc.stdout,"")
                    self.assertEqual(path.read_text(),"old 日本語")
                    self.assertIn("report failed after committed run_id=2:",proc.stderr)
                else:
                    self.assertEqual(proc.stderr,"")
                    self.assertEqual(json.loads(proc.stdout)["results"],expected)
                    self.assertEqual(json.loads(proc.stdout)["run_id"],2)
                    self.assertIn("# Web Research Report:",self.normalize_report(path.read_text(),start,end))
                self.assertEqual(untouched,preservation.snapshot(other))
                self.assertEqual(list(root.rglob(".kwr-report-*")),[])
                states.append(after)
            self.assertEqual(*states)
            type(self).policies += 1


if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CollectFixture))
    print("Collect strict CLI pairs:",CollectFixture.pairs,"paired failures:",CollectFixture.failures,"pre-I/O refusals:",CollectFixture.refusals,"no-clobber preservation cases:",CollectFixture.policies)
    raise SystemExit(not result.wasSuccessful())

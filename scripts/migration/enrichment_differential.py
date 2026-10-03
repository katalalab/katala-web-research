#!/usr/bin/env python3
"""Paired search/feed/enrichment over owned loopback, without archive writes."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import http_differential as fixture
import jina_reader_differential as jina
import reader_differential as direct
import json_provider_differential as preservation
from katala_web_research.archive import Archive
from katala_web_research.models import FeedItem, PageSnapshot


class CombinedHandler(jina.Handler):
    origins = []
    search_mode = "normal"

    def do_GET(self):
        if urlsplit(self.path).path != "/search":
            return super().do_GET()
        jina.TRACE.append(("search",self.path,{k.lower():v for k,v in self.headers.items()}))
        body = json.dumps({"results":[{"url":origin+f"/{self.search_mode}?item={i}",
                                      "title":f"alpha 日本語 thin {i}","content":"alpha 日本語 old snippet"}
                                     for i,origin in enumerate(self.origins)]},ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


class EnrichmentFixture(jina.JinaFixture):
    comparisons = 0
    signals = 0

    @classmethod
    def setUpClass(cls):
        with patch.object(jina,"Handler",CombinedHandler):
            super().setUpClass()
        CombinedHandler.origins = [cls.plain,cls.plain.replace("127.0.0.1","localhost")]

    def prepare(self, path, mode, highlight=False):
        self.seed(path, self.plain+"/old")
        archive = Archive(path)
        archive.conn.execute("DELETE FROM feed_items")
        # Same-host diversity is applied by the actual provider before enrichment.
        archive.upsert_feed_items([
            FeedItem("https://fixture.test/feed", origin+f"/{mode}?item={i}",
                     f"alpha 日本語 thin {i}", "alpha 日本語 old snippet", "Fixture feed", None, "fixed")
            for i,origin in enumerate([self.plain,self.plain.replace("127.0.0.1","localhost")])
        ])
        if highlight:
            archive.upsert_page(PageSnapshot(self.plain+f"/{mode}?item=0", "Cache title",
                                            "alpha 日本語 cached evidence. More details.", "cached", "fixed"))
        archive.close()

    def compare_search(self, mode="normal", reader="direct", limit=1, top=2, options=None, highlight=False, provider="feed", extra=None):
        options = options if options is not None else ["--json"]
        outputs, traces = [], []
        CombinedHandler.search_mode = mode
        with tempfile.TemporaryDirectory(prefix="kwr-enrichment-") as tmp:
            for native in [False, True]:
                root = Path(tmp)/("native" if native else "python")
                root.mkdir()
                selected = root/"日本語 selected.sqlite"
                other = root/"unselected.sqlite"
                self.prepare(selected, mode, highlight)
                self.seed(other, self.plain+"/other")
                before = direct.state(selected)
                untouched = preservation.snapshot(other)
                prefix = [str(fixture.BINARY)] if native else [sys.executable,"-m","katala_web_research.cli"]
                start = len(jina.TRACE)
                args = ["search", "alpha 日本語", "--provider", provider, "--archive", str(selected),
                        "--limit", str(limit), "--candidate-multiplier", "4", "--enrich-top", str(top),
                        "--reader", reader, *options, *(extra or [])]
                if highlight:
                    args += ["--highlight-top", "2"]
                proc = subprocess.run(prefix+args, cwd=root, env=dict(self.env_for(other, mode),KWR_SEARXNG_URL=self.tls),
                                      capture_output=True, text=True, timeout=20)
                self.assertEqual(proc.returncode, 0, (native,args,proc.stderr))
                self.assertEqual(proc.stderr, "")
                self.assertEqual(before, direct.state(selected))
                self.assertEqual(untouched, preservation.snapshot(other))
                self.assertFalse((root/".katala-web-research").exists())
                value = json.loads(proc.stdout) if "--json" in options else proc.stdout
                outputs.append(value)
                traces.append([(role, path, {k:v for k,v in headers.items() if k in ["accept","user-agent","authorization"]})
                               for role,path,headers in jina.TRACE[start:]])
                if isinstance(value,list):
                    for row in value:
                        self.assertNotIn("synthetic error body", json.dumps(row))
                        self.assertEqual(row["source"], provider)
                        self.assertIn(row["url"], [origin+f"/{mode}?item={i}" for i,origin in enumerate([self.plain,self.plain.replace("127.0.0.1","localhost")])])
                for role,_,headers in traces[-1]:
                    self.assertNotIn("authorization", headers)
                    self.assertEqual(headers["accept"], "application/json" if role=="search" else "text/plain" if role=="jina" else "text/html, text/plain;q=0.9, */*;q=0.5")
            self.assertEqual(*outputs)
            self.assertEqual(*traces)
            reads = [r for r in traces[0] if r[0] != "search"]
            if top > 0 and reader != "unknown":
                self.assertTrue(reads, "positive enrichment must still read with zero/negative limit")
            else:
                self.assertEqual(reads, [])
            type(self).comparisons += 1

    def test_reader_modes_signed_limits_and_rendering(self):
        for reader in ["direct","jina","auto"]:
            for limit in [-1,0,1,2]:
                for options in [["--json"],[]]:
                    self.compare_search(reader=reader,limit=limit,options=options)

    def test_failure_fallback_and_highlight(self):
        for mode,reader in [("error","jina"),("error","auto"),("payload","auto"),
                            ("both-error","auto"),("timeout","auto"),("direct-redirect","auto"),
                            ("empty","jina"),("domain-json","jina"),("jina-redirect","jina")]:
            self.compare_search(mode=mode,reader=reader,limit=2)
        for reader in ["direct","jina"]:
            self.compare_search(reader=reader,highlight=True)

    def test_lazy_invalid_reader_and_top(self):
        for top in [-3,0,1,99]:
            self.compare_search(reader="direct",top=top)
        self.compare_search(top=0)

    def test_network_search_category_and_enrichment(self):
        for reader in ["direct","jina","auto"]:
            for limit in [-1,0,1]:
                self.compare_search(provider="searxng",reader=reader,limit=limit)
            self.compare_search(mode="normal.pdf",provider="searxng",reader=reader,highlight=True,extra=["--category","pdf","--include-domain","127.0.0.1"])

    def test_owned_http_wait_interrupt(self):
        for native in [False,True]:
            with tempfile.TemporaryDirectory(prefix="kwr-enrichment-signal-") as tmp:
                root = Path(tmp)
                selected = root/"selected.sqlite"
                self.prepare(selected,"held")
                before = direct.state(selected)
                jina.STARTED.clear()
                jina.RELEASE.clear()
                prefix = [str(fixture.BINARY)] if native else [sys.executable,"-m","katala_web_research.cli"]
                child = subprocess.Popen(prefix+["search","alpha 日本語","--provider","feed","--archive",str(selected),
                                                "--enrich-top","1","--reader","jina","--json"],
                                         cwd=root,env=self.env_for(selected,"held"),stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,text=True,start_new_session=True)
                try:
                    self.assertTrue(jina.STARTED.wait(3))
                    os.killpg(child.pid,signal.SIGINT)
                    stdout,_ = child.communicate(timeout=3)
                    self.assertEqual(child.returncode,-signal.SIGINT)
                    self.assertEqual(stdout,"")
                    self.assertEqual(before,direct.state(selected))
                    type(self).signals += 1
                finally:
                    jina.RELEASE.set()
                    if child.poll() is None:
                        os.killpg(child.pid,signal.SIGKILL)
                        child.communicate(timeout=3)


if __name__ == "__main__":
    methods = {"test_reader_modes_signed_limits_and_rendering","test_failure_fallback_and_highlight",
               "test_lazy_invalid_reader_and_top","test_owned_http_wait_interrupt","test_network_search_category_and_enrichment"}
    wanted = set(sys.argv[1:]) or methods
    assert wanted <= methods
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EnrichmentFixture)
    suite = unittest.TestSuite(test for test in suite if test._testMethodName in wanted)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("Enrichment paired CLI cases:",EnrichmentFixture.comparisons,"owned signal executions:",EnrichmentFixture.signals)
    sys.exit(not result.wasSuccessful())

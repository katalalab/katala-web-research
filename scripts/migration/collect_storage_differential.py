#!/usr/bin/env python3
"""Native store_run vs Python on populated synthetic SQLite; no sockets/providers."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import reader_differential as seed
import json_provider_differential as preservation
from katala_web_research.archive import Archive
from katala_web_research.models import SearchResult

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(os.environ.get("KWR_STORE_RUN_PROBE",ROOT/"target/debug/examples/store_run_probe"))
CASES = json.loads((ROOT/"rust/tests/fixtures/collect-storage-golden.json").read_text())
TABLE_QUERIES = {
    "runs":"SELECT * FROM runs ORDER BY id",
    "search_results":"SELECT * FROM search_results ORDER BY id",
    "pages":"SELECT * FROM pages ORDER BY id",
    "repo_documents":"SELECT * FROM repo_documents ORDER BY id",
    "feed_sources":"SELECT * FROM feed_sources ORDER BY id",
    "feed_items":"SELECT * FROM feed_items ORDER BY id",
    "project_items":"SELECT * FROM project_items ORDER BY id",
    "engine_runs":"SELECT * FROM engine_runs ORDER BY id",
}
FTS_CHECKS = [
    "INSERT INTO pages_fts(pages_fts,rank) VALUES('integrity-check',1)",
    "INSERT INTO repo_documents_fts(repo_documents_fts,rank) VALUES('integrity-check',1)",
    "INSERT INTO feed_items_fts(feed_items_fts,rank) VALUES('integrity-check',1)",
    "INSERT INTO project_items_fts(project_items_fts,rank) VALUES('integrity-check',1)",
]
FTS_MATCHES = [
    "SELECT rowid FROM pages_fts WHERE pages_fts MATCH 'evidence' ORDER BY rowid",
    "SELECT rowid FROM repo_documents_fts WHERE repo_documents_fts MATCH 'evidence' ORDER BY rowid",
    "SELECT rowid FROM feed_items_fts WHERE feed_items_fts MATCH 'evidence' ORDER BY rowid",
    "SELECT rowid FROM project_items_fts WHERE project_items_fts MATCH 'old' ORDER BY rowid",
]


def state(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        tables = {name:[dict(r) for r in conn.execute(sql)] for name,sql in TABLE_QUERIES.items()}
        assert all(tables.values()), "all eight user tables must stay populated"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        for sql in FTS_CHECKS:
            conn.execute(sql)
        matches = [[tuple(r) for r in conn.execute(sql)] for sql in FTS_MATCHES]
        assert all(matches), "every seeded FTS MATCH must have a positive control"
        schema = [tuple(r) for r in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")]
        return dict(tables=tables,schema=schema,version=conn.execute("PRAGMA user_version").fetchone()[0],matches=matches)


class StorageFixture(unittest.TestCase):
    comparisons = 0
    faults = 0

    def compare(self,case,abort=False):
        outputs,states = [],[]
        with tempfile.TemporaryDirectory(prefix="kwr-collect-storage-") as tmp:
            for native in [False,True]:
                root = Path(tmp)/("native" if native else "python")
                root.mkdir()
                selected = root/"日本語 selected.sqlite"
                other = root/"unselected.sqlite"
                seed.ReaderFixture.seed(self,selected,"https://fixture.test/old")
                seed.ReaderFixture.seed(self,other,"https://fixture.test/unselected")
                before = state(selected)
                untouched = preservation.snapshot(other)
                if native:
                    env = {"PATH":os.environ.get("PATH",""),"KWR_ARCHIVE":str(other),
                           "KWR_HTTP_TIMEOUT_SECONDS":"invalid","KWR_META_PROVIDERS":"invalid"}
                    proc = subprocess.run([str(PROBE)],input=json.dumps(dict(archive=str(selected),calls=case["calls"],abort_later=abort)),
                                          env=env,cwd=root,capture_output=True,text=True,timeout=10)
                    self.assertEqual(proc.returncode,1 if abort else 0,(case["name"],proc.stderr))
                    if abort:
                        self.assertEqual(proc.stdout,"")
                    else:
                        self.assertEqual(proc.stderr,"")
                        outputs.append(json.loads(proc.stdout))
                else:
                    ids=[]
                    error=None
                    for call in case["calls"]:
                        archive = Archive(selected)
                        try:
                            if abort:
                                archive.conn.execute("CREATE TEMP TRIGGER fail_later_result BEFORE INSERT ON search_results WHEN new.rank=3 BEGIN SELECT RAISE(ABORT,'owned fixture'); END;")
                            with patch("katala_web_research.archive.utc_now_iso",lambda:"2026-01-01T00:00:00+00:00"):
                                ids.append(archive.store_run(call["query"],call["provider"],[SearchResult(**r) for r in call["results"]]))
                        except sqlite3.IntegrityError as exc:
                            error=exc
                            break
                        finally:
                            archive.close()
                    self.assertEqual(error is not None,abort)
                    if not abort:
                        outputs.append(dict(run_ids=ids))
                after = state(selected)
                self.assertEqual(before["schema"],after["schema"])
                self.assertEqual(before["version"],after["version"])
                self.assertEqual(before["matches"],after["matches"])
                committed = case["calls"][:-1] if abort else case["calls"]
                self.assertEqual(len(after["tables"]["runs"]),len(before["tables"]["runs"])+len(committed))
                self.assertEqual(len(after["tables"]["search_results"]),len(before["tables"]["search_results"])+sum(len(c["results"]) for c in committed))
                for name in ["runs","search_results"]:
                    self.assertEqual(after["tables"][name][:len(before["tables"][name])],before["tables"][name])
                for name in ["pages","repo_documents","feed_sources","feed_items","project_items","engine_runs"]:
                    self.assertEqual(before["tables"][name],after["tables"][name],(case["name"],name))
                self.assertEqual(untouched,preservation.snapshot(other))
                self.assertFalse((root/".katala-web-research").exists())
                states.append(after)
            self.assertEqual(*states,case["name"])
            if not abort:
                self.assertEqual(*outputs,case["name"])
                type(self).comparisons += 1
            else:
                type(self).faults += 1

    def test_all_reference_sequences_on_populated_copies(self):
        for case in CASES:
            self.compare(case)

    def test_partial_result_batch_failure_keeps_committed_earlier_run(self):
        rows=CASES[1]["calls"][0]["results"]
        self.compare(dict(name="first-batch-abort",calls=[dict(query="failed",provider="feed",results=[rows[0]|{"rank":2},rows[0]|{"rank":3}])]),abort=True)
        self.compare(dict(name="later-batch-abort",calls=[dict(query="success",provider="feed",results=rows),dict(query="failed",provider="feed",results=[rows[0]|{"rank":2},rows[0]|{"rank":3}])]),abort=True)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(StorageFixture))
    print("Store_run paired populated-copy sequences:",StorageFixture.comparisons,"paired SQL-abort sequences:",StorageFixture.faults)
    raise SystemExit(not result.wasSuccessful())

#!/usr/bin/env python3
"""Paired direct reader CLI/cache using loopback and eight populated synthetic tables."""
import contextlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import http_differential as fixture
import json_provider_differential as preservation
import meta_differential as seeded
from katala_web_research.archive import Archive
from katala_web_research.models import PageSnapshot
TRACE=[];STARTED=threading.Event();RELEASE=threading.Event()
class Handler(fixture.Handler):
    def do_GET(self):
        TRACE.append((self.path,{k.lower():v for k,v in self.headers.items()}))
        status=200;headers={'Content-Type':'text/plain; charset=utf-8'};body='  日本語 &amp; evidence\n second  '.encode()
        if self.path in ['/html','/redirect-target']:
            body=b'<html><title>Fixture &amp; title</title><p>atomic <b>evidence</b></p><script>hidden</script></html>';headers={'Content-Type':'text/html'}
        elif self.path=='/sjis-meta':body='<html><meta charset="shift_jis"><title>日本語</title><p>本文</p></html>'.encode('shift_jis');headers={'Content-Type':'text/html'}
        elif self.path=='/latin':body='Café £'.encode('latin1');headers={'Content-Type':'text/plain; charset=iso-8859-1'}
        elif self.path=='/redirect':status=302;headers['Location']='/redirect-target';body=b''
        elif self.path=='/empty':body=b''
        elif self.path=='/503':status=503;body=b'public synthetic error body'
        elif self.path=='/held':STARTED.set();RELEASE.wait(3)
        self.send_response(status)
        for k,v in headers.items():self.send_header(k,v)
        self.send_header('Content-Length',str(len(body)));self.end_headers()
        with contextlib.suppress(BrokenPipeError,ConnectionResetError):self.wfile.write(body)
        self.close_connection=True

def untimed(value):
    if isinstance(value,list):return [untimed(v) for v in value]
    if not isinstance(value,dict):return value
    out=dict(value)
    if 'fetched_at' in out:
        assert out['fetched_at']=='fixed' or re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00',out['fetched_at']),out
        if out['fetched_at']!='fixed':out['fetched_at']='<fixture-time>'
    return out

def state(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory=sqlite3.Row
        unrelated={name:[dict(r) for r in conn.execute(query)] for name,query in [
          ('runs','SELECT * FROM runs ORDER BY id'),('search_results','SELECT * FROM search_results ORDER BY id'),
          ('repos','SELECT * FROM repo_documents ORDER BY id'),('feed_sources','SELECT * FROM feed_sources ORDER BY url'),
          ('feed_items','SELECT * FROM feed_items ORDER BY id'),('projects','SELECT * FROM project_items ORDER BY id'),('engines','SELECT * FROM engine_runs ORDER BY id')]}
        assert all(unrelated.values()),'seed must populate every unrelated table'
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        schema=[tuple(r) for r in conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        pages=untimed([dict(r) for r in conn.execute('SELECT * FROM pages ORDER BY id')])
        conn.execute("INSERT INTO pages_fts(pages_fts,rank) VALUES('integrity-check',1)")
        fts=[tuple(r) for r in conn.execute('SELECT rowid,title,content FROM pages_fts ORDER BY rowid')]
        matches={term:[tuple(r) for r in conn.execute('SELECT rowid,title,content FROM pages_fts WHERE pages_fts MATCH ? ORDER BY rowid',(term,))] for term in ['old','atomic','evidence','本文','Café']}
        return unrelated,schema,conn.execute('PRAGMA user_version').fetchone()[0],pages,fts,matches

class ReaderFixture(fixture.Fixtures):
    comparisons=0;signal_executions=0
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,'Handler',Handler):super().setUpClass()
    def seed(self,path,url):
        with patch("katala_web_research.archive.utc_now_iso",lambda:"2026-01-01T00:00:00+00:00"):
            seeded.MetaFixture.seed(self,path)
        a=Archive(path);a.upsert_page(PageSnapshot(url,'old title','old evidence 日本語','cached','fixed',200,'text/plain'));a.close()
    def compare(self,route='/plain',options=None,cached=False,fail=False):
        options=options if options is not None else ['--json'];values=[];states=[];traces=[]
        with tempfile.TemporaryDirectory(prefix='kwr-reader-') as tmp:
            for native in [False,True]:
                root=Path(tmp)/('native' if native else 'python');root.mkdir();db=root/'日本語 selected.sqlite';other=root/'unselected.sqlite'
                url=self.origin+route;self.seed(db,url if cached else self.origin+'/old');self.seed(other,self.origin+'/other')
                before=state(db);other_before=preservation.snapshot(other);env=dict(self.env,KWR_ARCHIVE=str(other))
                prefix=[str(fixture.BINARY)] if native else [sys.executable,'-m','katala_web_research.cli']
                start=len(TRACE);result=subprocess.run(prefix+['read',url,*([] if '--reader' in options else ['--reader','direct']),'--archive',str(db),*options],env=env,cwd=root,capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,1 if fail else 0,(native,route,options,result.stderr))
                after=state(db)
                if not fail and route=='/html' and '--cache' in options and (not cached or '--refresh' in options):
                    with sqlite3.connect(db) as conn:
                        self.assertEqual(conn.execute("SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'atomic' AND rowid IN (SELECT id FROM pages WHERE url=?)",(url,)).fetchone()[0],1)
                        self.assertEqual(conn.execute("SELECT count(*) FROM pages_fts WHERE pages_fts MATCH 'old' AND rowid IN (SELECT id FROM pages WHERE url=?)",(url,)).fetchone()[0],0)
                self.assertEqual(before[:3],after[:3]);self.assertEqual(other_before,preservation.snapshot(other));self.assertFalse((root/'.katala-web-research').exists())
                if fail or '--cache' not in options:self.assertEqual(before,after)
                if fail:
                    self.assertEqual(result.stdout,'')
                    if native:self.assertNotIn('public synthetic error body',result.stderr)
                else:
                    output=untimed(json.loads(result.stdout)) if '--json' in options else result.stdout
                    values.append((output,result.stderr))
                traces.append(TRACE[start:]);states.append(after)
            if not fail:self.assertEqual(*values)
            self.assertEqual(*states);self.assertEqual(*traces)
            for _,headers in traces[0]:
                self.assertEqual(headers['accept'],'text/html, text/plain;q=0.9, */*;q=0.5');self.assertNotIn('authorization',headers)
            type(self).comparisons+=1
    def test_uncached_and_cache_miss_refresh(self):
        for route in ['/plain','/html','/sjis-meta','/latin','/redirect','/empty']:
            for opts in [['--json'],[],['--cache','--json'],['--cache'],['--cache','--refresh','--json'],['--refresh','--json']]:self.compare(route,opts)
    def test_cache_hit_and_refresh_failure(self):
        for opts in [['--cache','--json'],['--cache'],['--cache','--reader','jina','--json']]:self.compare('/503',opts,cached=True)
        for opts in [['--json'],['--cache','--refresh','--json']]:self.compare('/503',opts,cached=True,fail=True)
        self.compare('/503',['--cache','--json'],cached=False,fail=True)
    def test_cache_miss_refresh_inverted_index(self):
        self.compare('/html',['--cache','--json'])
        self.compare('/html',['--cache','--refresh','--json'],cached=True)
    def test_state_rejects_corrupt_inverted_index(self):
        with tempfile.TemporaryDirectory(prefix="kwr-reader-fts-") as tmp:
            db=Path(tmp)/"owned.sqlite";url=self.origin+"/old";self.seed(db,url)
            with sqlite3.connect(db) as conn:
                row=conn.execute("SELECT id,title,content FROM pages WHERE url=?",(url,)).fetchone()
                conn.execute("INSERT INTO pages_fts(pages_fts,rowid,title,content) VALUES('delete',?,?,?)",row)
                # External-content SELECT still sees the original page, although
                # this owned inverted index entry has been removed.
                self.assertEqual(conn.execute("SELECT content FROM pages_fts WHERE rowid=?",(row[0],)).fetchone()[0],row[2])
            with self.assertRaises(sqlite3.DatabaseError):state(db)
    def test_owned_worker_time_interrupt(self):
        for native in [False,True]:
            with tempfile.TemporaryDirectory(prefix='kwr-reader-signal-') as tmp:
                root=Path(tmp);db=root/'selected.sqlite';self.seed(db,self.origin+'/held');before=state(db)
                STARTED.clear();RELEASE.clear();prefix=[str(fixture.BINARY)] if native else [sys.executable,'-m','katala_web_research.cli']
                child=subprocess.Popen(prefix+['read',self.origin+'/held','--reader','direct','--cache','--refresh','--archive',str(db),'--json'],env=self.env,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
                try:
                    self.assertTrue(STARTED.wait(3),'owned request not started');os.killpg(child.pid,signal.SIGINT);stdout,stderr=child.communicate(timeout=3)
                    self.assertEqual(child.returncode,-signal.SIGINT);self.assertEqual(stdout,'');self.assertEqual(before,state(db));type(self).signal_executions+=1
                finally:
                    RELEASE.set()
                    if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.communicate(timeout=3)
if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReaderFixture)
    # Base HTTP tests are inherited helper implementation, not a rerun target.
    available={'test_uncached_and_cache_miss_refresh','test_cache_hit_and_refresh_failure','test_owned_worker_time_interrupt','test_state_rejects_corrupt_inverted_index','test_cache_miss_refresh_inverted_index'}
    wanted=set(sys.argv[1:]) or available;assert wanted <= available,'unknown fixture method'
    suite=unittest.TestSuite(test for test in suite if test._testMethodName in wanted)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print('Direct reader paired CLI cases:',ReaderFixture.comparisons,'owned signal executions:',ReaderFixture.signal_executions)
    sys.exit(not result.wasSuccessful())

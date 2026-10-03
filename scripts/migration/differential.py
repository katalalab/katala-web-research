#!/usr/bin/env python3
"""Offline CLI parity against the retained Python reference; only synthetic archives."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from katala_web_research.archive import Archive
from katala_web_research.models import FeedItem, FeedSource, PageSnapshot, ProjectItem, RepoDocument

ROOT = Path(__file__).resolve().parents[2]
RUST = Path(os.environ.get('KWR_RUST_BINARY', ROOT / 'target/debug/kwr-rs'))

class Differential(unittest.TestCase):
    comparisons = 0
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='kwr-parity-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / '日本語 fixture.sqlite'
        self.env = {k:v for k,v in os.environ.items() if not k.startswith(('KWR_', 'OPENALEX_', 'BRAVE_', 'JINA_', 'GITHUB_'))}
        self.env['PYTHONPATH'] = str(ROOT / 'src')
        self.seed()
    def seed(self):
        a = Archive(self.db)
        for i in range(3):
            a.upsert_page(PageSnapshot(f'https://example.test/{i}', f'evidence {i} 日本語', f'atomic evidence {i} rollback UTF-8 ©', 'fixture', '2026-01-01T00:00:00+00:00', 200, 'text/plain'))
            a.upsert_repo_document(RepoDocument('/synthetic', 'sample', f'docs/test_{i}%.md', f'evidence {i}', 'atomic evidence rollback', 'docs', 'fixed', context=f'contextterm {i}'))
        a.upsert_feed_source(FeedSource('https://example.test/feed', 'Original title', 'rss', 'fixed', 'fixed', 'ok', 1.0, '', 2))
        a.upsert_feed_items([FeedItem('https://example.test/feed', 'https://example.test/article', '日本語 evidence', 'atomic evidence rollback', 'Fixture feed', None, 'fixed')])
        a.upsert_project_items([ProjectItem('issue', 'fixture/example', 1, 'atomic evidence 日本語', 'https://example.test/issues/1', 'open', 'fixed', ['priority/p0', 'status:blocked'], 'p0', 'status:blocked')])
        a.record_engine_runs([{'provider':'ddg','status':'error','latency_ms':6000,'result_count':0,'error_kind':'FetchError'}] * 6)
        a.record_engine_runs([{'provider':'github','status':'ok','latency_ms':300,'result_count':2,'error_kind':''}] * 3)
        a.close()
    def call(self, cmd, rust):
        prefix = [str(RUST)] if rust else [sys.executable, '-m', 'katala_web_research.cli']
        return subprocess.run(prefix + cmd, cwd=self.root, env=self.env, capture_output=True, text=True, encoding='utf-8', timeout=15)
    def parity(self, cmd, as_json=True):
        p, r = self.call(cmd, False), self.call(cmd, True)
        self.assertEqual(p.returncode, r.returncode, (cmd, p.stderr, r.stderr))
        if as_json:
            self.assertEqual(json.loads(p.stdout), json.loads(r.stdout), cmd)
        else:
            self.assertEqual(p.stdout, r.stdout, cmd)
        self.assertEqual(p.stderr, r.stderr, cmd)
        type(self).comparisons += 1
    def test_plan(self):
        for query in ['', ' \t ', 'agent research', '日本語\u3000query ©', 'agent 2026', 'atomic\x1cevidence']:
            for maximum in [-1,0,1,2,4,8]:
                self.parity(['plan',query,'--max-subqueries',str(maximum),'--year','2026','--json'])
        self.parity(['plan',' research   query ','--year','2026'],False)
        self.parity(['--version'],False)
    def test_registry(self):
        for args in [[], ['--domain','security'], ['--domain','news','--query-type','media_bias'], ['--domain','missing'], ['--limit','0'], ['--limit','-1'], ['--limit','1000'], ['--domain','']]:
            self.parity(['sources','list',*args,'--json'])
        for url in ['https://www.cisa.gov/known-exploited-vulnerabilities-catalog', 'www.cisa.gov/known-exploited-vulnerabilities-catalog', 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog/details', 'https://www.cisa.gov/known-exploited-vulnerabilities-catalogue', 'https://evil.cisa.gov/', 'https://example.test/', 'invalid', 'https://www.cisa.gov:443/known-exploited-vulnerabilities-catalog', 'https://www.cisa.gov/a/../known-exploited-vulnerabilities-catalog', 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog;session=abc', 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog\n', '\n https://www.cisa.gov/known-exploited-vulnerabilities-catalog\t', 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog;session=abc/details', ' www.cisa.gov/known-exploited-vulnerabilities-catalog']:
            self.parity(['sources','match',url,'--json'])
        self.parity(['sources','list','--domain','security'],False)
        self.parity(['sources','match','https://example.test'],False)
        self.parity(['sources','match','https://www.cisa.gov/known-exploited-vulnerabilities-catalog'],False)
    def test_overlay(self):
        overlay = self.root / 'overlay.json'
        raw = json.loads((ROOT/'src/katala_web_research/data/source_registry.json').read_text())
        entry = raw['sources'][0]; entry['trust_score']=1; entry['best_for']='local fixture'
        raw['sources']=[entry,dict(name='Synthetic',domain='test',source_type='docs',url='https://fixture.test',hosts=['WWW.FIXTURE.TEST'])]
        overlay.write_text(json.dumps(raw),encoding='utf-8')
        self.env['KWR_SOURCE_REGISTRY_OVERLAY']=str(overlay)
        self.parity(['sources','list','--limit','1000','--json'])
        self.parity(['sources','match','https://www.fixture.test','--json'])
        overlay.write_text('{}',encoding='utf-8')
        self.parity(['sources','list','--limit','1000','--json'])
    def test_archive_queries(self):
        for command in [['query'],['repos','query'],['feeds','query'],['issues','query']]:
            for terms in ['evidence','rollback','日本語','atomic evidence','"evidence"','','OR NOT * :','missing']:
                self.parity([*command,terms,'--archive',str(self.db),'--json'])
            self.parity([*command,'evidence','--archive',str(self.db)],False)
            for limit in [-1,0,1]:
                self.parity([*command,'evidence','--limit',str(limit),'--archive',str(self.db),'--json'])
        for terms, options in [('repo:sample path:docs/ evidence',[]), ('repo:missing evidence',['--repo','sample']), ('contextterm',['--path','test_0%']), ('evidence',['--path','%']), ('repo:sample path:docs/',[])]:
            self.parity(['repos','query',terms,*options,'--archive',str(self.db),'--json'])
    def test_cache_and_health(self):
        self.parity(['read','https://example.test/0','--cache','--archive',str(self.db),'--json'])
        self.parity(['read','https://example.test/0','--cache','--archive',str(self.db)],False)
        for window in [-1,0,1,5,50]:
            self.parity(['engines','--window',str(window),'--archive',str(self.db),'--json'])
        self.parity(['engines','--archive',str(self.db)],False)
    def test_engine_decimal_rounding_regression(self):
        a=Archive(self.db)
        a.record_engine_runs([{'provider':'rounding','status':'ok','latency_ms':10,'result_count':1,'error_kind':''}]+[{'provider':'rounding','status':'ok','latency_ms':10,'result_count':0,'error_kind':''}]*7)
        a.close()
        self.parity(['engines','--archive',str(self.db),'--json'])
        rows=json.loads(self.call(['engines','--archive',str(self.db),'--json'],True).stdout)
        self.assertEqual(next(r['health_score'] for r in rows if r['provider']=='rounding'),0.6937)

    def test_feed_write(self):
        # Separate copies prevent one implementation's timestamp/write from contaminating the other's baseline.
        for title in ['', 'Updated title 日本語']:
            p_db, r_db = self.root/'python.sqlite', self.root/'rust.sqlite'
            with sqlite3.connect(self.db) as source:
                for path in [p_db,r_db]:
                    with sqlite3.connect(path) as target: source.backup(target)
            p=self.call(['feeds','add','https://example.test/feed','--title',title,'--archive',str(p_db),'--json'],False)
            r=self.call(['feeds','add','https://example.test/feed','--title',title,'--archive',str(r_db),'--json'],True)
            self.assertEqual(p.returncode,r.returncode,(p.stderr,r.stderr))
            pv,rv=json.loads(p.stdout),json.loads(r.stdout); pv['archive']=rv['archive']='<copy>'
            self.assertEqual(pv,rv)
            with sqlite3.connect(p_db) as pc, sqlite3.connect(r_db) as rc:
                self.assertEqual(pc.execute('SELECT * FROM feed_sources').fetchall(),rc.execute('SELECT * FROM feed_sources').fetchall())
            type(self).comparisons += 1
    def test_migration_cli_roundtrip(self):
        before = self.db.read_bytes()
        destination = self.root / 'native-copy.sqlite'
        dry = self.call(['migrate','--source',str(self.db),'--destination',str(destination),'--dry-run'],True)
        self.assertEqual(dry.returncode,0,dry.stderr)
        self.assertTrue(json.loads(dry.stdout)['source_unchanged'])
        self.assertFalse(destination.exists())
        migrated = self.call(['migrate','--source',str(self.db),'--destination',str(destination)],True)
        self.assertEqual(migrated.returncode,0,migrated.stderr)
        self.assertEqual(json.loads(migrated.stdout)['after']['user_version'],1)
        self.assertEqual(before,self.db.read_bytes())
        for cmd in [['query'],['repos','query'],['feeds','query'],['issues','query']]:
            original=self.call([*cmd,'evidence','--archive',str(self.db),'--json'],False)
            native=self.call([*cmd,'evidence','--archive',str(destination),'--json'],True)
            rollback=self.call([*cmd,'evidence','--archive',str(destination),'--json'],False)
            self.assertEqual(original.returncode,native.returncode)
            self.assertEqual(original.returncode,rollback.returncode)
            self.assertEqual(json.loads(original.stdout),json.loads(native.stdout))
            self.assertEqual(json.loads(original.stdout),json.loads(rollback.stdout))
            type(self).comparisons += 1

    def test_feed_refresh_search_and_repeated_refresh(self):
        fixture = self.root/'feed 日本語.rss'
        fixture.write_text((ROOT/'tests/fixtures/sample.rss.xml').read_text(),encoding='utf-8')
        source=fixture.as_uri()
        for rust,name in [(False,'python'),(True,'rust')]:
            archive=self.root/(name+'-refresh.sqlite')
            a=Archive(archive); a.upsert_feed_source(FeedSource(source,'Manual title','', 'fixed')); a.close()
        def clean(value):
            if isinstance(value,dict):
                return {k: ('<time>' if k in ['added_at','last_fetched_at','fetched_at'] and v else '<archive>' if k=='archive' else clean(v)) for k,v in value.items()}
            if isinstance(value,list):return [clean(v) for v in value]
            return value
        for round in range(2):
            outputs=[]
            for rust,name in [(False,'python'),(True,'rust')]:
                archive=self.root/(name+'-refresh.sqlite')
                p=self.call(['feeds','refresh','--archive',str(archive),'--json'],rust)
                self.assertEqual(p.returncode,0,p.stderr);outputs.append(clean(json.loads(p.stdout)))
            self.assertEqual(*outputs);type(self).comparisons+=1
        for query in ['RSSHub adapter','design','missing']:
            for limit in [-1,0,1,5]:
                outputs=[]
                for rust,name in [(False,'python'),(True,'rust')]:
                    archive=self.root/(name+'-refresh.sqlite')
                    p=self.call(['search',query,'--provider','feed','--archive',str(archive),'--limit',str(limit),'--json'],rust)
                    self.assertEqual(p.returncode,0,p.stderr);outputs.append(clean(json.loads(p.stdout)))
                self.assertEqual(*outputs,(query,limit));type(self).comparisons+=1
        # Repeat with malformed XML: error_kind and previous source metadata must match.
        fixture.write_text('<rss><broken>',encoding='utf-8')
        outputs=[]
        for rust,name in [(False,'python'),(True,'rust')]:
            p=self.call(['feeds','refresh','--archive',str(self.root/(name+'-refresh.sqlite')),'--json'],rust)
            self.assertEqual(p.returncode,0,p.stderr);outputs.append(clean(json.loads(p.stdout)))
        self.assertEqual(*outputs);type(self).comparisons+=1
    def test_local_feed_formats_selection_and_failure_state(self):
        def clean(value):
            if isinstance(value,dict):
                return {k: ('<time>' if k in ['added_at','last_fetched_at','fetched_at'] and v else '<archive>' if k=='archive' else clean(v)) for k,v in value.items()}
            if isinstance(value,list):return [clean(v) for v in value]
            return value
        for filename in ['sample.rss.xml','sample.atom.xml','sample.feed.json','comparison.feed.json']:
            fixture=self.root/('文書 '+filename)
            if filename == 'comparison.feed.json':
                fixture.write_text(json.dumps({'items':[{'url':'https://example.test/math','title':'Comparison','content_text':'Conditions: x < y > z, then continue.'}]}),encoding='utf-8')
            else:
                fixture.write_bytes((ROOT/'tests/fixtures'/filename).read_bytes())
            paths=[self.root/(name+filename+'.sqlite') for name in ['python','rust']]
            def compare(args):
                outputs=[]
                for rust,path in zip([False,True],paths):
                    proc=self.call([*args,'--archive',str(path),'--json'],rust)
                    self.assertEqual(proc.returncode,0,proc.stderr)
                    self.assertEqual(proc.stderr,'')
                    outputs.append(clean(json.loads(proc.stdout)))
                self.assertEqual(*outputs,(filename,args));type(self).comparisons+=1
            compare(['feeds','refresh']) # no registered sources
            compare(['feeds','refresh','--source',fixture.as_uri()])
            compare(['feeds','refresh','--source','']) # empty source means refresh registry
            compare(['feeds','query','feed'])
            for path in paths:
                with sqlite3.connect(path) as conn:
                    self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(),('ok',))
            fixture.write_text('{invalid}',encoding='utf-8')
            compare(['feeds','refresh'])
            fixture.unlink()
            compare(['feeds','refresh'])
            # Parse/fetch failure retains all old items and source identity.
            sources=[];items=[]
            for path in paths:
                with sqlite3.connect(path) as conn:
                    conn.row_factory=sqlite3.Row
                    sources.append(clean([dict(r) for r in conn.execute('SELECT * FROM feed_sources ORDER BY url')]))
                    items.append(clean([dict(r) for r in conn.execute('SELECT * FROM feed_items ORDER BY source_url,url')]))
            self.assertEqual(*sources);self.assertEqual(*items);self.assertTrue(items[0])
    def test_unsupported_feed_scheme_is_explicit_and_preserves_health(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE feed_sources SET url='ftp://example.test/feed'")
            before=conn.execute('SELECT * FROM feed_sources').fetchall()
        proc=self.call(['feeds','refresh','--archive',str(self.db),'--json'],True)
        self.assertEqual(proc.returncode,1)
        self.assertIn('feed scheme ftp not migrated yet',proc.stderr)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(before,conn.execute('SELECT * FROM feed_sources').fetchall())
        proc=self.call(['search','evidence','--provider','feed','--enrich-top','1','--archive',str(self.db),'--json'],True)
        self.assertEqual(proc.returncode,1)
        self.assertIn('derived-target enrichment is disabled',proc.stderr)

    def test_feed_search_highlights(self):
        for i, url in enumerate(['https://github.com/fixture/repo','https://www.cisa.gov/known-exploited-vulnerabilities-catalog','https://arxiv.org/abs/fixture','https://example.test/0']):
            a=Archive(self.db)
            a.upsert_feed_items([FeedItem('https://example.test/feed',url,'atomic evidence','atomic evidence rollback','Fixture feed',None,'fixed')]);a.close()
        for top in [-1,0,1,5]:
            self.parity(['search','atomic evidence','--provider','feed','--archive',str(self.db),'--highlight-top',str(top),'--json'])
        self.parity(['search','atomic evidence','--provider','feed','--archive',str(self.db)],False)
        for limit in [-2,-1,0,1,3,10]:
            for multiplier in [0,1,1.00001,2.1,3]:
                self.parity(['search','atomic evidence','--provider','feed','--archive',str(self.db),'--limit',str(limit),'--candidate-multiplier',str(multiplier),'--json'])
        for args in [['--category','github'],['--category','research','--category','pdf'],['--include-domain','https://WWW.example.test/path','--exclude-domain','other.test'],['--enrich-top','-1'],['--highlight-top','2']]:
            self.parity(['search','atomic evidence','--provider','feed','--archive',str(self.db),*args,'--json'])

    def test_parser_and_runtime_exit_codes(self):
        for args in [[], ['plan'], ['sources','missing'], ['query','evidence','--limit','invalid']]:
            self.assertEqual(self.call(args,False).returncode,self.call(args,True).returncode)
            type(self).comparisons += 1
        invalid=self.root/'invalid.sqlite'; invalid.write_text('synthetic invalid database')
        for rust in [False,True]:
            p=self.call(['query','evidence','--archive',str(invalid),'--json'],rust)
            self.assertEqual(p.returncode,1); self.assertTrue(p.stderr.startswith('kwr: error:'))
        type(self).comparisons += 1

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Differential)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f'offline CLI comparisons: {Differential.comparisons}')
    raise SystemExit(not result.wasSuccessful())

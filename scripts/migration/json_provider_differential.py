#!/usr/bin/env python3
"""Individual JSON provider CLI traces over loopback; never a paid/live endpoint."""
import json
import select
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
import http_differential as fixture
from katala_web_research.archive import Archive
from katala_web_research.models import PageSnapshot,FeedSource,FeedItem
from katala_web_research.http import DEFAULT_USER_AGENT

REQUESTS=[]
PUBLIC_KEY='public-fixture-key'
def items(provider,page):
    rows=[]
    for i in range(20):
        n=(page-1)*20+i
        row={'url':f'https://fixture{n}.test/item','title':f'alpha 日本語 {n}'}
        if n==0:row['url']='https://docs.python.org/3/library/urllib.html'
        if n==1:row['title']=None
        text='retracted=true' if n==2 else 'alpha 日本語 内容'
        if provider=='searxng':row.update(content=text,publishedDate='2026-01-01')
        elif provider=='brave':row.update(description=text,age='2025-02-01')
        else:row.update(description=text,publishedTime='2026-01-01')
        rows.append(row)
    return rows
class JsonHandler(fixture.Handler):
    def do_GET(self):
        parsed=urlsplit(self.path);params=parse_qs(parsed.query);q=params.get('q',[''])[0]
        if parsed.path=='/search':provider='searxng';page=int(params.get('pageno',['1'])[0])
        elif parsed.path=='/res/v1/web/search':provider='brave';page=int(params.get('offset',['0'])[0])+1
        elif parsed.path=='/':provider='jina';page=1
        else:self.send_error(404);return
        headers={k.lower():v for k,v in self.headers.items()}
        REQUESTS.append((provider,self.path,headers))
        rows=items(provider,page)
        if q=='fixture-empty' or (q=='fixture-empty-second' and page>1):rows=[]
        payload={'results':rows} if provider=='searxng' else {'web':{'results':rows}} if provider=='brave' else {'data':rows}
        body=json.dumps(payload,ensure_ascii=False).encode();status=200
        if q=='fixture-error' or (q=='fixture-later-error' and page>1):status=503;body=(PUBLIC_KEY+' public error body').encode()
        if q=='fixture-json-error' or (q=='fixture-later-json' and page>1):body=(PUBLIC_KEY+' public non-JSON body').encode()
        if q=='fixture-slow':time.sleep(0.4)
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True
class JsonProxy(fixture.ProxyHandler):
    tls_port=0
    def do_CONNECT(self):
        if self.path not in {'api.search.brave.com:443','s.jina.ai:443'}:self.send_error(403);return
        # Map only the two synthetic fixture names to our TLS socket. Never
        # resolve/connect a remote hostname or forward an arbitrary target.
        upstream=socket.create_connection(('127.0.0.1',self.tls_port),timeout=2)
        self.send_response(200,'Connection established');self.end_headers()
        try:
            while True:
                ready,_,_=select.select([self.connection,upstream],[],[],3)
                if not ready:break
                for source in ready:
                    data=source.recv(8192)
                    if not data:return
                    (upstream if source is self.connection else self.connection).sendall(data)
        except OSError:pass
        finally:upstream.close();self.close_connection=True
def snapshot(path):
    with sqlite3.connect(path) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        return conn.execute('PRAGMA user_version').fetchone()[0],list(conn.iterdump())
class JsonFixture(fixture.TlsAndProxy):
    additional_san=',DNS:api.search.brave.com,DNS:s.jina.ai'
    comparisons={p:0 for p in ['searxng','brave','jina']}
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,'Handler',JsonHandler),patch.object(fixture,'ProxyHandler',JsonProxy):super().setUpClass()
        JsonProxy.tls_port=cls.servers[1].server_port
    def compare(self,provider,query='alpha 日本語 + * ~',options=None,extra=None,expected=0):
        options=options or ['--json'];extra=extra or {}
        with tempfile.TemporaryDirectory(prefix='kwr-json-provider-') as tmp:
            values=[];traces=[]
            for rust,name in [(False,'python'),(True,'rust')]:
                path=Path(tmp)/(name+'.sqlite');a=Archive(path)
                a.upsert_page(PageSnapshot('https://docs.python.org/3/library/urllib.html','Old title','alpha 日本語 evidence. More alpha evidence.','cached','fixed'))
                a.upsert_feed_source(FeedSource('https://fixture.test/feed','Old feed','rss','fixed'))
                a.upsert_feed_items([FeedItem('https://fixture.test/feed','https://fixture.test/old','Old item','must remain','Old feed',None,'fixed')]);a.close()
                before=snapshot(path)
                env=dict(self.env,HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),KWR_HTTP_TIMEOUT_SECONDS='0.15' if query=='fixture-slow' else '1',KWR_SEARXNG_URL=self.plain,BRAVE_SEARCH_API_KEY=PUBLIC_KEY,JINA_API_KEY=PUBLIC_KEY)
                # Avoid duplicate keyword collisions for explicit config overrides.
                env.update(extra)
                prefix=[str(fixture.BINARY)] if rust else [sys.executable,'-m','katala_web_research.cli']
                start=len(REQUESTS)
                result=subprocess.run(prefix+['search',query,'--provider',provider,*options,'--archive',str(path)],env=env,capture_output=True,text=True,timeout=10)
                trace=REQUESTS[start:];traces.append(trace)
                self.assertEqual(result.returncode,expected,(provider,query,result.stderr))
                self.assertEqual(before,snapshot(path),(provider,query,'archive changed'))
                if expected:
                    self.assertEqual(result.stdout,'')
                    if rust:self.assertNotIn(PUBLIC_KEY,result.stderr)
                    values.append((result.returncode,result.stdout))
                else:
                    self.assertEqual(result.stderr,'')
                    values.append(json.loads(result.stdout) if '--json' in options else result.stdout)
                for actual,_,headers in trace:
                    self.assertEqual(actual,provider);self.assertEqual(headers.get('accept'),'application/json')
                    self.assertEqual(headers.get('user-agent'),DEFAULT_USER_AGENT)
                    if provider=='brave':self.assertEqual(headers.get('x-subscription-token'),PUBLIC_KEY)
                    elif provider=='jina':self.assertEqual(headers.get('authorization'),'Bearer '+PUBLIC_KEY)
                    else:self.assertNotIn('authorization',headers)
            self.assertEqual(*values,(provider,query,options,extra))
            self.assertEqual([(p,url,h.get('authorization'),h.get('x-subscription-token')) for p,url,h in traces[0]],[(p,url,h.get('authorization'),h.get('x-subscription-token')) for p,url,h in traces[1]],(provider,query))
            type(self).comparisons[provider]+=1
            return traces[1]
    def test_each_provider_query_options_rank_pagination_and_preservation(self):
        options=[['--json'],['--category','research','--json'],['--category','github','--category','pdf','--json'],['--include-domain','docs.python.org','--exclude-domain','other.test','--json'],['--highlight-top','3','--json'],['--enrich-top','-1','--json']]
        options += [['--limit',str(n),'--candidate-multiplier',str(m),'--json'] for n in [-1,0,1,21,41] for m in [1,2]]
        for provider in self.comparisons:
            for option in options:self.compare(provider,options=option)
            self.compare(provider,options=['--limit','2'])
            self.compare(provider,'fixture-empty')
    def test_each_provider_failures_redaction_and_preflight(self):
        for provider in self.comparisons:
            for query in ['fixture-error','fixture-json-error','fixture-slow']:
                trace=self.compare(provider,query,expected=1);self.assertEqual(len(trace),1)
            key={'searxng':'KWR_SEARXNG_URL','brave':'BRAVE_SEARCH_API_KEY','jina':'JINA_API_KEY'}[provider]
            self.assertEqual(self.compare(provider,extra={key:''},expected=1),[])
            if provider!='jina':
                for query in ['fixture-later-error','fixture-later-json']:
                    trace=self.compare(provider,query,options=['--limit','21','--candidate-multiplier','1','--json'],expected=1);self.assertEqual(len(trace),2)
                trace=self.compare(provider,'fixture-empty-second',options=['--limit','41','--candidate-multiplier','1','--json']);self.assertEqual(len(trace),2)
        self.assertEqual(self.compare('searxng',extra={'KWR_SEARXNG_TIME_RANGE':'forever'},expected=1),[])
        self.assertEqual(self.compare('brave',extra={'BRAVE_FRESHNESS':'invalid'},expected=1),[])
        self.compare('searxng',extra={'KWR_SEARXNG_CATEGORIES':'general,it','KWR_SEARXNG_LANGUAGE':'ja','KWR_SEARXNG_TIME_RANGE':'month','KWR_SEARXNG_SAFESEARCH':'1'})
        self.compare('brave',extra={'BRAVE_SEARCH_COUNTRY':'JP','BRAVE_SEARCH_LANG':'ja','BRAVE_UI_LANG':'ja-JP','BRAVE_FRESHNESS':'week','BRAVE_SAFESEARCH':'moderate'})
    test_downgrade_rejected=None
    test_http_proxy_and_environment_boundaries=None
    test_https_connect_proxy=None
    test_tls_trust_and_hostname=None
    test_trusted_tls_cli=None

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(JsonFixture))
    print('offline JSON provider CLI comparisons:',JsonFixture.comparisons)
    raise SystemExit(not result.wasSuccessful())

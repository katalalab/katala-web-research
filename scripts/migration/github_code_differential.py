#!/usr/bin/env python3
"""GitHub code CLI through exact loopback TLS mapping; synthetic token only."""
import json
import select
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
import http_differential as fixture
import json_provider_differential as normal
from katala_web_research.archive import Archive
from katala_web_research.models import PageSnapshot

TRACE=[];PUBLIC_KEY=normal.PUBLIC_KEY
class CodeHandler(fixture.Handler):
    def do_GET(self):
        parsed=urlsplit(self.path);params=parse_qs(parsed.query);q=params.get('q',[''])[0];page=int(params.get('page',['1'])[0])
        TRACE.append((self.path,{k.lower():v for k,v in self.headers.items()}))
        if parsed.path!='/search/code':self.send_error(404);return
        rows=[]
        for i in range(100):
            n=(page-1)*100+i
            rows.append({'html_url':f'https://github.com/fixture/repo/blob/main/item{n}.rs','path':f'src/日本語{n}.rs','name':f'file{n}.rs','repository':{'full_name':'fixture/repo','html_url':'https://github.com/fixture/repo','description':'alpha implementation','language':'Rust'},'text_matches':[{'object_type':'FileContent','property':'content','fragment':'retracted=true' if n==2 else 'alpha 日本語 context &amp; value'},{'object_type':'FileContent','property':'content','fragment':'more context'}]})
        if q=='fixture-empty' or (q=='fixture-empty-second' and page>1):rows=[]
        body=json.dumps({'items':rows},ensure_ascii=False).encode();status=200
        if q.startswith('fixture-status-'):status=int(q.rsplit('-',1)[1]);body=(PUBLIC_KEY+' status body').encode()
        if q.startswith('fixture-later-') and page>1:status=int(q.rsplit('-',1)[1]);body=(PUBLIC_KEY+' later status body').encode()
        if q=='fixture-json-error':body=(PUBLIC_KEY+' non-JSON body').encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True
class CodeProxy(normal.JsonProxy):
    def do_CONNECT(self):
        if self.path!='api.github.com:443':self.send_error(403);return
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
class CodeFixture(fixture.TlsAndProxy):
    additional_san=',DNS:api.github.com'
    comparisons=0
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,'Handler',CodeHandler),patch.object(fixture,'ProxyHandler',CodeProxy):super().setUpClass()
        CodeProxy.tls_port=cls.servers[1].server_port
    def compare(self,query='alpha 日本語 + * ~',options=None,extra=None,code=0):
        options=options or ['--json'];values=[];traces=[]
        with tempfile.TemporaryDirectory(prefix='kwr-github-code-') as tmp:
            for rust in [False,True]:
                path=Path(tmp)/('native.sqlite' if rust else 'python.sqlite');a=Archive(path)
                a.upsert_page(PageSnapshot('https://github.com/fixture/repo/blob/main/item0.rs','Old title','alpha 日本語 evidence. More context.','cached','fixed'));a.close();before=normal.snapshot(path)
                env=dict(self.env,HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),KWR_HTTP_TIMEOUT_SECONDS='1',GITHUB_TOKEN=PUBLIC_KEY);env.update(extra or {})
                prefix=[str(fixture.BINARY)] if rust else [sys.executable,'-m','katala_web_research.cli'];start=len(TRACE)
                result=subprocess.run(prefix+['search',query,'--provider','github_code',*options,'--archive',str(path)],env=env,capture_output=True,text=True,timeout=15)
                trace=TRACE[start:];traces.append(trace)
                self.assertEqual(result.returncode,code,(query,rust,result.stderr));self.assertEqual(before,normal.snapshot(path))
                if code:
                    self.assertEqual(result.stdout,'');values.append(None)
                    if rust:self.assertNotIn(PUBLIC_KEY,result.stderr)
                else:
                    self.assertEqual(result.stderr,'');values.append(json.loads(result.stdout) if '--json' in options else result.stdout)
                for _,headers in trace:
                    self.assertEqual(headers.get('authorization'),'Bearer '+PUBLIC_KEY);self.assertEqual(headers.get('accept'),'application/vnd.github.text-match+json');self.assertEqual(headers.get('x-github-api-version'),'2022-11-28')
            self.assertEqual(*values,(query,options,extra));self.assertEqual([p for p,_ in traces[0]],[p for p,_ in traces[1]]);type(self).comparisons+=1
            return traces[1]
    def test_requests_rank_options_highlights_and_paging(self):
        options=[['--json'],['--category','github','--json'],['--category','research','--category','pdf','--json'],['--include-domain','github.com','--exclude-domain','other.test','--json'],['--highlight-top','2','--json']]
        options += [['--limit',str(limit),'--candidate-multiplier',str(mult),'--json'] for limit in [-1,0,1,101] for mult in [1,2]]
        for option in options:self.compare(options=option)
        self.compare(options=['--limit','2'])
        self.compare('fixture-empty')
        self.assertEqual(len(self.compare(options=['--limit','1001','--candidate-multiplier','1','--json'])),10)
        self.compare(extra={'GITHUB_TOKEN':' \u001c '+PUBLIC_KEY+' \t'})
    def test_missing_keys_invalid_query_and_abort(self):
        for status in [401,403,422,503]:
            self.assertEqual(len(self.compare('fixture-status-'+str(status),code=0 if status==422 else 1)),1)
        self.assertEqual(len(self.compare('fixture-json-error',code=1)),1)
        for status in [422,503]:
            trace=self.compare('fixture-later-'+str(status),options=['--limit','101','--candidate-multiplier','1','--json'],code=0 if status==422 else 1);self.assertEqual(len(trace),2)
        self.assertEqual(len(self.compare('fixture-empty-second',options=['--limit','101','--candidate-multiplier','1','--json'])),2)
        for token in ['', ' \u001c ']:self.assertEqual(self.compare(extra={'GITHUB_TOKEN':token},code=1),[])
        self.assertEqual(self.compare(extra={'GITHUB_TOKEN':'','KWR_HTTP_TIMEOUT_SECONDS':'bad'},code=1),[])
    test_downgrade_rejected=None
    test_http_proxy_and_environment_boundaries=None
    test_https_connect_proxy=None
    test_tls_trust_and_hostname=None
    test_trusted_tls_cli=None
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CodeFixture))
    print('GitHub code localhost CLI comparisons:',CodeFixture.comparisons)
    raise SystemExit(not result.wasSuccessful())

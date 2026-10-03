#!/usr/bin/env python3
"""Synthetic op executable, eight-table archives, exact loopback OpenAlex mapping."""
import json
import os
import select
import shutil
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
import github_code_differential as code
from katala_web_research.archive import Archive
from katala_web_research.models import PageSnapshot
PROCESS=Path(os.environ.get('KWR_PROCESS_FIXTURE',fixture.ROOT/'target/debug/examples/process_fixture'));TRACE=[]
def item(n):
    return {'id':f'https://openalex.org/W{n}','display_name':f'alpha 日本語 work {n}','doi':f'https://doi.org/10.1/fixture{n}','publication_date':'2026-01-02','publication_year':2026,'type':'article','cited_by_count':n,'is_retracted':n==2,'abstract_inverted_index':{'alpha':[0],'日本語':[1],'evidence':[2]},'primary_location':{'landing_page_url':f'https://arxiv.org/abs/fixture{n}','pdf_url':f'https://fixture.test/paper{n}.pdf','is_oa':True,'license':'cc-by','source':{'id':'https://openalex.org/S1','display_name':'Fixture journal','type':'journal'}},'open_access':{'is_oa':True,'oa_status':'gold'},'content_urls':{'pdf':f'https://content.openalex.org/works/W{n}.pdf'}}
class OpenAlexHandler(fixture.Handler):
    def do_GET(self):
        parsed=urlsplit(self.path);params=parse_qs(parsed.query);TRACE.append((self.path,{k.lower():v for k,v in self.headers.items()}))
        if parsed.path!='/works':self.send_error(404);return
        query=params.get('search',[''])[0];cursor=params.get('cursor',['*'])[0];count=int(params.get('per_page',['10'])[0]);start=0 if cursor=='*' else 100 if cursor=='page2' else 2
        if query.startswith('fixture-later-'):count=min(count,2)
        rows=[item(start+i) for i in range(count)];status=200;headers={};next_cursor='page2' if count==100 else 'same-cursor' if query.startswith('fixture-later-') and cursor=='*' else None
        if query=='fixture-empty' or (query=='fixture-later-empty' and cursor!='*'):rows=[];next_cursor=None
        body=json.dumps({'results':rows,'meta':{'next_cursor':next_cursor}},ensure_ascii=False).encode()
        if query.startswith('fixture-status-') or (query.startswith('fixture-later-status-') and cursor!='*'):
            status=int(query.rsplit('-',1)[1]);body=(normal.PUBLIC_KEY+' rate/auth body').encode();headers['Retry-After']='1'
        if query=='fixture-json-error' or (query=='fixture-later-json' and cursor!='*'):body=(normal.PUBLIC_KEY+' non-JSON rate page').encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)))
        for name,value in headers.items():self.send_header(name,value)
        self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True
class OpenAlexProxy(normal.JsonProxy):
    def do_CONNECT(self):
        if self.path!='api.openalex.org:443':self.send_error(403);return
        upstream=socket.create_connection(('127.0.0.1',self.tls_port),timeout=2);self.send_response(200,'Connection established');self.end_headers()
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
class OpenAlexFixture(fixture.TlsAndProxy):
    additional_san=',DNS:api.openalex.org';comparisons=0
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,'Handler',OpenAlexHandler),patch.object(fixture,'ProxyHandler',OpenAlexProxy):super().setUpClass()
        OpenAlexProxy.tls_port=cls.servers[1].server_port
    def compare(self,query='alpha 日本語 + * ~',options=None,extra=None,op=True,error=False,calls=None,op_calls=None):
        options=options or ['--json'];values=[];traces=[];process=[]
        with tempfile.TemporaryDirectory(prefix='kwr-openalex-') as tmp:
            fakebin=Path(tmp)/'日本語 fixture bin';fakebin.mkdir()
            if op:shutil.copy2(PROCESS,fakebin/'op')
            for native in [False,True]:
                archive=Path(tmp)/('native.sqlite' if native else 'python.sqlite');a=Archive(archive);code.seed_history(a)
                a.upsert_page(PageSnapshot('https://arxiv.org/abs/fixture0','Old paper','alpha 日本語 cached evidence. More context.','cached','fixed'));a.close();before=normal.snapshot(archive)
                trace=Path(tmp)/('native-op.jsonl' if native else 'reference-op.jsonl')
                env=dict(self.env,PATH=str(fakebin),HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),OPENALEX_API_KEY=normal.PUBLIC_KEY,KWR_HTTP_TIMEOUT_SECONDS='1',KWR_FIXTURE_OP_TRACE=str(trace));env.update(extra or {})
                prefix=[str(fixture.BINARY)] if native else [sys.executable,'-m','katala_web_research.cli'];start=len(TRACE)
                result=subprocess.run(prefix+['search',query,'--provider','openalex',*options,'--archive',str(archive)],capture_output=True,text=True,env=env,timeout=15);traces.append(TRACE[start:]);process.append([json.loads(row) for row in trace.read_text().splitlines()] if trace.exists() else [])
                self.assertEqual(before,normal.snapshot(archive));self.assertEqual(result.returncode,1 if error else 0,(native,result.stderr))
                if error:
                    self.assertEqual(result.stdout,'');values.append(None)
                    if native:self.assertNotIn(normal.PUBLIC_KEY,result.stderr);self.assertNotIn('op://',result.stderr)
                else:self.assertEqual(result.stderr,'');values.append(json.loads(result.stdout) if '--json' in options else result.stdout)
            self.assertEqual(*values,(query,options,extra));self.assertEqual([path for path,_ in traces[0]],[path for path,_ in traces[1]]);self.assertEqual(*process)
            for _,headers in traces[1]:self.assertEqual(headers.get('accept'),'application/json')
            if calls is not None:self.assertEqual(len(traces[1]),calls)
            if op_calls is not None:self.assertEqual(len(process[1]),op_calls)
            type(self).comparisons+=1
    def test_cli_paging_options_filters_and_preservation(self):
        for options in [['--json'],['--category','research','--category','pdf','--json'],['--include-domain','arxiv.org','--exclude-domain','other.test','--json'],['--highlight-top','2','--json'],['--limit','-1','--json'],['--limit','0','--json'],['--limit','1','--candidate-multiplier','2','--json'],['--limit','101','--candidate-multiplier','1','--json'],['--limit','2']]:self.compare(options=options)
        self.compare('fixture-empty',calls=1)
        self.compare(extra={'OPENALEX_API_KEY':'','OPENALEX_MAILTO':' fixture@example.test '},calls=1)
        self.compare(extra={'OPENALEX_LANGUAGE':'en-US','OPENALEX_YEAR':'2026','OPENALEX_FROM_DATE':'2026-01-01','OPENALEX_TO_DATE':'2026-12-31','OPENALEX_HAS_PDF':'yes','OPENALEX_HAS_ABSTRACT':'off'},calls=1)
        self.compare(extra={'OPENALEX_LANGUAGE':'a\u0345','OPENALEX_YEAR':'²⁰²⁶'},calls=1)
    def test_op_resolution_order_and_no_real_credentials(self):
        for ref,error in [('Research/key',False),('nonzero',False),('empty',False),('invalid-stdout',True),('invalid-stderr',True)]:self.compare(extra={'OPENALEX_API_KEY':'op://fixture/'+ref},error=error,calls=0 if error else 1,op_calls=1)
        self.compare(extra={'OPENALEX_API_KEY':'op://fixture/Research/key'},op=False,calls=1,op_calls=0)
        self.compare(options=['--limit','101','--candidate-multiplier','1','--json'],extra={'OPENALEX_API_KEY':'op://fixture/Research/key'},calls=2,op_calls=2)
        self.compare(extra={'OPENALEX_API_KEY':'op://fixture/Research/key','OPENALEX_FROM_DATE':'bad'},error=True,calls=0,op_calls=1)
    def test_rate_auth_json_and_config_failures_abort(self):
        for status in [401,403,404,429,503]:self.compare('fixture-status-'+str(status),error=True,calls=1)
        self.compare('fixture-json-error',error=True,calls=1)
        for query,error in [('fixture-later-status-429',True),('fixture-later-status-503',True),('fixture-later-json',True),('fixture-later-empty',False)]:self.compare(query,options=['--limit','5','--candidate-multiplier','1','--json'],error=error,calls=2)
        for extra in [{'OPENALEX_FROM_DATE':'bad'},{'OPENALEX_HAS_ABSTRACT':'maybe'},{'KWR_HTTP_TIMEOUT_SECONDS':'bad'}]:self.compare(extra=extra,error=True,calls=0)
    test_downgrade_rejected=None
    test_http_proxy_and_environment_boundaries=None
    test_https_connect_proxy=None
    test_tls_trust_and_hostname=None
    test_trusted_tls_cli=None
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OpenAlexFixture));print('OpenAlex localhost CLI comparisons:',OpenAlexFixture.comparisons);raise SystemExit(not result.wasSuccessful())

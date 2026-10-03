#!/usr/bin/env python3
"""DDG CLI oracle over a synthetic local TLS/proxy; no external DNS/provider."""
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
from katala_web_research.models import PageSnapshot
from katala_web_research.http import DEFAULT_USER_AGENT

HTML=(fixture.ROOT/'tests/fixtures/sample.duckduckgo.html').read_bytes()
REQUESTS=[]
class DdgHandler(fixture.Handler):
    def do_GET(self):
        parsed=urlsplit(self.path)
        query=parse_qs(parsed.query).get('q',[''])[0]
        REQUESTS.append((self.path,{k.lower():v for k,v in self.headers.items()}))
        if parsed.path!='/html/':self.send_error(404);return
        body=HTML;status=200
        if query=='fixture-empty':body=b'<html>no results</html>'
        elif query=='fixture-error':status=503;body=b'public synthetic failure body'
        elif query=='fixture-slow':time.sleep(0.4)
        self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True
class DdgProxy(fixture.ProxyHandler):
    tls_port=0
    def do_CONNECT(self):
        # Only this exact fixture target maps to our TLS socket. No remote DNS
        # resolution, arbitrary proxy target, authentication or provider access.
        if self.path!='html.duckduckgo.com:443':self.send_error(403);return
        upstream=socket.create_connection(('127.0.0.1',self.tls_port),timeout=2)
        self.send_response(200,'Connection established');self.end_headers()
        sockets=[self.connection,upstream]
        try:
            while True:
                readable,_,_=select.select(sockets,[],[],3)
                if not readable:break
                for source in readable:
                    data=source.recv(8192)
                    if not data:return
                    (upstream if source is self.connection else self.connection).sendall(data)
        except OSError:pass
        finally:upstream.close();self.close_connection=True
class ProviderFixture(fixture.TlsAndProxy):
    additional_san=',DNS:html.duckduckgo.com'
    comparisons=0
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,'Handler',DdgHandler),patch.object(fixture,'ProxyHandler',DdgProxy):super().setUpClass()
        DdgProxy.tls_port=cls.servers[1].server_port
    def cli(self,args,rust,path):
        env=dict(self.env,HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),KWR_HTTP_TIMEOUT_SECONDS='0.15' if 'fixture-slow' in args else '1')
        prefix=[str(fixture.BINARY)] if rust else [sys.executable,'-m','katala_web_research.cli']
        start=len(REQUESTS)
        result=subprocess.run(prefix+['search',*args,'--archive',str(path)],capture_output=True,text=True,env=env,timeout=5)
        requests=REQUESTS[start:]
        self.assertLessEqual(len(requests),1)
        for _,headers in requests:
            self.assertEqual(headers.get('accept'),'text/html')
            self.assertEqual(headers.get('user-agent'),DEFAULT_USER_AGENT)
            self.assertNotIn('authorization',headers)
        return result,requests
    def test_cli_ddg_vertical(self):
        options=[['--json'],[],['--provider','ddg','--json'],['--category','research','--json'],['--category','github','--category','pdf','--json'],['--include-domain','docs.python.org','--exclude-domain','example.test','--json'],['--highlight-top','3','--json'],['--enrich-top','-1','--json']]
        options += [['--limit',str(n),'--candidate-multiplier',str(m),'--json'] for n in [-2,-1,0,1,3,20] for m in [1,2.5]]
        for option in options:
            with tempfile.TemporaryDirectory(prefix='kwr-provider-fixture-') as tmp:
                outputs=[];requests=[]
                for rust,name in [(False,'python'),(True,'rust')]:
                    path=Path(tmp)/(name+'.sqlite');a=Archive(path)
                    a.upsert_page(PageSnapshot('https://docs.python.org/3/library/urllib.html','Cached fixture','alpha Python documentation and evidence. More alpha evidence.','cached','fixed'))
                    a.close()
                    with sqlite3.connect(path) as conn:before=conn.execute('SELECT * FROM pages').fetchall()
                    result,seen=self.cli(['alpha 日本語 + * ~',*option],rust,path)
                    self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
                    outputs.append(json.loads(result.stdout) if '--json' in option else result.stdout);requests.append([url for url,_ in seen])
                    with sqlite3.connect(path) as conn:
                        self.assertEqual(before,conn.execute('SELECT * FROM pages').fetchall())
                        self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(*outputs,option);self.assertEqual(*requests,option)
                type(self).comparisons+=1
    def test_empty_and_transport_errors(self):
        for query in ['fixture-empty','fixture-error','fixture-slow']:
            with tempfile.TemporaryDirectory(prefix='kwr-provider-errors-') as tmp:
                values=[];requests=[]
                for rust,name in [(False,'python'),(True,'rust')]:
                    result,seen=self.cli([query,'--json'],rust,Path(tmp)/(name+'.sqlite'))
                    values.append((result.returncode,result.stdout));requests.append([url for url,_ in seen])
                    if query!='fixture-empty':
                        self.assertNotEqual(result.returncode,0);self.assertEqual(result.stdout,'')
                        if rust:self.assertNotIn('public synthetic failure body',result.stderr)
                self.assertEqual(*values,query);self.assertEqual(*requests,query)
                type(self).comparisons+=1
    # Only this slice's tests run; inherited transport tests belong to verify-http.
    test_downgrade_rejected=None
    test_http_proxy_and_environment_boundaries=None
    test_https_connect_proxy=None
    test_tls_trust_and_hostname=None
    test_trusted_tls_cli=None

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProviderFixture))
    print('offline DDG CLI comparisons:',ProviderFixture.comparisons)
    raise SystemExit(not result.wasSuccessful())

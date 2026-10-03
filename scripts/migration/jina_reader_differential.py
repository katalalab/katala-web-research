#!/usr/bin/env python3
"""Jina/auto paired CLI: whitelist TLS proxy, synthetic archives, no live target/key."""
import contextlib
import hashlib
import json
import os
import select
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.parse import unquote,urlsplit,parse_qs,quote
from unittest.mock import patch
import http_differential as fixture
import reader_differential as direct
import json_provider_differential as preservation
from katala_web_research.models import PageSnapshot
TRACE=[];STARTED=threading.Event();RELEASE=threading.Event();CAP=8*1024*1024
class Handler(fixture.Handler):
    def do_GET(self):
        jina=self.headers.get('Accept')=='text/plain'
        target=unquote(self.path[1:]) if jina else self.path
        if self.path.startswith('/relay?'):target=parse_qs(urlsplit(self.path).query)['target'][0]
        parsed=urlsplit(target);mode=parsed.path.strip('/')
        TRACE.append(('jina' if jina else 'direct',self.path,{k.lower():v for k,v in self.headers.items()}))
        body='# Heading\nBody 日本語 evidence'.encode() if jina else b'<html><title>Direct title</title><p>direct atomic evidence</p></html>'
        status=200;headers={'Content-Type':'text/plain; charset=utf-8' if jina else 'text/html'}
        if jina and mode in ['error','both-error','direct-redirect'] or not jina and mode=='both-error':status=503;body=b'public-fixture-key synthetic error body'
        elif jina and mode=='payload':body=b'{"code":422,"status":42200,"name":"AssertionFailureError","message":"public-fixture-key"}'
        elif jina and mode=='domain-json':body=b'{"code":"sample","message":"domain content","data":[1,2]}'
        elif jina and mode=='empty':body=b''
        elif jina and mode=='timeout':time.sleep(0.8)
        elif jina and mode=='held':STARTED.set();RELEASE.wait(3)
        elif jina and mode=='jina-redirect':status=302;headers['Location']='/relay?target='+quote(target.replace('jina-redirect','normal'),safe='');body=b''
        elif not jina and mode=='direct-redirect':status=302;headers['Location']='/direct-final';body=b''
        elif jina and mode in ['utf-cap','utf-over']:
            wanted=CAP-1 if mode=='utf-cap' else CAP;count,remainder=divmod(wanted-4,3);body=('# H\n'+'日'*count+'x'*remainder).encode()
        elif jina and mode in ['text-cap','text-over','body-over']:body=b'x'*(CAP-1 if mode=='text-cap' else CAP if mode=='text-over' else CAP+1)
        elif jina and mode in ['json-cap','json-over']:
            page=PageSnapshot(target,'H','# H\n','jina-reader','2026-01-01T00:00:00+00:00',200,'text/plain; charset=utf-8').to_dict()|{'cached':False}
            base=len((json.dumps(page,ensure_ascii=False,indent=2)+'\n').encode());count,remainder=divmod(CAP-base,6)
            body=('# H\n'+'\x00'*count+'x'*(remainder+(mode=='json-over'))).encode()
        self.send_response(status)
        for k,v in headers.items():self.send_header(k,v)
        self.send_header('Content-Length',str(len(body)));self.end_headers()
        with contextlib.suppress(BrokenPipeError,ConnectionResetError):self.wfile.write(body)
        self.close_connection=True
class Proxy(fixture.ProxyHandler):
    tls_port=0
    def do_CONNECT(self):
        if self.path not in {'r.jina.ai:443','localhost:'+str(self.tls_port)}:self.send_error(403);return
        upstream=socket.create_connection(('127.0.0.1',self.tls_port),timeout=2)
        self.send_response(200,'Connection established');self.end_headers()
        try:
            while True:
                ready,_,_=select.select([self.connection,upstream],[],[],3)
                if not ready:return
                for source in ready:
                    data=source.recv(8192)
                    if not data:return
                    (upstream if source is self.connection else self.connection).sendall(data)
        except OSError:pass
        finally:upstream.close();self.close_connection=True
class JinaFixture(fixture.TlsAndProxy):
    additional_san=',DNS:r.jina.ai'
    comparisons=0;policies=0;signals=0
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,'Handler',Handler),patch.object(fixture,'ProxyHandler',Proxy):super().setUpClass()
        Proxy.tls_port=cls.servers[1].server_port
    def seed(self,path,url):direct.ReaderFixture.seed(self,path,url)
    def env_for(self,other,mode):return dict(self.env,HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),KWR_ARCHIVE=str(other),KWR_HTTP_TIMEOUT_SECONDS='0.3' if mode=='timeout' else '5')
    def compare(self,mode='normal',reader='auto',options=None,fail=False,extra_query='',cached=True):
        options=options if options is not None else ['--json'];outputs=[];states=[];traces=[]
        with tempfile.TemporaryDirectory(prefix='kwr-jina-read-') as tmp:
            for native in [False,True]:
                root=Path(tmp)/('native' if native else 'python');root.mkdir();db=root/'日本語 selected.sqlite';other=root/'unselected.sqlite'
                target=self.plain+'/'+mode+extra_query;self.seed(db,target if cached else self.plain+'/old');self.seed(other,self.plain+'/other');before=direct.state(db);untouched=preservation.snapshot(other)
                prefix=[str(fixture.BINARY)] if native else [sys.executable,'-m','katala_web_research.cli'];start=len(TRACE)
                result=subprocess.run(prefix+['read',target,'--reader',reader,'--archive',str(db),*options],cwd=root,env=self.env_for(other,mode),capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,1 if fail else 0,(native,mode,reader,options,result.stderr));after=direct.state(db);self.assertEqual(before[:3],after[:3]);self.assertEqual(untouched,preservation.snapshot(other));self.assertFalse((root/'.katala-web-research').exists())
                if fail or '--cache' not in options or '--refresh' not in options and cached:self.assertEqual(before,after)
                if fail:
                    self.assertEqual(result.stdout,'')
                    if native:self.assertNotIn('public-fixture-key',result.stderr)
                else:
                    value=direct.untimed(json.loads(result.stdout)) if '--json' in options else result.stdout
                    outputs.append((value,result.stderr))
                    if '--json' in options and ('--cache' not in options or '--refresh' in options or not cached):
                        self.assertEqual(value['source'],'direct' if mode in ['error','payload','direct-redirect'] and reader=='auto' or reader=='direct' else 'jina-reader')
                        self.assertEqual(value['url'],self.plain+'/direct-final' if mode=='direct-redirect' and reader=='auto' else target)
                states.append(after);traces.append(TRACE[start:])
            if not fail:self.assertEqual(*outputs)
            self.assertEqual(*states)
            def stable(trace):return [(role,path,{k:v for k,v in headers.items() if k in ['accept','user-agent','authorization']}) for role,path,headers in trace]
            self.assertEqual(stable(traces[0]),stable(traces[1]))
            for trace in traces:
                for role,path,headers in trace:
                    self.assertNotIn('authorization',headers)
                    self.assertEqual(headers['accept'],'text/plain' if role=='jina' else 'text/html, text/plain;q=0.9, */*;q=0.5')
                if not fail and ('--cache' not in options or '--refresh' in options or not cached):self.assertEqual([role for role,_,_ in trace],['direct'] if reader=='direct' else ['jina','direct','direct'] if mode=='direct-redirect' else ['jina','jina'] if mode=='jina-redirect' else ['jina','direct'] if mode in ['error','payload','timeout'] else ['jina'])
            type(self).comparisons+=1
    def test_success_fallback_cache_attribution(self):
        for mode in ['normal','empty','domain-json','jina-redirect']:
            for reader in ['auto','jina']:
                for options in [['--json'],[],['--cache','--refresh','--json']]:self.compare(mode,reader,options)
        for mode in ['error','payload','direct-redirect']:
            for options in [['--json'],[],['--cache','--refresh','--json']]:self.compare(mode,'auto',options)
        self.compare('normal','direct',['--cache','--refresh','--json'])
        self.compare('normal','auto',['--cache','--json'])
        self.compare('normal','auto',['--cache','--json'],cached=False)
        self.compare('normal','jina',['--cache','--refresh','--json'],extra_query='?q=a%20b&x=%2F#fragment')
        self.compare('error','auto',['--cache','--refresh','--json'],extra_query='?q=a%20b&x=%2F#fragment')
    def test_remaining_direct_redirect_and_cache_miss(self):
        for options in [['--json'],[],['--cache','--refresh','--json']]:self.compare('direct-redirect','auto',options)
        self.compare('normal','direct',['--cache','--refresh','--json'])
        self.compare('normal','auto',['--cache','--json'])
        self.compare('normal','auto',['--cache','--json'],cached=False)
    def test_auto_timeout_keeps_cache(self):
        # urllib raw response-read timeout is TimeoutError, not FetchError;
        # auto must stop here without trying direct.
        self.compare('timeout','auto',['--cache','--refresh','--json'],fail=True)
    def test_failed_refresh_keeps_old_success_and_secret_diagnostics(self):
        for mode in ['error','payload','timeout','both-error']:
            self.compare(mode,'jina',['--cache','--refresh','--json'],fail=True,extra_query='?api_key=public-fixture-key')
        self.compare('both-error','auto',['--cache','--refresh','--json'],fail=True,extra_query='?api_key=public-fixture-key')
    def test_native_body_stdout_cap_exact_one_over(self):
        for mode in getattr(self,'cap_modes',['text-cap','text-over','json-cap','json-over','body-over','utf-cap','utf-over']):
            options=['--cache','--refresh']+(['--json'] if mode.startswith('json') else [])
            with tempfile.TemporaryDirectory(prefix='kwr-jina-cap-') as tmp:
                values=[]
                for native in [False,True]:
                    root=Path(tmp)/('native' if native else 'python');root.mkdir();db=root/'owned.sqlite';target=self.plain+'/'+mode;self.seed(db,target);before=direct.state(db)
                    prefix=[str(fixture.BINARY)] if native else [sys.executable,'-m','katala_web_research.cli']
                    result=subprocess.run(prefix+['read',target,'--reader','jina','--archive',str(db),*options],cwd=root,env=self.env_for(root/'unused.sqlite',mode),capture_output=True,timeout=25)
                    rejected=native and mode in ['text-over','json-over','body-over','utf-over'];self.assertEqual(result.returncode,1 if rejected else 0,(mode,native,result.stderr[:500]))
                    after=direct.state(db);self.assertEqual(before[:3],after[:3])
                    if rejected:
                        self.assertEqual(result.stdout,b'');self.assertEqual(before,after)
                        self.assertIn(b'Jina reader transport failed (FetchError)' if mode=='body-over' else b'reader output exceeds 8 MiB',result.stderr)
                    else:
                        self.assertEqual(len(result.stdout),CAP+(mode in ['text-over','json-over','utf-over']) if mode!='body-over' else CAP+2,(mode,native,len(result.stdout)))
                        values.append(direct.untimed(json.loads(result.stdout)) if '--json' in options else hashlib.sha256(result.stdout).hexdigest())
                if mode in ['text-cap','json-cap','utf-cap']:self.assertEqual(*values)
                type(self).policies+=1
    def test_rejection_class_before_cache_write(self):
        self.cap_modes=['text-over','json-over','body-over','utf-over'];self.test_native_body_stdout_cap_exact_one_over()
    def test_multibyte_cap_and_target_query(self):
        self.cap_modes=['utf-cap','utf-over'];self.test_native_body_stdout_cap_exact_one_over()
        self.compare('normal','jina',['--cache','--refresh','--json'],extra_query='?q=a%20b&x=%2F#fragment')
        self.compare('error','auto',['--cache','--refresh','--json'],extra_query='?q=a%20b&x=%2F#fragment')
    def test_owned_jina_worker_sigint_preserves_cache(self):
        for native in [False,True]:
            with tempfile.TemporaryDirectory(prefix='kwr-jina-signal-') as tmp:
                root=Path(tmp);db=root/'owned.sqlite';target=self.plain+'/held';self.seed(db,target);before=direct.state(db);STARTED.clear();RELEASE.clear()
                prefix=[str(fixture.BINARY)] if native else [sys.executable,'-m','katala_web_research.cli']
                child=subprocess.Popen(prefix+['read',target,'--reader','auto','--cache','--refresh','--json','--archive',str(db)],cwd=root,env=self.env_for(root/'unused.sqlite','held'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
                try:
                    self.assertTrue(STARTED.wait(5));os.killpg(child.pid,signal.SIGINT);stdout,stderr=child.communicate(timeout=3);self.assertEqual(child.returncode,-signal.SIGINT);self.assertEqual(stdout,b'');self.assertEqual(before,direct.state(db));type(self).signals+=1
                finally:
                    RELEASE.set()
                    if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.communicate(timeout=3)
if __name__=='__main__':
    wanted=set(sys.argv[1:]) or {'test_success_fallback_cache_attribution','test_failed_refresh_keeps_old_success_and_secret_diagnostics','test_native_body_stdout_cap_exact_one_over','test_owned_jina_worker_sigint_preserves_cache','test_auto_timeout_keeps_cache'}
    suite=unittest.TestSuite(JinaFixture(name) for name in sorted(wanted));result=unittest.TextTestRunner(verbosity=2).run(suite)
    print('Jina/auto paired CLI:',JinaFixture.comparisons,'named cap policies:',JinaFixture.policies,'owned signals:',JinaFixture.signals);sys.exit(not result.wasSuccessful())

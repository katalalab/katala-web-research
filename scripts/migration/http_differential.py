#!/usr/bin/env python3
"""Local, unauthenticated HTTP fixtures; never requests an external provider."""
import json
import os
import socket
import shutil
import select
import ssl
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from katala_web_research.http import fetch_url, FetchError
from katala_web_research.archive import Archive
from katala_web_research.models import FeedItem, FeedSource

ROOT=Path(__file__).resolve().parents[2]
PROBE=Path(os.environ.get('KWR_HTTP_PROBE',ROOT/'target/debug/examples/http_probe'))
BINARY=Path(os.environ.get('KWR_RUST_BINARY',ROOT/'target/debug/kwr-rs'))
RSS=(ROOT/'tests/fixtures/sample.rss.xml').read_bytes()
RECORDS=[]
CONNECTS=[]
DOWNGRADE_ORIGIN=''
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        RECORDS.append((self.path,{k.lower():v for k,v in self.headers.items()}))
        route=self.path.split('?',1)[0]
        body=RSS;status=200;headers={'Content-Type':'application/rss+xml; charset=utf-8'}
        if route=='/redirect': status=302;headers['Location']='/rss';body=b''
        elif route=='/uri-redirect':status=302;headers['URI']='/rss';body=b''
        elif route=='/cross-origin':status=302;headers['Location']=f'http://localhost:{self.server.server_port}/rss';body=b''
        elif route=='/downgrade':status=302;headers['Location']=DOWNGRADE_ORIGIN+'/rss';body=b''
        elif route.startswith('/slow-chain/'):
            time.sleep(0.06)
            n=int(route.rsplit('/',1)[1])
            if n<4:status=302;headers['Location']=f'/slow-chain/{n+1}';body=b''
        elif route=='/drip':body=b'12345'
        elif route=='/declared-big':headers['Content-Length']=str(8*1024*1024+1);body=b'x'
        elif route=='/loop': status=302;headers['Location']='/loop';body=b''
        elif route.startswith('/cycle/'):
            n=int(route.rsplit('/',1)[1]);status=302;headers['Location']=f'/cycle/{(n+1)%5}';body=b''
        elif route.startswith('/chain/'):
            n=int(route.rsplit('/',1)[1])
            if n<10:status=302;headers['Location']=f'/chain/{n+1}';body=b''
        elif route=='/latin1':
            body='<rss><channel><title>Café £</title><item><link>https://fixture.test/cafe</link><title>Café</title><description>price £ and \u0080</description></item></channel></rss>'.encode('latin1')
            headers['Content-Type']='application/rss+xml; charset=iso-8859-1'
        elif route=='/sjis':
            body='<rss><channel><title>日本語</title><item><link>https://fixture.test/日本語</link><title>日本語</title></item></channel></rss>'.encode('shift_jis')
            headers['Content-Type']='application/rss+xml; charset=shift_jis'
        elif route=='/unknown-charset':headers['Content-Type']='application/rss+xml; charset=unknown-fixture'
        elif route=='/invalid':body=b'<rss><broken>'
        elif route=='/404':status=404;body=b'fixture error body'
        elif route=='/503':status=503;body=b'fixture unavailable'
        elif route=='/302-no-location':status=302;body=b'fixture redirect missing'
        elif route=='/slow-headers':time.sleep(0.4)
        elif route=='/big':body=b'x'*256
        elif route=='/close-big':body=b'x'*256
        elif route=='/partial':body=b'<rss>';headers['Content-Length']='100'
        self.send_response(status)
        for k,v in headers.items():self.send_header(k,v)
        if route!='/close-big' and 'Content-Length' not in headers:self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        if route=='/slow-body':time.sleep(0.4)
        try:
            if route=='/drip':
                for byte in body:
                    time.sleep(0.06);self.wfile.write(bytes([byte]));self.wfile.flush()
            else:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True

class Fixtures(unittest.TestCase):
    comparisons=0
    safety_checks=0
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.server.daemon_threads=True
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.origin=f'http://127.0.0.1:{cls.server.server_port}'
        # Child processes never inherit credentials, real proxies or custom CA paths.
        cls.env={k:v for k,v in os.environ.items() if not k.startswith(('KWR_','GITHUB_','OPENALEX_','BRAVE_','JINA_')) and not k.lower().endswith('_proxy') and k not in ['REQUEST_METHOD','SSL_CERT_FILE','SSL_CERT_DIR','CURL_CA_BUNDLE','REQUESTS_CA_BUNDLE']}
        cls.env['PYTHONPATH']=str(ROOT/'src')
        cls.old_env=os.environ.copy()
        for key in list(os.environ):
            if key.lower().endswith('_proxy') or key in ['REQUEST_METHOD','KWR_HTTP_TIMEOUT_SECONDS','SSL_CERT_FILE','SSL_CERT_DIR']:os.environ.pop(key,None)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)
        os.environ.clear();os.environ.update(cls.old_env)
    def probe(self,url,env=None,**options):
        p=subprocess.run([str(PROBE)],input=json.dumps({'url':url,**options}),env=env or self.env,capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
        return json.loads(p.stdout)
    def test_response_parity(self):
        for route in ['/rss','/redirect','/uri-redirect','/chain/0','/latin1','/sjis','/unknown-charset','/invalid']:
            url=self.origin+route
            p=fetch_url(url,headers={'Accept':'application/rss+xml, application/atom+xml, application/feed+json, application/json, text/xml, */*'})
            r=self.probe(url)
            self.assertEqual(p.url,r['url'],route);self.assertEqual(p.status,r['status'],route)
            self.assertEqual(p.body,bytes(r['body']),route);self.assertEqual(p.text,r['text'],route)
            type(self).comparisons+=1
    def test_safety_policy(self):
        # Reference timeouts apply per socket operation. Native owns one total
        # deadline: a deliberately measured contract difference, not parity.
        for route in ['/drip','/slow-chain/0']:
            self.assertEqual(fetch_url(self.origin+route,timeout=0.15).status,200)
            start=time.monotonic();r=self.probe(self.origin+route,timeout=0.15)
            self.assertEqual(r['error_kind'],'TimeoutError',(route,r))
            self.assertLess(time.monotonic()-start,1.5)
            type(self).safety_checks+=1
        r=self.probe(self.origin+'/declared-big')
        self.assertEqual(r['error_kind'],'FetchError');self.assertIn('exceeds limit',r['error_message'])
        before=len(RECORDS)
        r=self.probe(self.origin.replace('http://','http://fixture-user:fixture-password@')+'/rss')
        self.assertEqual(r['error_kind'],'FetchError');self.assertEqual(before,len(RECORDS))
        self.assertNotIn('fixture-password',r['error_message'])
        r=self.probe(self.origin+'/404?token=fixture-secret#fixture-fragment')
        for marker in ['fixture-secret','fixture-fragment','fixture error body']:
            self.assertNotIn(marker,r['error_message'])
        for route,retained in [('/redirect',True),('/cross-origin',False)]:
            start=len(RECORDS)
            r=self.probe(self.origin+route,headers={'Authorization':'public-fixture-marker','Cookie':'public-fixture-cookie','Proxy-Authorization':'public-fixture-proxy'})
            self.assertEqual(r['status'],200)
            destination=RECORDS[start:][-1][1]
            for header in ['authorization','cookie','proxy-authorization']:
                self.assertEqual(header in destination,retained,(route,header,destination))
        type(self).safety_checks+=5
        start=len(RECORDS)
        with self.assertRaises(FetchError):fetch_url(self.origin+'/cycle/0',timeout=1)
        reference_requests=len(RECORDS)-start;start=len(RECORDS)
        r=self.probe(self.origin+'/cycle/0',timeout=3)
        self.assertEqual(r['error_kind'],'FetchError');self.assertIn('redirect limit',r['error_message'])
        self.assertEqual(len(RECORDS)-start,11)
        self.assertGreater(reference_requests,11)
        type(self).safety_checks+=1
    def test_guard_rejection_retains_archive_items(self):
        for route in ['/declared-big','/drip','/slow-chain/0']:
            with tempfile.TemporaryDirectory(prefix='kwr-guard-fixture-') as tmp:
                path=Path(tmp)/'guard.sqlite';source=self.origin+route;a=Archive(path)
                a.upsert_feed_source(FeedSource(source,'Old title','rss','fixed','fixed','ok',1.0,'',1))
                a.upsert_feed_items([FeedItem(source,'https://fixture.test/old','Old evidence','must remain','Old title',None,'fixed')]);a.close()
                p=subprocess.run([str(BINARY),'feeds','refresh','--archive',str(path),'--json'],env=dict(self.env,KWR_HTTP_TIMEOUT_SECONDS='0.15'),capture_output=True,text=True,timeout=5)
                self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,'')
                result=json.loads(p.stdout);self.assertEqual(result['indexed_items'],0)
                with sqlite3.connect(path) as conn:
                    self.assertEqual(conn.execute('SELECT title,summary FROM feed_items').fetchall(),[('Old evidence','must remain')])
                    self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                    self.assertEqual(conn.execute('SELECT status FROM feed_sources').fetchone()[0],'error')
                type(self).safety_checks+=1
        for _,headers in RECORDS:
            self.assertEqual(headers.get('user-agent'),'katala-web-research/0.1 (+local research tool)')
    def test_errors_and_no_retries(self):
        for route in ['/404','/503','/302-no-location','/loop','/slow-headers']:
            start=len(RECORDS);url=self.origin+route
            timeout=0.15 if route=='/slow-headers' else 1.0
            try:fetch_url(url,timeout=timeout)
            except Exception as e:kind=e.__class__.__name__
            else:self.fail('expected fetch failure')
            r=self.probe(url,timeout=timeout)
            self.assertEqual(r['error_kind'],kind,(route,r))
            expected=10 if route=='/loop' else 2
            self.assertEqual(len(RECORDS)-start,expected,route)
            type(self).comparisons+=1
    def test_bounds_and_body_errors(self):
        for route in ['/big','/close-big']:
            r=self.probe(self.origin+route,limit=64)
            self.assertEqual(r['error_kind'],'FetchError');self.assertIn('exceeds limit',r['error_message'])
        for route in ['/slow-body','/partial']:
            url=self.origin+route
            try:fetch_url(url,timeout=0.15)
            except Exception as e:kind=e.__class__.__name__
            else:self.fail('expected body failure')
            r=self.probe(url,timeout=0.15)
            self.assertEqual(kind,r['error_kind'],(route,kind,r));type(self).comparisons+=1
    def test_refresh_archive_parity_and_failure_preservation(self):
        for route in ['/rss','/redirect','/latin1','/sjis','/unknown-charset','/invalid','/404','/503','/loop','/slow-headers','/slow-body','/partial']:
            with tempfile.TemporaryDirectory(prefix='kwr-http-fixture-') as tmp:
                source=self.origin+route;outputs=[];rows=[]
                for rust,name in [(False,'python'),(True,'rust')]:
                    path=Path(tmp)/(name+'.sqlite');a=Archive(path)
                    a.upsert_feed_source(FeedSource(source,'Old title','rss','fixed','fixed','ok',1.0,'',1))
                    a.upsert_feed_items([FeedItem(source,'https://fixture.test/old','Old evidence','must remain','Old title',None,'fixed')]);a.close()
                    env=dict(self.env,KWR_HTTP_TIMEOUT_SECONDS='0.15' if route in ['/slow-headers','/slow-body'] else '1')
                    prefix=[str(BINARY)] if rust else [sys.executable,'-m','katala_web_research.cli']
                    p=subprocess.run(prefix+['feeds','refresh','--archive',str(path),'--json'],env=env,capture_output=True,text=True,timeout=5)
                    self.assertEqual(p.returncode,0,(route,p.stderr));self.assertEqual(p.stderr,'')
                    result=json.loads(p.stdout);result['archive']='<archive>'
                    for row in result['refreshed']:row['last_fetched_at']='<time>'
                    outputs.append(result)
                    with sqlite3.connect(path) as conn:
                        conn.row_factory=sqlite3.Row
                        records=[dict(r) for r in conn.execute('SELECT * FROM feed_items ORDER BY source_url,url')]
                        for r in records:
                            if r['fetched_at']!='fixed':r['fetched_at']='<time>'
                        rows.append(records)
                        self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(*outputs,route);self.assertEqual(*rows,route)
                self.assertIn('https://fixture.test/old',[r['url'] for r in rows[0]])
                type(self).comparisons+=1

class ProxyHandler(Handler):
    def do_CONNECT(self):
        CONNECTS.append(self.path)
        host,port=self.path.rsplit(':',1)
        if host not in ['localhost','127.0.0.1']:
            self.send_error(403);return
        upstream=socket.create_connection((host,int(port)),timeout=2)
        self.send_response(200,'Connection established');self.end_headers()
        sockets=[self.connection,upstream]
        try:
            while True:
                readable,_,_=select.select(sockets,[],[],3)
                if not readable:break
                for source in readable:
                    data=source.recv(8192)
                    if not data:return
                    target=upstream if source is self.connection else self.connection
                    target.sendall(data)
        except (OSError,ConnectionResetError):pass
        finally:upstream.close();self.close_connection=True

class TlsAndProxy(unittest.TestCase):
    comparisons=0
    safety_checks=0
    probe=Fixtures.probe
    @classmethod
    def setUpClass(cls):
        global DOWNGRADE_ORIGIN
        cls.tmp=tempfile.TemporaryDirectory(prefix='kwr-tls-fixture-')
        root=Path(cls.tmp.name)
        ca_config=root/'ca.cnf';ca_config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=v3\n[dn]\nCN=kwr synthetic fixture CA\n[v3]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid:always\n')
        leaf_config=root/'leaf.cnf';leaf_config.write_text('[req]\nprompt=no\ndistinguished_name=dn\n[dn]\nCN=localhost\n[v3]\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:localhost\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n')
        if getattr(cls,'additional_san',''):
            leaf_config.write_text(leaf_config.read_text().replace('subjectAltName=DNS:localhost','subjectAltName=DNS:localhost'+cls.additional_san))
        # Ephemeral test keys remain in TemporaryDirectory and are never tracked.
        commands=[['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-config',str(ca_config),'-keyout',str(root/'ca.key'),'-out',str(root/'ca.crt')],
                  ['req','-new','-newkey','rsa:2048','-nodes','-config',str(leaf_config),'-keyout',str(root/'leaf.key'),'-out',str(root/'leaf.csr')],
                  ['x509','-req','-in',str(root/'leaf.csr'),'-CA',str(root/'ca.crt'),'-CAkey',str(root/'ca.key'),'-CAcreateserial','-days','1','-extfile',str(leaf_config),'-extensions','v3','-out',str(root/'leaf.crt')]]
        openssl_tool=shutil.which('openssl')
        if not openssl_tool:raise RuntimeError('TLS fixtures require an existing OpenSSL CLI; no automatic install')
        for command in commands:subprocess.run([openssl_tool,*command],check=True,capture_output=True,timeout=5)
        cls.ca_path=root/'ca.crt';cls.ca_pem=cls.ca_path.read_text()
        cls.env={k:v for k,v in os.environ.items() if not k.startswith(('KWR_','GITHUB_','OPENALEX_','BRAVE_','JINA_')) and not k.lower().endswith('_proxy') and k not in ['REQUEST_METHOD','SSL_CERT_FILE','SSL_CERT_DIR','CURL_CA_BUNDLE','REQUESTS_CA_BUNDLE']}
        cls.env['PYTHONPATH']=str(ROOT/'src')
        cls.old_env=os.environ.copy();cls.old_opener=urllib.request._opener
        for key in list(os.environ):
            if key.lower().endswith('_proxy') or key in ['REQUEST_METHOD','KWR_HTTP_TIMEOUT_SECONDS','SSL_CERT_FILE','SSL_CERT_DIR']:os.environ.pop(key,None)
        cls.servers=[];cls.threads=[]
        for handler,tls in [(Handler,False),(Handler,True),(ProxyHandler,False)]:
            server=ThreadingHTTPServer(('127.0.0.1',0),handler);server.daemon_threads=True
            if tls:
                context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(root/'leaf.crt',root/'leaf.key')
                server.socket=context.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            cls.servers.append(server);cls.threads.append(thread)
        cls.plain=f'http://127.0.0.1:{cls.servers[0].server_port}'
        cls.tls=f'https://localhost:{cls.servers[1].server_port}'
        cls.wrong_host=f'https://127.0.0.1:{cls.servers[1].server_port}'
        cls.proxy=f'http://127.0.0.1:{cls.servers[2].server_port}'
        DOWNGRADE_ORIGIN=cls.plain
    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:server.shutdown();server.server_close()
        for thread in cls.threads:thread.join(timeout=2)
        os.environ.clear();os.environ.update(cls.old_env);urllib.request._opener=cls.old_opener
        cls.tmp.cleanup()
    def python_response(self,url,values=None,trust=False):
        old=os.environ.copy();old_opener=urllib.request._opener
        try:
            os.environ.update(values or {})
            context=ssl.create_default_context(cafile=str(self.ca_path)) if trust else ssl.create_default_context()
            urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=context)))
            try:
                response=fetch_url(url,timeout=1)
                return {'url':response.url,'body':list(response.body),'text':response.text,'status':response.status}
            except Exception as e:
                self.last_python_error=str(e)
                return {'error_kind':e.__class__.__name__}
        finally:os.environ.clear();os.environ.update(old);urllib.request._opener=old_opener
    def compare(self,url,values=None,trust=False):
        values=values or {};env=dict(self.env,**values)
        options={'timeout':1}
        if trust:options['root_pem']=self.ca_pem
        r=self.probe(url,env=env,**options);p=self.python_response(url,values,trust)
        self.assertEqual(p,{k:r[k] for k in p},(url,values,p,r))
        if trust and url.startswith(self.tls) and 'error_kind' in p:self.fail('synthetic trusted TLS: '+self.last_python_error+' native '+str(r))
        type(self).comparisons+=1
        return r
    def test_tls_trust_and_hostname(self):
        self.assertEqual(self.compare(self.tls+'/rss',trust=True)['status'],200)
        self.assertEqual(self.compare(self.tls+'/rss')['error_kind'],'FetchError')
        self.assertEqual(self.compare(self.wrong_host+'/rss',trust=True)['error_kind'],'FetchError')
    def test_downgrade_rejected(self):
        p=self.python_response(self.tls+'/downgrade',trust=True)
        self.assertEqual(p['status'],200)
        start=len(RECORDS)
        r=self.probe(self.tls+'/downgrade',timeout=1,root_pem=self.ca_pem)
        self.assertEqual(r['error_kind'],'FetchError');self.assertIn('downgrade rejected',r['error_message'])
        self.assertEqual([path for path,_ in RECORDS[start:]],['/downgrade'])
        type(self).safety_checks+=1
    def test_http_proxy_and_environment_boundaries(self):
        start=len(RECORDS)
        self.compare(self.plain+'/rss',{'http_proxy':self.proxy,'HTTP_PROXY':'http://127.0.0.1:1'})
        self.assertTrue(any(path.startswith(self.plain+'/') for path,_ in RECORDS[start:]))
        for values in [{'HTTP_PROXY':'http://127.0.0.1:1','REQUEST_METHOD':'GET'},
                       {'HTTP_PROXY':'http://127.0.0.1:1','http_proxy':''},
                       {'http_proxy':'http://127.0.0.1:1','no_proxy':'127.0.0.1'},
                       {'http_proxy':'http://127.0.0.1:1','no_proxy':'*'},
                       {'http_proxy':'http://127.0.0.1:1','NO_PROXY':'127.0.0.1','no_proxy':''},
                       {'http_proxy':'http://127.0.0.1:1'}]:self.compare(self.plain+'/rss',values)
    def test_https_connect_proxy(self):
        before=len(CONNECTS)
        self.assertEqual(self.compare(self.tls+'/rss',{'https_proxy':self.proxy},trust=True)['status'],200)
        self.assertEqual(len(CONNECTS)-before,2)
        self.compare(self.tls+'/rss',{'https_proxy':self.proxy})
    def test_trusted_tls_cli(self):
        with tempfile.TemporaryDirectory(prefix='kwr-tls-archive-') as tmp:
            outputs=[]
            for rust,name in [(False,'python'),(True,'rust')]:
                path=Path(tmp)/(name+'.sqlite')
                env=dict(self.env,SSL_CERT_FILE=str(self.ca_path))
                prefix=[str(BINARY)] if rust else [sys.executable,'-m','katala_web_research.cli']
                p=subprocess.run(prefix+['feeds','refresh','--source',self.tls+'/rss','--archive',str(path),'--json'],env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(p.returncode,0,p.stderr);result=json.loads(p.stdout);result['archive']='<archive>'
                for row in result['refreshed']:row['last_fetched_at']='<time>'
                outputs.append(result)
            self.assertEqual(*outputs);self.assertEqual(outputs[0]['indexed_items'],2,outputs)
            type(self).comparisons+=1

if __name__=='__main__':
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in [Fixtures,TlsAndProxy]])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print('offline HTTP comparisons:',Fixtures.comparisons+TlsAndProxy.comparisons)
    print('intentional safety checks:',Fixtures.safety_checks+TlsAndProxy.safety_checks)
    raise SystemExit(not result.wasSuccessful())

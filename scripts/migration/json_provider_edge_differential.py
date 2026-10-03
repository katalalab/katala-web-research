#!/usr/bin/env python3
"""CLI malformed/type/config cases over strict loopback endpoint mappings only."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
import json_provider_differential as normal
import http_differential as fixture
from katala_web_research.archive import Archive
from katala_web_research.models import PageSnapshot

BODY='{}'
TRACE=[]
class EdgeHandler(normal.JsonHandler):
    def do_GET(self):
        TRACE.append((self.path,{k.lower():v for k,v in self.headers.items()}))
        status=200 if urlsplit(self.path).path in {'/search','/res/v1/web/search','/'} else 404
        body=(BODY if status==200 else normal.PUBLIC_KEY+' wrong endpoint body').encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True
class EdgeFixture(normal.JsonFixture):
    comparisons={p:0 for p in ['searxng','brave','jina']}
    policies=0
    config_boundaries=0
    @classmethod
    def setUpClass(cls):
        with patch.object(normal,'JsonHandler',EdgeHandler):super().setUpClass()
    def run_case(self,case,extra=None,native_only=False,expected=None,expected_calls=None):
        global BODY
        steps=case.get('steps',[]);BODY=steps[0]['text'] if steps else '{}'
        provider=case['provider'];values=[];traces=[];messages=[]
        with tempfile.TemporaryDirectory(prefix='kwr-json-edges-') as tmp:
            for rust in ([True] if native_only else [False,True]):
                path=Path(tmp)/('native.sqlite' if rust else 'python.sqlite');a=Archive(path)
                a.upsert_page(PageSnapshot('https://fixture.test/old','Old title','must remain','fixture','fixed'));a.close();before=normal.snapshot(path)
                env=dict(self.env,HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),KWR_HTTP_TIMEOUT_SECONDS='1',KWR_SEARXNG_URL=self.plain,BRAVE_SEARCH_API_KEY=normal.PUBLIC_KEY,JINA_API_KEY=normal.PUBLIC_KEY)
                for key,value in case.get('env',{}).items():
                    env[key]=self.plain+'///' if key=='KWR_SEARXNG_URL' and value=='http://fixture.test///' else value
                env.update(extra or {})
                reference=case.get('native_expected',case['expected']) if rust else case['expected']
                code=expected if expected is not None else int('error_kind' in reference)
                prefix=[str(fixture.BINARY)] if rust else [sys.executable,'-m','katala_web_research.cli'];start=len(TRACE)
                result=subprocess.run(prefix+['search',case.get('query','alpha'),'--provider',provider,'--limit',str(case.get('limit',10)),'--candidate-multiplier','1','--json','--archive',str(path)],env=env,capture_output=True,text=True,timeout=10)
                trace=TRACE[start:];traces.append(trace)
                self.assertEqual(result.returncode,code,(provider,case['name'],rust,result.stderr));self.assertEqual(before,normal.snapshot(path))
                self.assertEqual(len(trace),len(steps) if expected_calls is None else expected_calls,(provider,case['name'],rust))
                if code:
                    self.assertEqual(result.stdout,'');values.append(None)
                    if rust:self.assertNotIn(normal.PUBLIC_KEY,result.stderr)
                else:
                    self.assertEqual(result.stderr,'');values.append(json.loads(result.stdout))
                messages.append(result.stderr)
                for _,headers in trace:
                    self.assertEqual(headers.get('accept'),'application/json');self.assertEqual(headers.get('user-agent'),fixture.DEFAULT_USER_AGENT if hasattr(fixture,'DEFAULT_USER_AGENT') else 'katala-web-research/0.1 (+local research tool)')
            if not native_only:
                if 'native_expected' not in case:self.assertEqual(*values,(provider,case['name']))
                else:type(self).policies+=1
                self.assertEqual([p for p,_ in traces[0]],[p for p,_ in traces[1]])
                type(self).comparisons[provider]+=1
        return messages
    def test_library_edges_through_cli(self):
        data=json.loads((fixture.ROOT/'rust/tests/fixtures/json-provider-edges.json').read_text())
        for case in data['cases']:
            # argv/environment cannot carry NUL. A whitespace-only instance URL
            # is a transport/config test below, not a scripted adapter request.
            if '\0' in case['query'] or (case['provider']=='searxng' and case['name']=='whitespace-credential'):continue
            with self.subTest(provider=case['provider'],case=case['name']):self.run_case(case)
    def test_credentials_endpoint_and_preflight_order(self):
        for provider,key in [('searxng','KWR_SEARXNG_URL'),('brave','BRAVE_SEARCH_API_KEY'),('jina','JINA_API_KEY')]:
            case={'provider':provider,'name':'missing-before-invalid-http','env':{key:''},'expected':{'error_kind':'FetchError'}}
            messages=self.run_case(case,extra={'KWR_HTTP_TIMEOUT_SECONDS':'bad'},expected=1,expected_calls=0)
            for message in messages:self.assertIn('required',message)
            type(self).config_boundaries+=1
        for provider,key in [('brave','BRAVE_SEARCH_API_KEY'),('jina','JINA_API_KEY')]:
            case={'provider':provider,'name':'invalid-secret-header','env':{key:normal.PUBLIC_KEY+'\r\nX-Injection: marker'},'expected':{'error_kind':'FetchError'}}
            self.run_case(case,expected=1,expected_calls=0);type(self).config_boundaries+=1
        for value,calls in [(self.plain+'/wrong',1),('::'+normal.PUBLIC_KEY,0),('   ',0)]:
            case={'provider':'searxng','name':'wrong-instance-endpoint','env':{'KWR_SEARXNG_URL':value},'expected':{'error_kind':'FetchError'}}
            self.run_case(case,expected=1,expected_calls=calls);type(self).config_boundaries+=1
        # Native userinfo rejection is an intentional policy; do not let urllib
        # attempt to resolve an authority containing synthetic credentials.
        value=self.plain.replace('http://','http://fixture-user:'+normal.PUBLIC_KEY+'@')
        case={'provider':'searxng','name':'userinfo-endpoint-rejected','env':{'KWR_SEARXNG_URL':value},'expected':{'error_kind':'FetchError'}}
        self.run_case(case,native_only=True,expected=1,expected_calls=0);type(self).config_boundaries+=1
    test_brave_key_redirect_origin_boundaries=None
    test_each_provider_failures_redaction_and_preflight=None
    test_each_provider_query_options_rank_pagination_and_preservation=None
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(EdgeFixture))
    print('JSON edge CLI comparisons:',EdgeFixture.comparisons,'named safety comparisons:',EdgeFixture.policies,'credential/config boundaries:',EdgeFixture.config_boundaries)
    raise SystemExit(not result.wasSuccessful())

#!/usr/bin/env python3
"""Native gh fixture + exact loopback REST mapping; synthetic history/token only."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
import http_differential as fixture
import json_provider_differential as normal
import github_code_differential as code
from katala_web_research.archive import Archive
from katala_web_research.models import PageSnapshot
PROCESS=Path(os.environ.get('KWR_PROCESS_FIXTURE',fixture.ROOT/'target/debug/examples/process_fixture'));TRACE=[]
REST_BODY=json.loads((fixture.ROOT/'rust/tests/fixtures/github-repo-golden.json').read_text())['cases'][0]['steps'][0]['text'].encode()
class RepoHandler(fixture.Handler):
    def do_GET(self):
        TRACE.append((self.path,{k.lower():v for k,v in self.headers.items()}));parsed=urlsplit(self.path)
        if parsed.path!='/search/repositories':self.send_error(404);return
        body=REST_BODY;self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True
class RepoFixture(fixture.TlsAndProxy):
    additional_san=',DNS:api.github.com';comparisons=0
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,'Handler',RepoHandler),patch.object(fixture,'ProxyHandler',code.CodeProxy):super().setUpClass()
        code.CodeProxy.tls_port=cls.servers[1].server_port
    def compare(self,query='alpha 日本語 + * ~',gh=True,options=None,token=normal.PUBLIC_KEY,error=False,expected_calls=None,extra=None):
        options=options or ['--json'];values=[];traces=[]
        with tempfile.TemporaryDirectory(prefix='kwr-github-repo-') as tmp:
            fakebin=Path(tmp)/'日本語 fixture bin';fakebin.mkdir()
            if gh:shutil.copy2(PROCESS,fakebin/'gh')
            for native in [False,True]:
                archive=Path(tmp)/('native.sqlite' if native else 'python.sqlite');a=Archive(archive);code.seed_history(a)
                for url in ['https://github.com/fixture/repo','https://github.com/fixture/repo0']:a.upsert_page(PageSnapshot(url,'Old repo','alpha 日本語 repository evidence. More context.','cached','fixed'))
                a.close();before=normal.snapshot(archive)
                env=dict(self.env,PATH=str(fakebin),HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),GITHUB_TOKEN=token,KWR_HTTP_TIMEOUT_SECONDS='1')
                env.update(extra or {})
                prefix=[str(fixture.BINARY)] if native else [sys.executable,'-m','katala_web_research.cli'];start=len(TRACE)
                result=subprocess.run(prefix+['search',query,'--provider','github',*options,'--archive',str(archive)],capture_output=True,text=True,env=env,timeout=10);traces.append(TRACE[start:])
                self.assertEqual(before,normal.snapshot(archive));self.assertEqual(result.returncode,1 if error else 0,(native,result.stderr));self.assertEqual(result.stdout,'') if error else None
                if error:
                    values.append(None)
                    if native:self.assertNotIn(normal.PUBLIC_KEY,result.stderr)
                else:
                    self.assertEqual(result.stderr,'');values.append(json.loads(result.stdout) if '--json' in options else result.stdout)
            self.assertEqual(*values,(query,options,gh));self.assertEqual([path for path,_ in traces[0]],[path for path,_ in traces[1]])
            for reference,native in zip(traces[0],traces[1]):
                for header in ['accept','authorization','x-github-api-version']:self.assertEqual(reference[1].get(header),native[1].get(header))
            type(self).comparisons+=1
            if expected_calls is not None:self.assertEqual(len(traces[1]),expected_calls)
    def test_gh_and_rest_cli_options_history_and_requests(self):
        for gh in [False,True]:
            for options in [['--json'],['--category','github','--json'],['--include-domain','github.com','--exclude-domain','other.test','--json'],['--highlight-top','2','--json'],['--limit','-1','--json'],['--limit','0','--json'],['--limit','1','--candidate-multiplier','2','--json'],['--limit','31','--json'],['--limit','2']]:self.compare(gh=gh,options=options,expected_calls=0 if gh else 1)
        for token in ['',normal.PUBLIC_KEY,' '+normal.PUBLIC_KEY+' ']:self.compare(gh=False,token=token,expected_calls=1)
    def test_gh_fallback_failure_and_discard_boundaries(self):
        for query in ['fixture-gh-empty','fixture-gh-nonzero']:self.compare(query,expected_calls=1)
        for query in ['fixture-gh-malformed','fixture-gh-invalid','fixture-gh-stderr-invalid']:self.compare(query,error=True,expected_calls=0)
        self.compare('fixture-gh-retracted',expected_calls=0)
        self.compare(extra={'KWR_HTTP_TIMEOUT_SECONDS':'bad'},expected_calls=0)
        self.compare(token='\udcff',expected_calls=0)
        self.compare('fixture-gh-empty',extra={'KWR_HTTP_TIMEOUT_SECONDS':'bad'},error=True,expected_calls=0)
    test_downgrade_rejected=None
    test_http_proxy_and_environment_boundaries=None
    test_https_connect_proxy=None
    test_tls_trust_and_hostname=None
    test_trusted_tls_cli=None
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RepoFixture));print('GitHub repository localhost CLI comparisons:',RepoFixture.comparisons);raise SystemExit(not result.wasSuccessful())

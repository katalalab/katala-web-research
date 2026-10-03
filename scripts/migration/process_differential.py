#!/usr/bin/env python3
"""Execute only the owned Rust process fixture; no installed gh/op or network."""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FIXTURE=Path(os.environ.get('KWR_PROCESS_FIXTURE',ROOT/'target/debug/examples/process_fixture'))
class ProcessFixture(unittest.TestCase):
    comparisons=0;policies=0
    def probe(self,args,timeout_ms=1000,output_limit=8*1024*1024,missing=False):
        result=subprocess.run([str(FIXTURE),'probe'],input=json.dumps(dict(args=args,timeout_ms=timeout_ms,output_limit=output_limit,missing=missing)),capture_output=True,text=True,timeout=3)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'');return json.loads(result.stdout)
    def test_raw_output_arguments_utf8_and_crlf(self):
        for args in [['echo','alpha 日本語','a b',';$(literal)*~',''],['both'],['invalid'],['echo','x'*1024]]:
            reference=subprocess.run([str(FIXTURE),*args],capture_output=True,timeout=2)
            native=self.probe(args,output_limit=1024 if args[0]=='echo' and len(args[1])==1024 else 8*1024*1024)
            self.assertEqual(native,dict(return_code=reference.returncode,stdout=list(reference.stdout),stderr=list(reference.stderr)));type(self).comparisons+=1
        with tempfile.TemporaryDirectory(prefix='kwr-process-') as tmp:
            binary=Path(tmp)/'日本語 space fixture';shutil.copy2(FIXTURE,binary)
            result=subprocess.run([str(binary),'probe'],input=json.dumps(dict(args=['echo','日本語'],timeout_ms=1000,output_limit=1024)),capture_output=True,text=True,timeout=3)
            self.assertEqual(json.loads(result.stdout)['stdout'],list('日本語'.encode()));type(self).comparisons+=1
    def test_missing_deadline_combined_output_and_descendants(self):
        self.assertFalse(FIXTURE.with_name('missing-owned-fixture-executable').exists())
        self.assertEqual(self.probe([],missing=True)['error_kind'],'FileNotFoundError');type(self).policies+=1
        for mode in ['flood','stderr-flood']:
            started=time.monotonic();result=self.probe([mode],output_limit=1024)
            self.assertEqual(result['error_kind'],'OutputLimitError');self.assertLess(time.monotonic()-started,1.5);type(self).policies+=1
        self.assertEqual(self.probe(['both'],output_limit=32)['error_kind'],'OutputLimitError');type(self).policies+=1
        started=time.monotonic();result=self.probe(['sleep'],timeout_ms=80)
        self.assertEqual(result['error_kind'],'TimeoutExpired');self.assertLess(time.monotonic()-started,1.5);type(self).policies+=1
        with tempfile.TemporaryDirectory(prefix='kwr-owned-descendant-') as tmp:
            heartbeat=Path(tmp)/'heartbeat';result=self.probe(['descendant',str(heartbeat)],timeout_ms=150)
            self.assertEqual(result['error_kind'],'TimeoutExpired');self.assertTrue(heartbeat.exists())
            before=heartbeat.read_bytes();self.assertTrue(before);time.sleep(0.2)
            self.assertEqual(heartbeat.read_bytes(),before,'owned descendant continues after deadline');type(self).policies+=1
    def test_interrupt_terminates_owned_descendants(self):
        for received,kind in [(signal.SIGINT,'KeyboardInterrupt'),(signal.SIGTERM,'SignalError')]:
            with tempfile.TemporaryDirectory(prefix='kwr-owned-signal-') as tmp:
                heartbeat=Path(tmp)/'heartbeat'
                request=json.dumps(dict(args=['descendant',str(heartbeat)],timeout_ms=2000,output_limit=1024))
                child=subprocess.Popen([str(FIXTURE),'probe'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    child.stdin.write(request);child.stdin.close();child.stdin=None
                    until=time.monotonic()+1
                    while not heartbeat.exists() and time.monotonic()<until:time.sleep(0.01)
                    self.assertTrue(heartbeat.exists());child.send_signal(received)
                    output,errors=child.communicate(timeout=2);self.assertEqual(errors,'');self.assertEqual(json.loads(output)['error_kind'],kind)
                    before=heartbeat.read_bytes();time.sleep(0.15);self.assertEqual(heartbeat.read_bytes(),before);type(self).policies+=1
                finally:
                    if child.poll() is None:child.kill();child.wait(timeout=2)
if __name__=='__main__':
    if os.name!='posix':raise SystemExit('Native process safety is pending on this platform; do not treat as a passing gate')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProcessFixture));print('owned process comparisons:',ProcessFixture.comparisons,'policy assertions:',ProcessFixture.policies);raise SystemExit(not result.wasSuccessful())

#!/usr/bin/env python3
"""Combined Meta CLI: exact loopback hosts, owned processes and synthetic ledgers."""
import collections
import contextlib
import copy
import io
import json
import os
import select
import shutil
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
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import http_differential as fixture
import json_provider_differential as normal
import github_code_differential as code
from katala_web_research.archive import Archive
from katala_web_research.models import FeedItem, PageSnapshot
from katala_web_research import cli, providers

PROCESS = Path(os.environ.get("KWR_PROCESS_FIXTURE", fixture.ROOT / "target/debug/examples/process_fixture"))
META_PROBE = Path(os.environ.get("KWR_META_PROBE", fixture.ROOT / "target/debug/examples/meta_probe"))
REFERENCE = fixture.ROOT / "scripts/migration/meta_reference_fixture.py"
TRACE, PLAN = [], {}
MODEL_FIELDS = {"title","url","snippet","source","published_at","rank","score","metadata"}
MODEL_OBSERVATIONS = {"rows":0,"sources":{},"meta_run_fields":set()}
HOSTS = {"html.duckduckgo.com", "api.github.com", "api.openalex.org", "api.search.brave.com", "s.jina.ai", "localhost"}
REQUESTED = threading.Event()
TABLE_QUERIES = ["SELECT * FROM pages ORDER BY id", "SELECT * FROM runs ORDER BY id", "SELECT * FROM search_results ORDER BY id", "SELECT * FROM repo_documents ORDER BY id", "SELECT * FROM feed_sources ORDER BY id", "SELECT * FROM feed_items ORDER BY id", "SELECT * FROM project_items ORDER BY id"]

def preserved(path):
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return (conn.execute("PRAGMA user_version").fetchone()[0],
                [conn.execute(query).fetchall() for query in TABLE_QUERIES],
                conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall(),
                conn.execute("SELECT rowid,title,content FROM pages_fts ORDER BY rowid").fetchall())

def ledger(path):
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM engine_runs ORDER BY id")]

def volatile_times(value):
    if isinstance(value, list): return [volatile_times(v) for v in value]
    if not isinstance(value, dict): return value
    output = {}
    for key, data in value.items():
        if key in {"engine_latency_ms", "latency_ms"}:
            if not isinstance(data, int) or not 0 <= data <= 15000:
                raise AssertionError(("timing outside the child fixture deadline", key, data))
            # Full JSON/score is first checked against the Python oracle replayed
            # with this execution's measured clock and completion inputs.
            output[key] = "<measured-ms>"
        elif key == "recorded_at": output[key] = "<time>"
        else: output[key] = volatile_times(data)
    return output

def expected_at_measured_inputs(transcript,run_rows,env,args,library=False):
    """No network/process calls: feed actual timings/order to the Python algorithm.

    Raw component outputs are from the reference child; statuses/counts/error kinds
    must match native observations. No result/health/rank/score field is normalized.
    """
    requests=transcript["requests"];available=list(range(len(requests)));order=[]
    for row in run_rows:
        index=next(i for i in available if requests[i]["provider"]==row["provider"])
        available.remove(index);order.append(index)
    assert not available,("missing completions",available)
    mapped={index:row for index,row in zip(order,run_rows)}
    class Future:
        def __init__(self,index):self.index=index
        def result(self):
            recorded=transcript["outputs"][str(self.index)];observed=mapped[self.index]
            for key in ["status","result_count","error_kind"]:
                assert recorded["run"][key]==observed[key],("component changed",self.index,key,recorded,observed)
            run=providers._MetaEngineRun(provider=observed["provider"],status=observed["status"],latency_ms=observed["latency_ms"],result_count=observed["result_count"],error_kind=observed["error_kind"],health_score=providers._meta_engine_health_score(status=observed["status"],result_count=observed["result_count"],latency_ms=observed["latency_ms"],requested=requests[self.index]["limit"]))
            results=[providers.SearchResult(**copy.deepcopy(r)) for r in recorded["results"]]
            return [providers._annotate_engine_result(r,run) for r in results],run
    futures=[]
    class Pool:
        def __init__(self,max_workers):assert max_workers==min(len(requests),4)
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def submit(self,callback,provider,query,limit):
            index=len(futures);assert {"provider":provider,"query":query,"limit":limit}==requests[index]
            future=Future(index);futures.append(future);return future
    stdout=io.StringIO();stderr=io.StringIO()
    with patch.dict(os.environ,env,clear=True),patch.object(providers,"ThreadPoolExecutor",Pool),patch.object(providers,"as_completed",lambda _: [futures[i] for i in order]),patch.object(providers,"_route_around_weak_engines",lambda _: [r["provider"] for r in requests]),patch.object(providers,"_record_engine_runs",lambda _: None),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
        if library:
            params=args;value={"results":[r.to_dict() for r in providers.MetaSearch().search(params["query"],limit=params["limit"])]}
            print(json.dumps(value,ensure_ascii=False))
        else:assert cli.main(args)==0
    assert len(futures)==len(requests) and not stderr.getvalue(),stderr.getvalue()
    return stdout.getvalue()

class MetaHandler(fixture.Handler):
    def do_GET(self):
        parsed = urlsplit(self.path); params = parse_qs(parsed.query)
        provider = {"/html/": "ddg", "/search/repositories": "github", "/search/code": "github_code", "/search": "searxng", "/res/v1/web/search": "brave", "/works": "openalex", "/": "jina"}.get(parsed.path)
        if provider is None: self.send_error(404); return
        TRACE.append((provider, self.path, {k.lower():v for k,v in self.headers.items()})); REQUESTED.set()
        status = 200; mode = PLAN.get(provider, "normal")
        if mode == "slow": time.sleep(0.5)
        count = 0 if mode == "empty" else 2
        if provider == "ddg":
            body = "".join(f'<a class="result__a" href="https://docs.python.org/fixture{i}">alpha 日本語 docs {i}</a><div class="result__snippet">alpha 日本語 evidence</div>' for i in range(count)).encode()
            content_type = "text/html; charset=utf-8"
        else:
            rows = []
            for i in range(count):
                if provider == "github": rows.append({"full_name":f"fixture/alpha{i}","html_url":f"https://github.com/fixture/alpha{i}","description":"alpha 日本語 implementation","updated_at":"2026-01-02","stargazers_count":i,"fork":False})
                elif provider == "github_code": rows.append({"html_url":f"https://github.com/fixture/code/blob/main/item{i}.rs","name":f"alpha{i}.rs","path":f"src/alpha{i}.rs","repository":{"full_name":"fixture/code","description":"alpha 日本語 implementation"},"text_matches":[{"object_type":"FileContent","property":"content","fragment":"alpha 日本語 evidence"}]})
                elif provider == "openalex": rows.append({"id":f"https://openalex.org/W{i}","display_name":f"alpha 日本語 paper {i}","doi":f"https://doi.org/10.1/meta{i}","publication_date":"2026-01-02","publication_year":2026,"type":"article","cited_by_count":i,"abstract_inverted_index":{"alpha":[0],"日本語":[1],"evidence":[2]},"primary_location":{"landing_page_url":f"https://doi.org/10.1/meta{i}"}})
                else:
                    host = "vendor-docs.fixture.test" if provider == "searxng" else "institution.edu" if provider == "jina" else "generic.fixture.test"
                    row = {"url":f"https://{host}/alpha{i}","title":f"alpha 日本語 {provider} {i}"}
                    row["content" if provider == "searxng" else "description"] = "alpha 日本語 evidence"
                    rows.append(row)
            payload = {"items":rows} if provider in {"github","github_code"} else {"results":rows,"meta":{"next_cursor":None}} if provider=="openalex" else {"results":rows} if provider=="searxng" else {"web":{"results":rows}} if provider=="brave" else {"data":rows}
            body = json.dumps(payload,ensure_ascii=False).encode(); content_type="application/json; charset=utf-8"
        if mode == "error":status=503;body=(normal.PUBLIC_KEY+" synthetic error body").encode()
        if mode == "json-error":body=(normal.PUBLIC_KEY+" non-JSON").encode()
        self.send_response(status);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True

class MetaProxy(normal.JsonProxy):
    def do_CONNECT(self):
        host, port = self.path.rsplit(":",1)
        if host not in HOSTS or (host!="localhost" and port!="443"):
            self.send_error(403);return
        upstream=socket.create_connection(("127.0.0.1",self.tls_port),timeout=2)
        self.send_response(200,"Connection established");self.end_headers()
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

class MetaFixture(fixture.TlsAndProxy):
    additional_san=",DNS:html.duckduckgo.com,DNS:api.github.com,DNS:api.openalex.org,DNS:api.search.brave.com,DNS:s.jina.ai"
    comparisons=0; signal_policies=0
    @classmethod
    def setUpClass(cls):
        with patch.object(fixture,"Handler",MetaHandler),patch.object(fixture,"ProxyHandler",MetaProxy):super().setUpClass()
        MetaProxy.tls_port=cls.servers[1].server_port
    def seed(self,path,history=None):
        a=Archive(path);code.seed_history(a)
        a.upsert_feed_items([FeedItem("https://fixture.test/feed",f"https://feed.fixture.test/item{i}",f"alpha 日本語 feed {i}","alpha 日本語 evidence","Old feed",None,"fixed") for i in range(2)])
        a.upsert_page(PageSnapshot("https://docs.python.org/fixture0","Old docs","alpha 日本語 cached evidence. More context.","cached","fixed"))
        if history:
            for provider,runs in history.items():a.record_engine_runs([{"provider":provider,"status":status,"latency_ms":latency,"result_count":count,"error_kind":"FetchError" if status=="error" else ""} for status,latency,count in runs],keep_per_provider=1000)
        # Both test copies have the recognized v1 stamp; actual legacy refusal is a
        # separately measured migration policy. No production archive is rewritten.
        a.conn.execute("PRAGMA user_version=1");a.conn.commit();a.close()
    def environment(self,fakebin,unselected,extra):
        env=dict(self.env,PATH=str(fakebin),HTTPS_PROXY=self.proxy,SSL_CERT_FILE=str(self.ca_path),KWR_HTTP_TIMEOUT_SECONDS="2",KWR_ARCHIVE=str(unselected),KWR_SEARXNG_URL=self.tls,BRAVE_SEARCH_API_KEY=normal.PUBLIC_KEY,JINA_API_KEY=normal.PUBLIC_KEY,GITHUB_TOKEN=normal.PUBLIC_KEY,OPENALEX_API_KEY=normal.PUBLIC_KEY)
        env.update(extra or {});return env
    def compare(self,providers="ddg,github,openalex,searxng",profile="broad",options=None,extra=None,plan=None,gh=True,history=None,default=False,expected_providers=None,version=1):
        PLAN.clear();PLAN.update(plan or {});options=options or ["--json"]
        values=[];traces=[];runs=[];transcript=None
        with tempfile.TemporaryDirectory(prefix="kwr-meta-") as tmp:
            fakebin=Path(tmp)/"日本語 fixture bin";fakebin.mkdir()
            if gh:shutil.copy2(PROCESS,fakebin/"gh")
            for native in [False,True]:
                child_root=Path(tmp)/("native" if native else "reference");child_root.mkdir()
                archive=child_root/".katala-web-research/archive.sqlite" if default else child_root/"日本語 selected.sqlite"
                unselected=child_root/"unselected.sqlite";self.seed(unselected);unselected_before=normal.snapshot(unselected)
                self.seed(archive,history)
                if version != 1:
                    with sqlite3.connect(archive) as conn:conn.execute("PRAGMA user_version=0")
                before=preserved(archive);old=ledger(archive);old_max=max(r["id"] for r in old)
                env=self.environment(fakebin,unselected,dict(KWR_META_PROVIDERS=providers,KWR_META_PROFILE=profile,**(extra or {})))
                trace_file=child_root/"reference-components.json"
                prefix=[str(fixture.BINARY)] if native else [sys.executable,str(REFERENCE),str(trace_file)]
                start=len(TRACE);args=prefix+["search","alpha 日本語","--provider","meta",*options]
                if not default:args += ["--archive",str(archive)]
                result=subprocess.run(args,cwd=child_root,capture_output=True,text=True,env=env,timeout=15)
                self.assertEqual(result.returncode,0,(providers,profile,native,result.stderr));self.assertEqual(result.stderr,"")
                self.assertEqual(before,preserved(archive));self.assertEqual(unselected_before,normal.snapshot(unselected))
                if not default:self.assertFalse((child_root/".katala-web-research").exists())
                new=[r for r in ledger(archive) if r["id"]>old_max]
                self.assertEqual(sorted(r["id"] for r in new),list(range(old_max+1,old_max+len(new)+1)))
                if new:self.assertEqual(len({r["recorded_at"] for r in new}),1)
                if expected_providers is not None:self.assertEqual(collections.Counter(r["provider"] for r in new),collections.Counter(expected_providers))
                if not native:transcript=json.loads(trace_file.read_text())
                oracle_args=args[len(prefix):]
                if "--archive" not in oracle_args:oracle_args += ["--archive",str(archive)]
                expected=expected_at_measured_inputs(transcript,new,env,oracle_args)
                if "--json" in options:self.assertEqual(json.loads(result.stdout),json.loads(expected),(providers,profile,options,native))
                else:self.assertEqual(result.stdout,expected,(providers,profile,options,native))
                if native and "--json" in options:
                    for row in json.loads(result.stdout):
                        self.assertEqual(set(row),MODEL_FIELDS)
                        self.assertIsInstance(row["rank"],int);self.assertIsInstance(row["score"],(float,int));self.assertIsInstance(row["metadata"],dict)
                        MODEL_OBSERVATIONS["rows"]+=1
                        MODEL_OBSERVATIONS["sources"].setdefault(row["source"],set()).update(row["metadata"])
                        for run in row["metadata"]["meta_engine_runs"]:MODEL_OBSERVATIONS["meta_run_fields"].update(run)
                for r in new:r.pop("id")
                runs.append(sorted(volatile_times(new),key=lambda r:(r["provider"],r["status"],r["result_count"])))
                rows=ledger(archive)
                self.assertTrue(all(n<=500 for n in collections.Counter(r["provider"] for r in rows).values()))
                old_by_id={r["id"]:r for r in old}
                for row in rows:
                    if row["id"]<=old_max:self.assertEqual(row,old_by_id[row["id"]])
                values.append(volatile_times(json.loads(result.stdout)) if "--json" in options else result.stdout)
                traces.append(sorted((p,path,tuple((key,h.get(key)) for key in ["accept","authorization","x-subscription-token","x-github-api-version"])) for p,path,h in TRACE[start:]))
            self.assertEqual(*traces);self.assertEqual(*runs)
            type(self).comparisons+=1
            return values[0],runs[0],traces[0]
    def test_all_components_profiles_options_archive_and_metadata(self):
        all_names="ddg,github,github_code,searxng,brave,jina,openalex,feed"
        self.compare(all_names,expected_providers=all_names.split(","))
        self.compare(all_names,gh=False,expected_providers=all_names.split(","))
        for profile in ["broad","docs","scholarly","code","fresh","local","monitoring","unknown"," DOCS \u001c"]:self.compare("",profile)
        for options in [["--json"],["--category","research","--category","pdf","--json"],["--include-domain","github.com","--exclude-domain","other.test","--json"],["--highlight-top","3","--json"],["--limit","-1","--json"],["--limit","0","--json"],["--limit","1","--candidate-multiplier","1","--json"],["--limit","50","--candidate-multiplier","1","--json"],["--limit","2"]]:self.compare(all_names,options=options)
        self.compare("feed,ddg",default=True,expected_providers=["feed","ddg"])
        self.compare("ddg,github,ddg,unknown,meta",expected_providers=["ddg","github","ddg"])
        self.compare("unknown,meta",expected_providers=[])
        self.compare("ddg,github",version=0,expected_providers=["ddg","github"])
    def test_partial_empty_config_failures_routing_and_pruning(self):
        for plan in [{"ddg":"error"},{"openalex":"json-error"},{"ddg":"empty","searxng":"empty","openalex":"empty"},{"ddg":"error","searxng":"error","openalex":"error"},{"ddg":"slow"}]:self.compare("ddg,searxng,openalex",plan=plan,extra={"KWR_HTTP_TIMEOUT_SECONDS":"0.1"} if "slow" in plan.values() else None)
        self.compare("brave,github_code,searxng",extra={"BRAVE_SEARCH_API_KEY":"","GITHUB_TOKEN":"","KWR_SEARXNG_URL":""},expected_providers=["brave","github_code","searxng"])
        self.compare("ddg,github",extra={"KWR_HTTP_TIMEOUT_SECONDS":"bad"},expected_providers=["ddg","github"])
        bad=[("error",6000,0)]*6
        self.compare("ddg,github",history={"ddg":bad},expected_providers=["github"])
        self.compare("ddg,github",history={"ddg":bad,"github":bad},expected_providers=["ddg","github"])
        self.compare("ddg,github",history={"ddg":bad[:4]},expected_providers=["ddg","github"])
        self.compare("ddg,github",history={"ddg":bad*100,"github":bad*100},expected_providers=["ddg","github"])
    def test_library_no_health_ledger_without_named_archive(self):
        PLAN.clear();values=[];transcript=None
        with tempfile.TemporaryDirectory(prefix="kwr-meta-library-") as tmp:
            root=Path(tmp);fakebin=root/"bin";fakebin.mkdir()
            for native in [False,True]:
                cwd=root/("native" if native else "reference");cwd.mkdir()
                env=self.environment(fakebin,cwd/"must-not-exist.sqlite",{"KWR_META_PROVIDERS":"ddg,searxng"});env.pop("KWR_ARCHIVE")
                trace_file=root/"reference-components.json";params={"query":"alpha 日本語","limit":4,"archive":None}
                command=[str(META_PROBE)] if native else [sys.executable,str(REFERENCE),str(trace_file),"--library"]
                result=subprocess.run(command,input=json.dumps(params),cwd=cwd,env=env,capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,"");values.append(volatile_times(json.loads(result.stdout)))
                if not native:transcript=json.loads(trace_file.read_text())
                actual=json.loads(result.stdout)
                measured=actual["results"][0]["metadata"]["meta_engine_runs"]
                # These distinct URLs do not have completion-order representative
                # ties; either order yields the same Python output.
                expected=json.loads(expected_at_measured_inputs(transcript,measured,env,params,library=True))
                self.assertEqual(actual,expected)
                self.assertEqual(list(cwd.iterdir()),[])
            type(self).comparisons+=1
    def test_selected_directory_failure_and_legacy_refusal(self):
        with tempfile.TemporaryDirectory(prefix="kwr-meta-refusal-") as tmp:
            directory=Path(tmp)/"is-directory";directory.mkdir();fakebin=Path(tmp)/"bin";fakebin.mkdir()
            for native in [False,True]:
                start=len(TRACE);prefix=[str(fixture.BINARY)] if native else [sys.executable,"-m","katala_web_research.cli"]
                result=subprocess.run(prefix+["search","alpha","--provider","meta","--archive",str(directory),"--json"],env=self.environment(fakebin,directory,{"KWR_META_PROVIDERS":"ddg"}),capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,"");self.assertEqual(len(TRACE),start);self.assertNotIn(normal.PUBLIC_KEY,result.stderr)
            path=Path(tmp)/"legacy.sqlite";self.seed(path)
            with sqlite3.connect(path) as conn:conn.execute("PRAGMA user_version=2")
            before=normal.snapshot(path);start=len(TRACE)
            result=subprocess.run([str(fixture.BINARY),"search","alpha","--provider","meta","--archive",str(path),"--json"],env=self.environment(fakebin,path,{"KWR_META_PROVIDERS":"ddg"}),capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,"");self.assertEqual(before,normal.snapshot(path));self.assertEqual(len(TRACE),start)
    def test_graceful_signals_preserve_ledger_and_stop_owned_descendants(self):
        for sig in [signal.SIGINT,signal.SIGTERM]:
            for native in [False,True]:
                with tempfile.TemporaryDirectory(prefix="kwr-meta-signal-") as tmp:
                    root=Path(tmp);fakebin=root/"bin";fakebin.mkdir();shutil.copy2(PROCESS,fakebin/"gh")
                    path=root/"selected.sqlite";self.seed(path);before=normal.snapshot(path);heartbeat=root/"heartbeat"
                    env=self.environment(fakebin,path,{"KWR_META_PROVIDERS":"github,ddg","KWR_FIXTURE_GH_HEARTBEAT":str(heartbeat)})
                    PLAN.clear();PLAN["ddg"]="slow";REQUESTED.clear()
                    prefix=[str(fixture.BINARY)] if native else [sys.executable,"-m","katala_web_research.cli"]
                    child=subprocess.Popen(prefix+["search","fixture-meta-signal","--provider","meta","--archive",str(path),"--json"],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
                    try:
                        deadline=time.monotonic()+3
                        while time.monotonic()<deadline and (not heartbeat.exists() or heartbeat.stat().st_size<3):
                            if child.poll() is not None:self.fail("signal fixture exited before owned heartbeat")
                            time.sleep(0.01)
                        self.assertTrue(heartbeat.exists());self.assertTrue(REQUESTED.wait(timeout=1))
                        started=time.monotonic();os.killpg(child.pid,sig);stdout,stderr=child.communicate(timeout=3)
                        self.assertLess(time.monotonic()-started,2);self.assertEqual(stdout,"");self.assertNotIn(normal.PUBLIC_KEY,stderr)
                        self.assertEqual(child.returncode,(130 if sig==signal.SIGINT else 143) if native else -sig)
                        count=heartbeat.stat().st_size;time.sleep(0.06);self.assertEqual(heartbeat.stat().st_size,count)
                        self.assertEqual(before,normal.snapshot(path))
                        type(self).signal_policies+=1
                    finally:
                        if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.communicate(timeout=3)
    def test_empty_archive_and_old_schema_are_explicit(self):
        PLAN.clear();values=[]
        with tempfile.TemporaryDirectory(prefix="kwr-meta-schema-") as tmp:
            root=Path(tmp);fakebin=root/"bin";fakebin.mkdir();unselected=root/"unselected.sqlite";self.seed(unselected);before=normal.snapshot(unselected)
            for native in [False,True]:
                prefix=[str(fixture.BINARY)] if native else [sys.executable,"-m","katala_web_research.cli"]
                result=subprocess.run(prefix+["search","alpha 日本語","--provider","meta","--archive","","--json"],cwd=root,env=self.environment(fakebin,unselected,{"KWR_META_PROVIDERS":"feed,ddg"}),capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,"");values.append(volatile_times(json.loads(result.stdout)));self.assertEqual(before,normal.snapshot(unselected))
            self.assertEqual(*values);self.assertFalse((root/".katala-web-research").exists());type(self).comparisons+=1
            # Mirror the existing recognized pre-context schema, without asking the
            # Python Archive constructor to upgrade it before the refusal check.
            schema=(fixture.ROOT/"rust/src/schema.sql").read_text()
            for old,new in [("context TEXT NOT NULL DEFAULT '',",""),("file_size INTEGER NOT NULL DEFAULT 0,",""),("file_mtime_ns INTEGER NOT NULL DEFAULT 0,",""),("content_sha256 TEXT NOT NULL DEFAULT '',",""),("title, context, content","title, content"),("new.title, new.context, new.content","new.title, new.content"),("old.title, old.context, old.content","old.title, old.content")]:schema=schema.replace(old,new)
            legacy=root/"old-columns.sqlite"
            with sqlite3.connect(legacy) as conn:
                conn.executescript(schema)
                conn.execute("INSERT INTO repo_documents(repo_path,repo_name,rel_path,title,content,kind,indexed_at) VALUES ('/synthetic','fixture','old.rs','alpha','old evidence','rust','fixed')")
            prior=normal.snapshot(legacy);prior_bytes=legacy.read_bytes();start=len(TRACE)
            result=subprocess.run([str(fixture.BINARY),"search","alpha","--provider","meta","--archive",str(legacy),"--json"],cwd=root,env=self.environment(fakebin,unselected,{"KWR_META_PROVIDERS":"ddg"}),capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,1);self.assertEqual(result.stdout,"");self.assertEqual(len(TRACE),start);self.assertEqual(prior,normal.snapshot(legacy));self.assertEqual(prior_bytes,legacy.read_bytes())
    test_downgrade_rejected=None
    test_http_proxy_and_environment_boundaries=None
    test_https_connect_proxy=None
    test_tls_trust_and_hostname=None
    test_trusted_tls_cli=None

if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MetaFixture))
    print("Meta paired localhost CLI comparisons:",MetaFixture.comparisons,"signal policies:",MetaFixture.signal_policies)
    raise SystemExit(not result.wasSuccessful())

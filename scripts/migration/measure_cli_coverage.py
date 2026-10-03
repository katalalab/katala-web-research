#!/usr/bin/env python3
"""Measure existing paired CLI golden coverage; schemas are snapshots, not readiness."""
import dataclasses
import hashlib
import json
import unittest
from pathlib import Path
import differential
from katala_web_research import mcp_server,models

ROOT=Path(__file__).resolve().parents[2]
inventory=json.loads((ROOT/"docs/migration/python-contract.json").read_text())
assert mcp_server.TOOLS==inventory["mcp"]["tools"],"reference tool schemas changed"
assert mcp_server.PROTOCOL_VERSION==inventory["mcp"]["protocol"]
observed=[];last=[]
original_call=differential.Differential.call
original_parity=differential.Differential.parity
def call(self,command,native):
    result=original_call(self,command,native)
    last.append((command,native,result))
    return result
def parity(self,command,as_json=True):
    original_parity(self,command,as_json)
    pairs=last[-2:];assert pairs[0][1] is False and pairs[1][1] is True
    native=pairs[-1][2]
    row={"command":command,"json":as_json,"exit":native.returncode,"fields":[],"metadata":[]}
    if as_json:
        value=json.loads(native.stdout)
        if isinstance(value,dict):row["fields"]=sorted(value)
        elif isinstance(value,list):
            row["fields"]=sorted({k for item in value if isinstance(item,dict) for k in item})
            row["metadata"]=sorted({k for item in value if isinstance(item,dict) for k in item.get("metadata",{})})
    observed.append(row)
differential.Differential.call=call;differential.Differential.parity=parity
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(differential.Differential))
assert result.wasSuccessful(),"golden suite failed; no coverage artifact accepted"
assert differential.Differential.comparisons==218,"aggregate scope changed; inspect before accepting"
coverage=[]
for leaf in inventory["cli"]:
    prefix=leaf["command"].split();cases=[r for r in observed if r["command"][:len(prefix)]==prefix]
    flags={flag for arg in leaf["arguments"] for flag in arg["flags"]}
    exercised=sorted({arg for case in cases for arg in case["command"] if arg in flags})
    coverage.append({"command":leaf["command"],"strict_paired_cases_measured":len(cases),"json_cases":sum(r["json"] for r in cases),"text_cases":sum(not r["json"] for r in cases),"exercised_flags":exercised,"unmeasured_explicit_flags":sorted(flags-set(exercised)),"output_keys_observed":sorted({key for r in cases for key in r["fields"]}),"metadata_keys_observed":sorted({key for r in cases for key in r["metadata"]}),"scope_acceptance":"passed_measured_cases" if cases else "not_measured","full_ready":False})
h=hashlib.sha256()
for p in sorted([*ROOT.glob("rust/src/**/*.rs"),ROOT/"Cargo.toml",ROOT/"Cargo.lock",ROOT/"rust-toolchain.toml"],key=lambda p:p.relative_to(ROOT).as_posix()):h.update(p.relative_to(ROOT).as_posix().encode()+b"\0"+p.read_bytes()+b"\0")
payload={"reference":inventory["baseline"],"source_tree_sha256":h.hexdigest(),"target":"aarch64-apple-darwin","executor":"author; actual target only","aggregate_cli_comparisons":differential.Differential.comparisons,"strict_parity_hook_cases":len(observed),"inventoried_leaf_cases":sum(row["strict_paired_cases_measured"] for row in coverage),"root_version_cases":sum(row["command"]==["--version"] for row in observed),"coverage":coverage,"search_result_fields":sorted(f.name for f in dataclasses.fields(models.SearchResult)),"mcp":{"reference_tools":len(mcp_server.TOOLS),"reference_snapshot_equal":True,"schemas":mcp_server.TOOLS,"native_tools_implemented":0,"native_protocol_executed":False,"scope_acceptance":"reference_schema_snapshot_only","full_ready":False},"complete_migration":False}
(ROOT/"docs/migration/cli-coverage.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
print("CLI coverage:",len(coverage),"inventoried leaves;",len(observed),"strict paired cases measured;",differential.Differential.comparisons,"aggregate; native MCP 0/9; full_ready=false")

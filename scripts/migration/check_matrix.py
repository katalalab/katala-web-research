#!/usr/bin/env python3
"""Validate the final-gate inventory; no runtime, credentials or network."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
inventory=json.loads((ROOT/'docs/migration/python-contract.json').read_text())
matrix=json.loads((ROOT/'docs/migration/golden-matrix.json').read_text())
rows=matrix['rows']
assert len({r['id'] for r in rows})==len(rows),'duplicate gate IDs'
assert matrix['reference']==inventory['baseline'],'reference mismatch'
expected={c['command'] for c in inventory['cli']}
assert {r['surface'] for r in rows if r['id'].startswith('cli:')}==expected,'missing/extra CLI leaf'
search=next(c for c in inventory['cli'] if c['command']=='search')
providers=next(a['choices'] for a in search['arguments'] if a['dest']=='provider')
assert {r['surface'] for r in rows if r['id'].startswith('provider:')}==set(providers)-{'feed'},'missing/extra network provider'
for row in rows:
    assert row['required_cases'] and row['final_acceptance'] in ['pending','passed'],row['id']
    if row['final_acceptance']=='pending':
        assert row.get('pending_reasons') and all(row['pending_reasons']),row['id']
        assert row.get('missing_assertions') and all(row['missing_assertions']),row['id']
        assert row.get('next_tests') and row.get('close_when'),row['id']
        for test in row['next_tests']:
            assert test['status'] in ['proposed','blocked'] and not test['execution_evidence'],row['id']
            assert test['assertions'] and test['planned_file'] and test['id'],row['id']
        assert row['scope_acceptance']['full_ready'] is False,row['id']
    else:
        assert not row.get('pending_reasons'),row['id']
    cases=row.get('case_evidence',[])
    assert len({case['id'] for case in cases})==len(cases),row['id']
    for case in cases:
        assert case['status'] in ['pending','passed'] and case['scope'] and case['evidence'],row['id']
        assert all((ROOT/path).is_file() for path in case['evidence']),(row['id'],case['id'],'missing evidence')
        if case['status']=='passed':
            assert case['target'] and case['executor'] and case['source_tree_sha256'] and case['count']>0,case['id']
if matrix['complete_migration']:
    assert all(r['final_acceptance']=='passed' for r in rows),'complete migration still has pending gates'
print('golden matrix:',len(expected),'commands,',len(providers)-1,'network providers,',len(rows),'total rows; complete =',matrix['complete_migration'])
print('scoped passed case records:',sum(case['status']=='passed' for row in rows for case in row.get('case_evidence',[])),'final pending rows:',sum(row['final_acceptance']=='pending' for row in rows))

map_path=ROOT/"docs/migration/mcp-tool-dependencies.json"
if map_path.is_file():
    dependencies=json.loads(map_path.read_text());tools=dependencies["tools"]
    assert {t["name"] for t in tools}=={t["name"] for t in inventory["mcp"]["tools"]},"missing/extra MCP mapping"
    assert len(tools)==dependencies["reference_tool_count"]==9
    mapped={i for t in tools for i in t["rows"]}|set(dependencies["non_mcp_command_rows"])
    assert mapped=={r["id"] for r in rows},("MCP/standalone gate mapping mismatch",mapped^{r["id"] for r in rows})
    assert dependencies["native_tools_implemented"]==0 and not dependencies["complete_migration"]
    print("MCP dependencies: all9 schemas mapped; all35 rows accounted for; native0/9")

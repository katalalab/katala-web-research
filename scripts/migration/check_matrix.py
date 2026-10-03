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
if matrix['complete_migration']:
    assert all(r['final_acceptance']=='passed' for r in rows),'complete migration still has pending gates'
print('golden matrix:',len(expected),'commands,',len(providers)-1,'network providers,',len(rows),'total rows; complete =',matrix['complete_migration'])

#!/usr/bin/env python3
"""Capture public contracts from the Python reference without network or user data."""
import argparse
import ast
import dataclasses
import hashlib
import json
import re
import tempfile
from pathlib import Path
from katala_web_research.archive import Archive
from katala_web_research.cli import build_parser
from katala_web_research import models, mcp_server

ROOT = Path(__file__).resolve().parents[2]

def commands(parser, prefix=()):
    rows = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                rows.extend(commands(child, (*prefix, name)))
    if 'func' in parser._defaults:
        rows.append({'command': ' '.join(prefix), 'handler': parser._defaults['func'].__name__,
            'arguments': [{'dest': a.dest, 'flags': a.option_strings, 'required': a.required,
                'default': a.default, 'choices': a.choices, 'type': getattr(a.type, '__name__', None),
                'action': type(a).__name__} for a in parser._actions if a.dest != 'help']})
    return rows

def capture():
    files, env, handlers = [], {}, {}
    for path in sorted((ROOT / 'src/katala_web_research').glob('*.py')):
        source = path.read_text(encoding='utf-8')
        files.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(source.encode()).hexdigest()})
        for lineno, line in enumerate(source.splitlines(), 1):
            for name in re.findall(r'\b(?:KWR|OPENALEX|BRAVE|JINA|GITHUB)_[A-Z_]+\b', line):
                env.setdefault(name, []).append(f'{path.name}:{lineno}')
        if path.name == 'cli.py':
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.FunctionDef) and node.name.startswith('cmd_'):
                    handlers[node.name] = {'line': node.lineno, 'json_keys': sorted({k.value
                        for d in ast.walk(node) if isinstance(d, ast.Dict) for k in d.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}),
                        'returns': [ast.unparse(n.value) for n in ast.walk(node) if isinstance(n, ast.Return)]}
    with tempfile.TemporaryDirectory(prefix='kwr-contract-') as directory:
        archive = Archive(Path(directory) / 'synthetic.sqlite')
        schema = [dict(row) for row in archive.conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")]
        version = archive.conn.execute('PRAGMA user_version').fetchone()[0]
        archive.close()
    return {'baseline': 'e66e449cc210bd80ecb25a00391091e72abd9c2b',
        'cli': commands(build_parser()), 'handlers': handlers, 'environment_references': env,
        'models': {name: [{'name': f.name, 'type': str(f.type)} for f in dataclasses.fields(cls)]
            for name, cls in vars(models).items() if isinstance(cls, type) and dataclasses.is_dataclass(cls)},
        'mcp': {'protocol': mcp_server.PROTOCOL_VERSION, 'tools': mcp_server.TOOLS},
        'sqlite': {'user_version': version, 'schema': schema}, 'sources': files}

if __name__ == '__main__':
    value = json.dumps(capture(), ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    (ROOT / 'docs/migration/python-contract.json').write_text(value, encoding='utf-8')

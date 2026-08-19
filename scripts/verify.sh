#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== compile =="
PYTHONPATH=src python3 -m compileall -q src tests

echo "== unit tests =="
PYTHONPATH=src python3 -m unittest discover -s tests

echo "== cli smoke =="
PYTHONPATH=src python3 -m katala_web_research.cli doctor >/tmp/katala-web-research-doctor.txt
grep -q "sqlite_fts5: ok" /tmp/katala-web-research-doctor.txt
rm -f /tmp/katala-web-research-doctor.txt
PYTHONPATH=src python3 -m katala_web_research.cli plan "agentic retrieval source quality" --max-subqueries 2 >/tmp/katala-web-research-plan.txt
grep -q "official:" /tmp/katala-web-research-plan.txt
rm -f /tmp/katala-web-research-plan.txt
PYTHONPATH=src python3 -m katala_web_research.cli eval --min-score 80 --out /tmp/katala-web-research-eval.md >/tmp/katala-web-research-eval.txt
grep -q "passed: true" /tmp/katala-web-research-eval.txt
grep -q "Research Quality Benchmark" /tmp/katala-web-research-eval.md
rm -f /tmp/katala-web-research-eval.txt /tmp/katala-web-research-eval.md
PYTHONPATH=src python3 -m katala_web_research.cli sources list --domain security --json >/tmp/katala-web-research-sources.txt
grep -q "CISA Known Exploited Vulnerabilities Catalog" /tmp/katala-web-research-sources.txt
rm -f /tmp/katala-web-research-sources.txt
PYTHONPATH=src python3 -m katala_web_research.cli sources match "https://www.cisa.gov/known-exploited-vulnerabilities-catalog" --json >/tmp/katala-web-research-source-match.txt
grep -q '"matched": true' /tmp/katala-web-research-source-match.txt
rm -f /tmp/katala-web-research-source-match.txt
feed_smoke_dir="$(mktemp -d)"
trap 'rm -rf "$feed_smoke_dir"' EXIT
feed_smoke_archive="$feed_smoke_dir/archive.sqlite"
# $ROOT is an MSYS path under Git Bash, which is not a resolvable file:// URL on
# Windows; as_uri() spells the repo-relative fixture natively on every platform.
feed_smoke_url="$(python3 -c 'import pathlib; print(pathlib.Path("tests/fixtures/sample.rss.xml").resolve().as_uri())')"
PYTHONPATH=src python3 -m katala_web_research.cli feeds add "$feed_smoke_url" --archive "$feed_smoke_archive" >/tmp/katala-web-research-feed-add.txt
grep -q "source_count: 1" /tmp/katala-web-research-feed-add.txt
PYTHONPATH=src python3 -m katala_web_research.cli feeds refresh --archive "$feed_smoke_archive" >/tmp/katala-web-research-feed-refresh.txt
grep -q "indexed_items: 2" /tmp/katala-web-research-feed-refresh.txt
PYTHONPATH=src python3 -m katala_web_research.cli search "RSSHub" --provider feed --archive "$feed_smoke_archive" >/tmp/katala-web-research-feed-search.txt
grep -q "RSSHub adapter research" /tmp/katala-web-research-feed-search.txt
rm -f /tmp/katala-web-research-feed-add.txt /tmp/katala-web-research-feed-refresh.txt /tmp/katala-web-research-feed-search.txt

echo "== token budget benchmark =="
scripts/benchmark-token-budget.py

echo "== research quality benchmark =="
scripts/benchmark-research-quality.py --iterations 30 --out /tmp/katala-web-research-quality.md >/tmp/katala-web-research-quality.txt
grep -q "all_passed: true" /tmp/katala-web-research-quality.txt
grep -q "Deterministic Multi-Run Evaluation" /tmp/katala-web-research-quality.md
rm -f /tmp/katala-web-research-quality.txt /tmp/katala-web-research-quality.md

echo "== .env secret pattern guard =="
# Allowed in .env: op:// references and plain public emails.
# Reject any line that looks like a raw secret token or key.
if [ -f "$ROOT/.env" ]; then
  bad_lines="$(grep -nE '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)' "$ROOT/.env" || true)"
  if [ -n "$bad_lines" ]; then
    echo "Refusing: .env contains raw secret pattern (sk-, ghp_, AKIA, private key header)" >&2
    echo "$bad_lines" >&2
    exit 1
  fi
fi

echo "== tracked artifact guard =="
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  tracked_sensitive="$(git ls-files -- . | grep -E '(^|/)(raw|downloads|sessions|logs?)/|\.env($|\.)|\.jsonl$|\.sqlite(-shm|-wal)?$|\.log$|__pycache__|\.pyc|\.DS_Store' | grep -vE '(^|/)\.env\.example$' || true)"
  if [ -n "$tracked_sensitive" ]; then
    echo "Refusing: tracked raw/runtime/sensitive artifact found" >&2
    echo "$tracked_sensitive" >&2
    exit 1
  fi
fi

echo "katala-web-research verification passed"

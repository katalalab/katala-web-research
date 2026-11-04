#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# A private directory prevents concurrent runs from overwriting each other's output.
# TMPDIR can be set to an isolated workspace by the caller.
scratch="$(mktemp -d "${TMPDIR:-/tmp}/katala-web-research-verify.XXXXXXXX")"
cleanup() {
  # Avoid following an obvious replacement of the directory with a symlink.
  # A private TMPDIR is still required: this check cannot prevent a later swap.
  if [ -L "$scratch" ] || [ ! -d "$scratch" ]; then
    echo "Refusing to clean replaced temporary directory: $scratch" >&2
    return 1
  fi
  rm -f -- "$scratch"/doctor.txt "$scratch"/plan.txt "$scratch"/eval.md "$scratch"/eval.txt \
    "$scratch"/sources.txt "$scratch"/source-match.txt "$scratch"/feed-add.txt \
    "$scratch"/feed-refresh.txt "$scratch"/feed-search.txt "$scratch"/quality.md \
    "$scratch"/quality.txt "$scratch"/archive.sqlite "$scratch"/archive.sqlite-wal \
    "$scratch"/archive.sqlite-shm "$scratch"/archive.sqlite-journal
  rmdir -- "$scratch"
}
trap cleanup EXIT

echo "== compile =="
PYTHONPATH=src python3 -m compileall -q src tests

echo "== unit tests =="
PYTHONPATH=src python3 -m unittest discover -s tests

echo "== cli smoke =="
PYTHONPATH=src python3 -m katala_web_research.cli doctor >"$scratch/doctor.txt"
grep -q "sqlite_fts5: ok" "$scratch/doctor.txt"
PYTHONPATH=src python3 -m katala_web_research.cli plan "agentic retrieval source quality" --max-subqueries 2 >"$scratch/plan.txt"
grep -q "official:" "$scratch/plan.txt"
PYTHONPATH=src python3 -m katala_web_research.cli eval --min-score 80 --out "$scratch/eval.md" >"$scratch/eval.txt"
grep -q "passed: true" "$scratch/eval.txt"
grep -q "Research Quality Benchmark" "$scratch/eval.md"
PYTHONPATH=src python3 -m katala_web_research.cli sources list --domain security --json >"$scratch/sources.txt"
grep -q "CISA Known Exploited Vulnerabilities Catalog" "$scratch/sources.txt"
PYTHONPATH=src python3 -m katala_web_research.cli sources match "https://www.cisa.gov/known-exploited-vulnerabilities-catalog" --json >"$scratch/source-match.txt"
grep -q '"matched": true' "$scratch/source-match.txt"
feed_smoke_archive="$scratch/archive.sqlite"
# $ROOT is an MSYS path under Git Bash, which is not a resolvable file:// URL on
# Windows; as_uri() spells the repo-relative fixture natively on every platform.
feed_smoke_url="$(python3 -c 'import pathlib; print(pathlib.Path("tests/fixtures/sample.rss.xml").resolve().as_uri())')"
PYTHONPATH=src python3 -m katala_web_research.cli feeds add "$feed_smoke_url" --archive "$feed_smoke_archive" >"$scratch/feed-add.txt"
grep -q "source_count: 1" "$scratch/feed-add.txt"
PYTHONPATH=src python3 -m katala_web_research.cli feeds refresh --archive "$feed_smoke_archive" >"$scratch/feed-refresh.txt"
grep -q "indexed_items: 2" "$scratch/feed-refresh.txt"
PYTHONPATH=src python3 -m katala_web_research.cli search "RSSHub" --provider feed --archive "$feed_smoke_archive" >"$scratch/feed-search.txt"
grep -q "RSSHub adapter research" "$scratch/feed-search.txt"

echo "== token budget benchmark =="
scripts/benchmark-token-budget.py

echo "== research quality benchmark =="
scripts/benchmark-research-quality.py --iterations 30 --out "$scratch/quality.md" >"$scratch/quality.txt"
grep -q "all_passed: true" "$scratch/quality.txt"
grep -q "Deterministic Multi-Run Evaluation" "$scratch/quality.md"

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

echo "== gitleaks =="
if command -v gitleaks >/dev/null 2>&1; then
  gitleaks dir "$ROOT" --no-banner --redact
else
  # A silent skip here is worse than no check: it reads as a clean scan in the log.
  echo "SKIP: gitleaks not installed (install it or run the scan on a node that has it)"
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

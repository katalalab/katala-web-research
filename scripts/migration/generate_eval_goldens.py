#!/usr/bin/env python3
"""Freeze repository-owned Python eval fixtures; never used by the Rust runtime."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

from katala_web_research import evaluation

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "rust/tests/fixtures/evaluation-cases.json"
GOLDEN = ROOT / "rust/tests/fixtures/evaluation-golden.json"
PYTHON = [sys.executable, "-m", "katala_web_research.cli"]


def call(args: list[str]) -> dict:
    env = os.environ.copy()
    env.pop("KWR_SOURCE_REGISTRY_OVERLAY", None)
    proc = subprocess.run(PYTHON + ["eval", *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", check=False)
    assert proc.stderr == "", proc.stderr
    return {"args": args, "exit": proc.returncode, "stdout": proc.stdout}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare without writing, using the committed fixture year")
    args = parser.parse_args()
    year = json.loads(CASES.read_text(encoding="utf-8"))["year"] if args.check else datetime.now(timezone.utc).year
    previous_year = evaluation.CURRENT_YEAR
    try:
        evaluation.CURRENT_YEAR = year
        cases = [asdict(case) for case in evaluation.default_eval_cases()]
    finally:
        evaluation.CURRENT_YEAR = previous_year
    cases_text = json.dumps(
            {"year": year, "cases": cases},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    golden_text = json.dumps(
            [
                call([]),
                call(["--json"]),
                call(["--min-score", "50", "--max-subqueries", "1", "--json"]),
                call(["--min-score", "90", "--max-subqueries", "1", "--json"]),
                call(["--min-score", "-1", "--max-subqueries", "-5", "--json"]),
            ],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    for path, content in [(CASES, cases_text), (GOLDEN, golden_text)]:
        if args.check:
            if path.read_bytes() != content.encode("utf-8"):
                raise SystemExit(f"Python reference differs: {path.relative_to(ROOT)}")
        else:
            path.write_text(content, encoding="utf-8")
    print("Python evaluation fixtures match" if args.check else "Python evaluation fixtures regenerated")


if __name__ == "__main__":
    main()

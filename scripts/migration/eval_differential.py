#!/usr/bin/env python3
"""Compare unchanged Python and native eval CLI output without network access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
NATIVE = Path(os.environ.get("KWR_RUST_BINARY", ROOT / "target/debug/kwr-rs"))
PYTHON = [sys.executable, "-m", "katala_web_research.cli"]
CASES = [
    [],
    ["--json"],
    ["--min-score", "50", "--max-subqueries", "1", "--json"],
    ["--min-score", "90", "--max-subqueries", "1", "--json"],
    ["--min-score", "-1", "--max-subqueries", "-5", "--json"],
]


class EvalDifferential(unittest.TestCase):
    def call(self, root: Path, native: bool, args: list[str]) -> subprocess.CompletedProcess[str]:
        command = [str(NATIVE)] if native else PYTHON
        env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
        env.pop("KWR_SOURCE_REGISTRY_OVERLAY", None)
        return subprocess.run(command + ["eval", *args], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", check=False)

    def test_stdout_stderr_and_status_match_python(self) -> None:
        self.assertTrue(NATIVE.is_file(), NATIVE)
        for args in CASES:
            with tempfile.TemporaryDirectory(prefix="kwr-eval-diff-") as temp:
                root = Path(temp)
                python = self.call(root, False, args)
                native = self.call(root, True, args)
                self.assertEqual(native.returncode, python.returncode, args)
                self.assertEqual(native.stdout, python.stdout, args)
                self.assertEqual(native.stderr, python.stderr, args)

    def test_markdown_report_bytes_match_python(self) -> None:
        for options, expected_status in [([], 0), (["--min-score", "90", "--max-subqueries", "1", "--json"], 1)]:
            with self.subTest(options=options), tempfile.TemporaryDirectory(prefix="kwr-eval-report-") as temp:
                root = Path(temp)
                python_root, native_root = root / "python", root / "native"
                python_root.mkdir()
                native_root.mkdir()
                report = Path("reports/nested/research-quality.md")
                args = ["--out", str(report), *options]
                python = self.call(python_root, False, args)
                native = self.call(native_root, True, args)
                self.assertEqual(python.returncode, expected_status)
                self.assertEqual(native.returncode, python.returncode)
                self.assertEqual(native.stdout, python.stdout)
                self.assertEqual(native.stderr, python.stderr)
                self.assertEqual((native_root / report).read_bytes(), (python_root / report).read_bytes())


if __name__ == "__main__":
    raise SystemExit(not unittest.main(verbosity=2, exit=False).result.wasSuccessful())

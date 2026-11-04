from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class VerifyTemporaryFilesTest(unittest.TestCase):
    def test_preserves_legacy_file_and_allows_overlapping_runs(self):
        bash = (r"C:\Program Files\Git\bin\bash.exe" if os.name == "nt" else shutil.which("bash"))
        if bash and not Path(bash).is_file():
            bash = None
        if not bash:
            self.skipTest("bash is required by scripts/verify.sh")
        original = Path(__file__).resolve().parents[1] / "scripts/verify.sh"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            self.assertTrue(root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            for directory in ("scripts", "bin", "legacy", "tmp space", "barrier", "src", "tests"):
                (root / directory).mkdir()
            # Redirect only legacy hard-coded filenames into this synthetic fixture.
            # Neither version touches the machine's real shared /tmp.
            legacy_prefix = (root / "legacy/katala-web-research-").as_posix()
            script = original.read_text(encoding="utf-8").replace("/tmp/katala-web-research-", legacy_prefix)
            (root / "scripts/verify.sh").write_text(script, encoding="utf-8", newline="\n")
            sentinel = root / "legacy/katala-web-research-doctor.txt"
            sentinel.write_text("preserve this existing file\n", encoding="utf-8")
            stub = '''#!/usr/bin/env bash
set -eu
if [[ "${KWR_TEST_FAIL:-}" == '1' && " $* " == *" doctor "* ]]; then exit 7; fi
if [[ " $* " == *" doctor "* ]]; then
  for ((attempt=0; attempt<200; attempt++)); do
    dirs=("$TMPDIR"/katala-web-research-verify.*)
    if [[ ${#dirs[@]} == 2 && -d "${dirs[0]}" && -d "${dirs[1]}" ]]; then
      printf '%s\\n' "${dirs[@]}" > "$KWR_BARRIER_DIR/$PPID"
      break
    fi
    sleep 0.05
  done
  [[ -f "$KWR_BARRIER_DIR/$PPID" ]] || exit 8
  for ((attempt=0; attempt<200; attempt++)); do
    markers=("$KWR_BARRIER_DIR"/*)
    [[ ${#markers[@]} == 2 && -f "${markers[0]}" && -f "${markers[1]}" ]] && break
    sleep 0.05
  done
  [[ ${#markers[@]} == 2 && -f "${markers[0]}" && -f "${markers[1]}" ]] || exit 9
fi
if [[ " $* " == *" -c "* ]]; then echo 'file:///synthetic/feed.xml'; exit 0; fi
prev=''
for arg in "$@"; do
  if [[ "$prev" == '--out' ]]; then printf '%s\\n' 'Research Quality Benchmark' 'Deterministic Multi-Run Evaluation' > "$arg"; fi
  prev="$arg"
done
printf '%s\\n' 'sqlite_fts5: ok' 'official:' 'passed: true' 'CISA Known Exploited Vulnerabilities Catalog' '"matched": true' 'source_count: 1' 'indexed_items: 2' 'RSSHub adapter research' 'all_passed: true'
'''
            for path in (root / "bin/python3", root / "scripts/benchmark-token-budget.py", root / "scripts/benchmark-research-quality.py"):
                path.write_text(stub, encoding="utf-8", newline="\n")
                path.chmod(0o755)
            system_path = r"C:\Program Files\Git\usr\bin;C:\Windows\System32" if os.name == "nt" else "/usr/bin:/bin"
            env = {"PATH": str(root / "bin") + os.pathsep + system_path,
                   "HOME": str(root), "USERPROFILE": str(root), "TMPDIR": (root / "tmp space").as_posix(),
                   "TEMP": str(root / "tmp space"), "TMP": str(root / "tmp space"),
                   "KWR_BARRIER_DIR": (root / "barrier").as_posix()}
            if "SystemRoot" in os.environ:
                env["SystemRoot"] = os.environ["SystemRoot"]

            def run():
                return subprocess.run([bash, str(root / "scripts/verify.sh")], cwd=root, env=env,
                                      capture_output=True, text=True, timeout=30)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: run(), range(2)))
            self.assertTrue(sentinel.is_file(), "verifier removed the existing legacy file")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve this existing file\n")
            for result in results:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("katala-web-research verification passed", result.stdout)
            barriers = list((root / "barrier").iterdir())
            self.assertEqual(len(barriers), 2)
            paths = [set(p.read_text(encoding="utf-8").splitlines()) for p in barriers]
            self.assertEqual(paths[0], paths[1])
            self.assertEqual(len(paths[0]), 2)
            self.assertEqual(list((root / "tmp space").iterdir()), [])
            env["KWR_TEST_FAIL"] = "1"
            failed = run()
            self.assertEqual(failed.returncode, 7, failed.stdout + failed.stderr)
            self.assertEqual(list((root / "tmp space").iterdir()), [])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve this existing file\n")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Native help assertion; no network, credentials or archive initialization."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BINARY = Path(os.environ.get("KWR_RUST_BINARY",ROOT/"target/debug/kwr-rs"))
with tempfile.TemporaryDirectory(prefix="kwr-enrichment-help-") as tmp:
    root = Path(tmp)
    env = {"PATH":os.environ.get("PATH",""),"KWR_HTTP_TIMEOUT_SECONDS":"invalid",
           "KWR_META_PROVIDERS":"invalid","KWR_ARCHIVE":str(root/"missing"/"archive.sqlite")}
    result = subprocess.run([str(BINARY),"search","--help"],cwd=root,env=env,
                            capture_output=True,text=True,timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stderr == "", result.stderr
    help_text = " ".join(result.stdout.split())
    assert "--enrich-top <ENRICH_TOP>" in help_text
    assert "Disabled for positive values pending safe handling of URLs returned by search; use 0 to skip enrichment" in help_text
    assert list(root.iterdir()) == [], "help initialized runtime data"
print("native enrichment help: disabled-positive scope, exit0/stdout-only, no runtime data")

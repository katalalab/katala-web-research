#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export CARGO_BUILD_JOBS=1
scripts/rust.sh build --locked --offline --bin kwr-rs
PYTHONPATH=src python3 scripts/migration/github_code_differential.py

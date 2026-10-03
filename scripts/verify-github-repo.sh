#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export CARGO_BUILD_JOBS=1
scripts/rust.sh build --locked --offline --bin kwr-rs --example process_fixture
PYTHONPATH=src python3 scripts/migration/process_differential.py
PYTHONPATH=src python3 scripts/migration/github_repo_differential.py

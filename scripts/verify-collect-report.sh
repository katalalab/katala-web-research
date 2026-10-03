#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export CARGO_BUILD_JOBS=1
scripts/rust.sh test --locked --offline --test report
scripts/rust.sh build --locked --offline --bin kwr-rs
PYTHONPATH=src python3 scripts/migration/collect_report_differential.py

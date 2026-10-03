#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export CARGO_BUILD_JOBS=1
scripts/rust.sh build --locked --offline --bin kwr-rs --example process_fixture --example meta_probe
PYTHONPATH=src python3 scripts/migration/meta_differential.py

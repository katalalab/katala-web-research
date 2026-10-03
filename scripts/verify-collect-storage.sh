#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export CARGO_BUILD_JOBS=1
scripts/rust.sh test --locked --offline --test collect_storage
scripts/rust.sh build --locked --offline --example store_run_probe
PYTHONPATH=src python3 scripts/migration/collect_storage_differential.py

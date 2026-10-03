#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export CARGO_BUILD_JOBS=1
python3 scripts/migration/check_matrix.py
scripts/rust.sh build --locked --offline --bin kwr-rs
PYTHONPATH=src python3 scripts/migration/json_provider_edge_differential.py

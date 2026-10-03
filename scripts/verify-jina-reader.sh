#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export CARGO_BUILD_JOBS=1
scripts/rust.sh build --locked --offline --bin kwr-rs
scripts/rust.sh test --locked --offline --test reader
PYTHONPATH=src python3 scripts/migration/jina_reader_differential.py

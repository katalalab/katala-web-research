#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Fetch registry dependencies once before using this offline gate.
scripts/rust.sh fmt -- --check
scripts/rust.sh clippy --locked --offline --all-targets -- -D warnings
scripts/rust.sh test --locked --offline
scripts/rust.sh build --locked --offline
PYTHONPATH=src python3 scripts/migration/differential.py

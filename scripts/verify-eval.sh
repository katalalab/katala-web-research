#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
env KWR_SOURCE_REGISTRY_OVERLAY=/nonexistent PYTHONPATH=src python3 -B scripts/migration/generate_eval_goldens.py --check
scripts/rust.sh test --locked --offline --test evaluation
scripts/rust.sh build --locked --offline --bin kwr-rs
env -u KWR_SOURCE_REGISTRY_OVERLAY KWR_RUST_BINARY="${KWR_RUST_BINARY:-${CARGO_TARGET_DIR:-$ROOT/target}/debug/kwr-rs}" PYTHONPATH=src python3 scripts/migration/eval_differential.py

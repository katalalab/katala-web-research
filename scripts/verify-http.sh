#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
# Local socket fixture gate only: no provider, credentials, installs or OS trust
# changes. Python >=3.11 and an existing OpenSSL CLI are prerequisites.
scripts/rust.sh build --locked --offline --bin kwr-rs --example http_probe
PYTHONPATH=src python3 scripts/migration/http_differential.py

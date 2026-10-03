# Reproducible Rust preview and copy migration

This is the first native migration slice, not a complete replacement. The Python `kwr` entry point remains the production/reference command. Rust builds `kwr-rs`; it never invokes Python. Python is used only by the development differential test harness. See [parity](parity.md) for every remaining command and [ledger](ledger.md) for actual verification evidence.

## Setup and build

Use Rust **1.96.0** (MSRV also 1.96), `rust-toolchain.toml`, committed Cargo.lock, and a platform C compiler for bundled SQLite. Use the standard rustup installer only if Rust is absent, after reviewing https://rustup.rs; this task did not install or modify system tooling. If rustup is already installed but lacks the pinned version:

```sh
rustup toolchain install 1.96.0 --profile minimal --component rustfmt --component clippy
cargo +1.96.0 fetch --locked
```

With a shell that prioritizes Homebrew Rust, `scripts/rust.sh` selects the pinned cargo, rustc, rustdoc, and clippy explicitly. On Unix:

```sh
scripts/rust.sh fetch --locked
scripts/verify-rust.sh
scripts/rust.sh build --release --locked --offline
./target/release/kwr-rs plan 'agent evidence' --json
```

Registry fetch is a one-time prerequisite; the gate itself uses `--offline --locked`. It performs formatting, clippy, native migration/golden tests, build, and CLI differential tests. The Python reference requires Python >=3.11; run `scripts/verify.sh` as the existing repository gate.

Windows PowerShell equivalent (design instructions; not executed on Windows):

```powershell
$env:RUSTC = (rustup which --toolchain 1.96.0 rustc)
$env:RUSTDOC = (rustup which --toolchain 1.96.0 rustdoc)
$env:PATH = (Split-Path $env:RUSTC) + ';' + $env:PATH
cargo fmt -- --check
cargo clippy --locked --offline --all-targets -- -D warnings
cargo test --locked --offline
cargo build --locked --offline
$env:PYTHONPATH = 'src'
python scripts/migration/differential.py
```

Supply a C compiler (Visual Studio Build Tools on Windows; platform SDK/cc on macOS/Linux) for SQLite. No Windows/Linux execution or certificate/proxy/signal validation is claimed. No installer or global CLI replacement is included. The current CI workflows are unchanged to avoid adding runners or costs; Rust gates are local until the review decides how to integrate them into the existing CI budget.

Dependencies are pinned transitively in Cargo.lock. `dependency-licenses.json` lists registry package names, versions, and declared license expressions; permissive MIT/Apache alternatives are selected where multiple options exist (including the optional LGPL alternative). No paid runtime/API/model dependency was introduced. Release distribution must include the project's LICENSE and required dependency notices from the locked registry packages. Do not publish a cross-platform release until actual target gates, attribution packaging, and review pass. Current release build is a local preview only.

## Native commands in this slice

- `plan`, `sources list`, `sources match`
- `query`, `repos query`, `feeds query`, `issues query`
- `feeds add`, `engines`
- `read --cache` for an existing page only; uncached reads, refreshes, and cache misses fail clearly
- new `migrate --source PATH --destination PATH [--dry-run]` emits a JSON validation report

All other reference commands remain available through Python and are pending in Rust. Parser diagnostics/help intentionally use clap wording; argument errors retain exit 2, runtime errors exit 1, success exit 0. JSON/UTF-8 outputs and supported command text outputs are compared with the reference. Numeric CLI arguments are signed 64-bit; arbitrary-size Python integers and invalid Unix filename bytes are not certified for parity.

## Synthetic copy migration

Do not use a real archive during development. Generate a small synthetic source:

```sh
PYTHONPATH=src python3 -c 'from katala_web_research.archive import Archive; a=Archive("/tmp/kwr-synthetic.sqlite"); a.close()'
./target/debug/kwr-rs migrate --source /tmp/kwr-synthetic.sqlite --destination /tmp/kwr-preview.sqlite --dry-run
./target/debug/kwr-rs migrate --source /tmp/kwr-synthetic.sqlite --destination /tmp/kwr-preview.sqlite
./target/debug/kwr-rs query evidence --archive /tmp/kwr-preview.sqlite --json
```

The source opens read-only, takes a coherent SQLite read snapshot, and uses the backup API to include committed WAL pages. Migration operates in a private temporary file beside the destination, with an atomic SQLite transaction and FTS external-content integrity checks. Existing row values are checked with typed, length-delimited SHA-256 fingerprints; row counts and schema hashes are returned. A no-clobber publish and fsync protect the chosen destination. Source database and WAL byte preservation are tested on synthetic inputs. `source_unchanged` describes content within that coherent snapshot; it is not a promise that another concurrent writer cannot modify the source afterward. Standard SQLite read-only WAL access can use shared-memory sidecars; live data is outside this task's execution scope.

Version 0 is accepted only for the exact reference schema or the explicitly recognized pre-metadata/context repository schema. The latter adds file_size, file_mtime_ns, content_sha256, context and rebuilds only the repository FTS index on the copy. An already upgraded legacy column order is recognized. Version 1 is the same compatible data schema with an explicit user_version stamp. Future versions, unknown objects/triggers/defaults, and other legacy variants are rejected for manual analysis. FTS shadow-table DDL is included in schema recognition; bundled SQLite was tested against the local Python SQLite reference. Additional SQLite versions require verification.

A dry-run validates a temporary copy and removes it without publishing the destination. Rerunning a version-1 source into a **new** destination performs the same data/schema-preserving checks; an existing destination always fails without overwrite. Normal abort/error rolls back and cleans the temporary file. A process kill or power loss before publication can leave an unnamed `.tmp*` copy/journal in the chosen directory; it is never adopted automatically or treated as migrated output. Retry with a new unused destination; inspect/remove only the known abandoned synthetic temporary files after confirming no process owns them. Hard-kill/power-loss recovery remains unverified.

Rollback is to continue using the untouched source with Python; tests also reopen the migrated copy with Python and compare retrieval. No CLI/default path switch, automatic source delete, backup overwrite, or in-place rollback is provided. Changes written later to a copy must be reconciled separately before any future production cutover.

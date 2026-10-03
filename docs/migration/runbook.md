# Reproducible Rust preview and copy migration

This is a partial native migration preview, not a complete replacement. The Python `kwr` entry point remains the production/reference command. Rust builds `kwr-rs`; it never invokes Python. Python is used only by the development differential test harness. See [parity](parity.md) for every remaining command and [ledger](ledger.md) for actual verification evidence.

## Setup and build

Use Rust **1.96.0** (MSRV also 1.96), `rust-toolchain.toml`, committed Cargo.lock, and a platform C compiler for bundled SQLite. Use the standard rustup installer only if Rust is absent, after reviewing https://rustup.rs; this task did not install or modify system tooling. If rustup is already installed but lacks the pinned version:

```sh
rustup toolchain install 1.96.0 --profile minimal --component rustfmt --component clippy
scripts/rust.sh fetch --locked
```

With a shell that prioritizes Homebrew Rust, `scripts/rust.sh` selects the pinned cargo, rustc, rustdoc, and clippy explicitly. On Unix:

```sh
scripts/rust.sh fetch --locked
CARGO_BUILD_JOBS=1 scripts/verify-rust.sh
CARGO_BUILD_JOBS=1 scripts/verify-http.sh
scripts/verify-providers.sh
scripts/verify-json-providers.sh
scripts/verify-provider-edges.sh
CARGO_BUILD_JOBS=1 scripts/rust.sh build --release --locked --offline
./target/release/kwr-rs plan 'agent evidence' --json
```

Registry fetch is a one-time prerequisite; the gates use `--offline --locked`. The Rust gate performs formatting, clippy, native migration/golden tests, build, and CLI differential tests. The separate HTTP gate uses unauthenticated loopback servers/proxy and temporary synthetic TLS certificates, requiring an already installed OpenSSL CLI. It performs no provider request, install, or OS trust change. The Python reference requires Python >=3.11; run `scripts/verify.sh` as the existing repository gate.

The provider gate checks the complete golden matrix and uses synthetic TLS/proxy mappings to test the unchanged DDG endpoint/request path against Python. Only the exact fixture DDG CONNECT target maps to a loopback server; other targets are rejected, with no external DNS/provider request. Its CA is process-local and temporary. No authentication/API/model cost or OS trust change. Run build gates sequentially with CARGO_BUILD_JOBS=1 and record source/fixture/log sizes against min(10% starting free space, 2 GiB), and monitor owned build targets separately; remove only idle recoverable self-generated cache when needed.

The JSON-provider gate additionally runs only loopback SearXNG and exact Brave/Jina TLS proxy mappings. Regenerate its oracle with `PYTHONPATH=src python3 scripts/migration/generate_json_provider_goldens.py`; expected values come from the unchanged Python reference. For owned worktree cache reuse, set absolute CARGO_TARGET_DIR, KWR_RUST_BINARY and KWR_HTTP_PROBE paths because differential cases can change their working directory. Do not run different worktree builds concurrently against one target.

Windows PowerShell equivalent (design instructions; not executed on Windows):

```powershell
$env:RUSTC = (rustup which --toolchain 1.96.0 rustc)
$env:RUSTDOC = (rustup which --toolchain 1.96.0 rustdoc)
$env:PATH = (Split-Path $env:RUSTC) + ';' + $env:PATH
$env:CARGO_BUILD_JOBS = '1'
cargo fmt -- --check
cargo clippy --locked --offline --all-targets -- -D warnings
cargo test --locked --offline
cargo build --locked --offline
$env:PYTHONPATH = 'src'
python scripts/migration/differential.py
cargo build --locked --offline --example http_probe
python scripts/migration/http_differential.py
python scripts/migration/check_matrix.py
python scripts/migration/provider_differential.py
python scripts/migration/json_provider_differential.py
python scripts/migration/json_provider_edge_differential.py
```

Supply a C compiler (Visual Studio Build Tools on Windows; platform SDK/cc on macOS/Linux) for SQLite. No Windows/Linux execution or certificate/proxy/signal validation is claimed. No installer or global CLI replacement is included. The current CI workflows are unchanged to avoid adding runners or costs; Rust gates are local until the review decides how to integrate them into the existing CI budget.

Dependencies are pinned transitively in Cargo.lock. `dependency-licenses.json` lists registry package names, versions, and declared license expressions; permissive MIT/Apache alternatives are selected where multiple options exist (including the optional LGPL alternative). No paid runtime/API/model dependency was introduced. Release distribution must include the project's LICENSE and required dependency notices from the locked registry packages. Do not publish a cross-platform release until actual target gates, attribution packaging, and review pass. Current release build is a local preview only.

## Native commands in this slice

- `plan`, `sources list`, `sources match`
- `query`, `repos query`, `feeds query`, `issues query`
- `feeds add`, `engines`
- `feeds refresh` with `file://`, `http://`, `https://`, normal RSS/Atom/JSONFeed; HTTP bounds/security differences and pending transport edges are recorded in [http-contract.md](http-contract.md)
- `search QUERY --provider feed` over the selected local archive, query filters/candidate oversampling and cached-page highlights
- `search QUERY` / `--provider ddg` fetches ordinary DDG HTML, normalizes links/title/snippet, ranks and applies existing query/category/candidate/highlight/slicing behavior; this explicitly opts into HTTP. Four other network providers and positive enrichment remain unsupported. Malformed HTML/tokenizer and unusual transport edges plus all live DDG behavior remain unverified.
- `search --provider searxng`, `brave` or `jina` implements normal JSON requests, config, pagination, result/rank/CLI fields with existing environment-only settings. Live use explicitly opts into HTTP and existing service cost posture; migration verification uses synthetic values only. Full edges and doctor preflight remain pending, detailed in [provider-contract.md](provider-contract.md).
- `read --cache` for an existing page only; uncached reads, refreshes, and cache misses fail clearly
- new `migrate --source PATH --destination PATH [--dry-run]` emits a JSON validation report

Example offline feed loop (synthetic destination only):

```sh
fixture_url="$(python3 -c 'from pathlib import Path; print(Path("tests/fixtures/sample.rss.xml").resolve().as_uri())')"
./target/debug/kwr-rs feeds refresh --source "$fixture_url" --archive /tmp/kwr-feed-preview.sqlite --json
./target/debug/kwr-rs search RSSHub --provider feed --archive /tmp/kwr-feed-preview.sqlite --json
```

The parser's normal RSS/Atom/JSONFeed fields are covered by committed Python goldens. Internal XML DTD/entity declarations remain unsupported, matching roxmltree's default rejection; unusual dates, malformed non-string JSON fields, ill-formed HTML/tokenizer edges, native file URL edge cases, and injected database-write failures require further reference fixtures before claiming full parser/refresh parity. Fetching local files currently reads the complete file as the reference does; file byte limits belong to a separately reviewed contract change. HTTP defaults to 8 MiB response bytes, at most 10 redirects, and a single 20-second total deadline (KWR_HTTP_TIMEOUT_SECONDS overrides the positive finite duration). It rejects HTTPS downgrades and URL userinfo, strips sensitive headers on cross-origin redirects, and does not retry. These intentional safety differences can reject inputs accepted by Python. Previous feed items remain on failure. Full charset/URL/OS proxy compatibility and all live sources remain unverified.

Regenerate synthetic parser/query/highlight/ranking fixtures with `PYTHONPATH=src python3 scripts/migration/generate_feed_goldens.py`; ranking uses an explicit fixture year. Do not regenerate expected values from Rust.

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

A dry-run validates a temporary copy and removes it without publishing the destination. Rerunning a version-1 source into a **new** destination performs the same data/schema-preserving checks; an existing destination body or SQLite `-wal`/`-shm`/`-journal` entry (including a dangling symlink) always fails without overwrite. The namespace is rechecked immediately before publication, and a detected sidecar appearing during publication causes failure while preserving all files. Use a quiescent destination directory; this API cannot force unrelated concurrent writers to cooperate. Normal abort/error rolls back and cleans the temporary file. A process kill or power loss before publication can leave an unnamed `.tmp*` copy/journal in the chosen directory; it is never adopted automatically or treated as migrated output. Retry with a new unused destination; inspect/remove only the known abandoned synthetic temporary files after confirming no process owns them. Hard-kill/power-loss recovery remains unverified.

Rollback is to continue using the untouched source with Python; tests also reopen the migrated copy with Python and compare retrieval. No CLI/default path switch, automatic source delete, backup overwrite, or in-place rollback is provided. Changes written later to a copy must be reconciled separately before any future production cutover.

## Meta preview evidence

Build with the installed pinned toolchain and locked offline dependencies:

```sh
CARGO_BUILD_JOBS=1 scripts/rust.sh build --locked --offline --bin kwr-rs --example process_fixture --example meta_probe
PYTHONPATH=src python3 scripts/migration/meta_differential.py
PYTHONPATH=src python3 scripts/migration/measure_meta_metadata.py
python3 scripts/migration/update_acceptance_plan.py
python3 scripts/migration/check_matrix.py
CARGO_BUILD_JOBS=1 scripts/rust.sh build --locked --offline --release --bin kwr-rs
```

`scripts/verify-meta.sh` builds and executes the combined loopback fixture. With an
owned shared target, set CARGO_TARGET_DIR plus KWR_RUST_BINARY, KWR_PROCESS_FIXTURE
and KWR_META_PROBE to its exact debug executable paths; run builds serially. The
coverage scripts execute tests, not just inspect source: measure_cli_coverage.py runs
218 offline baseline comparisons, records observed flags/outputs and reference MCP
schemas only. No native MCP protocol/tools are implemented. Use the committed
coverage artifact to review successful evidence without needlessly rerunning gates.
Meta oracle replay does no I/O and checks full output at each child's measured timing/
completion inputs; read meta-contract.md before interpreting the scope. No live API,
real archive or authentication store is part of these tests. All final acceptance
rows stay pending; proposed test filenames are not executed evidence. Installed CLI
replacement and production migration remain unauthorized.

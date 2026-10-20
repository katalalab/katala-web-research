# Native Evaluation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an offline `kwr-rs eval` preview with Python-reference output and quality-gate parity.

**Architecture:** Bundle repository-owned synthetic cases, reuse the existing native planner/ranker/registry, and emit the same summary and Markdown report. Python remains the unchanged development oracle; native evaluation never launches it.

**Tech Stack:** Rust 1.96, existing clap/serde/serde_json dependencies, Python unittest.

## Task 1: Capture the missing-command failure

- [x] Register `rust/tests/evaluation.rs` in Cargo.toml and assert `eval --json` exits zero and emits JSON.
- [x] Run `CARGO_TARGET_DIR=/private/tmp/kwr-eval-red scripts/rust.sh test --locked --offline --test evaluation` before implementation; clap rejected the unknown command.

## Task 2: Add native evaluation and reference fixtures

- [x] Create `rust/src/evaluation.rs`, exported from `rust/src/lib.rs`, with `run(min_score: i64, max_subqueries: i64, registry: &Registry) -> Result<Summary>` and `report(summary: &Summary) -> String`.
- [x] Reuse native `planner::plan`, `search::rank`, and `search::classify` for fixed synthetic cases from the unchanged Python default benchmark.
- [x] Generate `evaluation-cases.json` and `evaluation-golden.json` through `scripts/migration/generate_eval_goldens.py`.
- [x] Cover MRR, recall, graded nDCG, and rejection when ranking ties the provider-order baseline. Preserve signed CLI subquery behavior and ties-to-even score rounding.

## Task 3: Connect CLI and report semantics

- [x] Add `eval --min-score --max-subqueries --out --json` to `rust/src/main.rs`; a failed quality gate emits the result before returning exit 1.
- [x] Reproduce the missing-parent report regression, then create nonempty parents before writing.
- [x] Compare stdout/stderr/status and nested Markdown bytes against Python for both success and quality failure using `scripts/migration/eval_differential.py`.
- [x] Remove ambient registry overlays from default golden generation and comparisons. Keep runtime overlay support intact.

## Task 4: Preserve reproducibility and CI coverage

- [x] Add `--check` to the generator. Use the committed fixture year, compare bytes without source writes, and run with an invalid ambient overlay in `scripts/verify-eval.sh`.
- [x] Add the pinned Rust `rust-evaluation` CI job with existing action SHAs, read-only permissions, two build jobs, and a thirty-minute timeout.
- [x] Document native preview scope and separate CI definition from actual Linux execution in the migration runbook and evaluation contract.

## Task 5: Final evidence and delivery

- [x] Run pinned formatting/clippy/all Rust tests, eval differential and repository verifier after the final fixes.
- [x] Preserve the first three-workflow measurement as preliminary evidence and add a source-bound replay driver to the delivery evidence. Final acceptance requires a rebuilt release and fifteen alternating pairs per workflow with matching statuses/outputs/reports and source/binary/oracle/driver hashes.
- [ ] Obtain independent review of the final source snapshot; create the PR and apply the canonical exact-head merge gate. A CI or required-review blocker remains incomplete and must not be bypassed.

**Rollback:** Revert the native evaluation change; Python `kwr eval` remains the installed/default command. No real archive or live provider is used.

# Native `eval` preview contract

`kwr-rs eval` is an offline preview of the unchanged Python `kwr eval` benchmark. It reads the repository-owned synthetic cases bundled in `rust/tests/fixtures/evaluation-cases.json`; the fixture generator is derived from this MIT-licensed repository's unchanged `src/katala_web_research/evaluation.py`.

The command accepts `--min-score` (default `80`), signed `--max-subqueries` (default `4`), `--out PATH`, and `--json`. It preserves all summary and case JSON fields, text output, Markdown report bytes, and exit status: accepted quality exits `0`, while a score or ranking-quality failure still writes its result and exits `1`.

The fixture records its UTC generation year. Native ranking uses that same year for freshness, so the synthetic results do not change as calendar time advances. `generate_eval_goldens.py --check` regenerates cases with that recorded year and compares both files without writing. The offline gate runs this check with an invalid ambient registry overlay to prove the default oracle ignores that setting. The native runtime does not launch Python. Python is used only to regenerate goldens and by the development-only differential test.

The ranking gate requires aggregate `ndcg@10` to be strictly greater than provider-order `baseline_ndcg@10`; equality fails even if the numeric score threshold is met. Evaluation covers score thresholds, signed subquery limits, relevance labels, quality ranking and Markdown rendering. Live providers, real research archives, Windows and Linux execution remain unverified.

Run the preview gate with:

```sh
CARGO_TARGET_DIR=/private/tmp/kwr-eval CARGO_BUILD_JOBS=2 scripts/verify-eval.sh
```

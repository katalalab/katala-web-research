# Native evaluation preview design

The Rust preview currently lacks the deterministic `eval` command used to judge research quality. Connect its existing native planner, ranker and registry to repository-owned benchmark cases rather than introducing another search implementation.

The unchanged Python command defines summary JSON, text, report bytes, default threshold 80, signed subquery limits, and success/failure status. Preserve the provider-order comparison: equal aggregate nDCG fails even at an otherwise acceptable score. Report output creates missing parents, including when the evaluation returns failure. Bundled synthetic cases retain their recorded year; fixture checks use that year to remain reproducible.

The native runtime reads bundled cases and the existing optional registry overlay. It never invokes Python, requests a provider, or opens an archive. Writing a report is explicit through `--out`. Python is a development oracle only. The Python default entry point is retained.

The selected approach extends the existing native library and CLI. A separate evaluator binary would duplicate parser/registry policy, while invoking Python would retain its runtime dependency and invalidate a native migration. No new dependency is needed.

Acceptance requires a failing missing-command regression before implementation; exact differential outputs and process statuses; metric and provider-order tests; nested report success/failure cases; hermetic golden regeneration; locked native/repository checks; independent exact-source review; and startup-inclusive paired performance samples bound to hashes. CI definition, CI success, repository integration, and runtime acceptance are separate evidence. Live providers, real archives and additional OS targets remain outside this preview's verified scope.

# Operations

This is the day-to-day operating surface for `katala-web-research`.

## Normal Research Cycle

Use the wrapper script when you want the standard flow:

```sh
scripts/kwr-research-cycle.sh "OpenAI Agents SDK handoffs"
```

It performs:

1. incremental scan of `~/Documents/GitHub`
2. bounded query decomposition
3. web search
4. local repository evidence lookup
5. selected page capture
6. SQLite archive write
7. Markdown investigation report

Defaults:

- archive: `~/.kwr/research.sqlite`
- report: `reports/<query-slug>.md`
- provider: `ddg`
- reader: `auto`
- web results: 8
- repo hits: 6
- captured pages: 2
- expanded queries: enabled

## Useful Overrides

```sh
KWR_MAX_REPOS=50 KWR_MAX_FILES=20 \
scripts/kwr-research-cycle.sh "browser automation research" reports/browser-automation.md
```

```sh
KWR_PROVIDER=github KWR_READ_TOP=0 \
scripts/kwr-research-cycle.sh "agent research tools"
```

Run local metasearch across configured engines:

```sh
KWR_PROVIDER=meta KWR_META_PROVIDERS=ddg,github,openalex \
op run --env-file=.env -- scripts/kwr-research-cycle.sh "research agent evaluation metrics"
```

Use a profile when the source mix is known:

```sh
KWR_PROVIDER=meta KWR_META_PROFILE=scholarly \
op run --env-file=.env -- scripts/kwr-research-cycle.sh "rank fusion retrieval benchmark"
```

Pass SearXNG API controls through when using a private instance:

```sh
KWR_SEARXNG_LANGUAGE=ja KWR_SEARXNG_TIME_RANGE=month KWR_SEARXNG_SAFESEARCH=1 \
kwr search "SearXNG engine settings" --provider searxng --limit 5
```

Disable query decomposition when you need a single exact query:

```sh
KWR_EXPAND_QUERIES=0 scripts/kwr-research-cycle.sh "exact release title"
```

## Optional Provider Boundary And Rollback Controls

Every optional provider is off until an environment variable turns it on, and every one of them is plain `urllib.request` — `dependencies = []` in `pyproject.toml`, so turning a provider off removes the whole code path from a run without a reinstall.

| Provider | Turn on with | Roll back by | Effect when off |
| --- | --- | --- | --- |
| `github_code` | `GITHUB_TOKEN` | unset it | provider raises `FetchError`; `meta` drops it from the fan-out |
| `jina` | `JINA_API_KEY` | unset it | same; the reader still works without a key |
| `brave` | `BRAVE_SEARCH_API_KEY` | unset it | same |
| `searxng` | `KWR_SEARXNG_URL` | unset it | same |
| `openalex` | none (key optional) | unset `OPENALEX_API_KEY` | falls back to the unauthenticated pool |
| engine health ledger | any `--archive` | omit `--archive`, or delete the `engine_runs` rows | no ledger is written and no engine is routed around |

Secret handling:

- `OPENALEX_API_KEY` accepts an `op://` reference and is resolved through `op read` at call time; nothing is written to disk. The other keys are read straight from the environment, so run them under `op run --env-file=.env`.
- OpenAlex only accepts its key as an `api_key=` query parameter, so the credential is unavoidably in the request URL. `redact_url()` strips it (and any basic-auth userinfo) from every error message before it can reach a log or a report.
- `.env` is gitignored and `scripts/verify.sh` refuses a tracked `.env`, a raw `sk-`/`ghp_`/`AKIA`/private-key pattern inside it, and any tracked runtime artifact.

License boundary: SearXNG is AGPL and is only ever reached over HTTP at `KWR_SEARXNG_URL`. No SearXNG source is vendored into this MIT tree, and `tests/test_provider_boundaries.py` fails if an `import searx` ever appears under `src/`.

## Token Budget Benchmark

Run the deterministic local benchmark:

```sh
scripts/benchmark-token-budget.py
```

Run against the real `Documents/GitHub` corpus:

```sh
scripts/benchmark-token-budget.py --root ~/Documents/GitHub
```

Run the optional live web benchmark:

```sh
scripts/benchmark-token-budget.py --root ~/Documents/GitHub --live-web
```

The benchmark estimates tokens from emitted text and generated reports. It fails when output exceeds the defined budget. This is a practical guard against accidentally dumping full captured pages or huge JSON payloads into agent context.

## Output Discipline

- Prefer `--out <file>` for `brief` and `investigate`; stdout stays short.
- Use `kwr plan` before expensive investigations when you want to inspect the fan-out.
- Keep `--read-top` small, usually `1-3`.
- Use `kwr query` for follow-up retrieval instead of re-running large web captures.
- Use `kwr repos scan` incrementally before important research.
- Use `--json` only for automation that will consume structured output; JSON can include larger payloads.

## Verification

```sh
scripts/verify.sh
scripts/benchmark-token-budget.py
PYTHONPATH=src python3 -m katala_web_research.cli eval --out /tmp/kwr-eval.md
```

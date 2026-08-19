#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from katala_web_research.evaluation import default_eval_cases, run_eval  # noqa: E402
from katala_web_research.providers import openalex_expand, search  # noqa: E402

EVAL_CASES = default_eval_cases()
THEMES = [case.query for case in EVAL_CASES]
LIVE_THEMES = THEMES[:3]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--out", default="docs/research-quality-benchmark.md")
    parser.add_argument("--json-out")
    parser.add_argument("--live-openalex", action="store_true")
    parser.add_argument("--live-meta", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    eval_runs = [run_eval(min_score=80) for _ in range(args.iterations)]
    token_runs = run_token_budget()
    live_runs = run_live_openalex(args.limit) if args.live_openalex else []
    expand_runs = run_live_openalex_expand(args.limit) if args.live_openalex else []
    meta_runs = run_live_meta(args.limit) if args.live_meta else []
    payload = {
        "iterations": args.iterations,
        "case_count": len(eval_runs[0].cases) if eval_runs else 0,
        "scores": [run.score for run in eval_runs],
        "min_score": min(run.score for run in eval_runs),
        "max_score": max(run.score for run in eval_runs),
        "mean_score": round(statistics.mean(run.score for run in eval_runs), 2),
        "category_scores": aggregate_category_scores(eval_runs),
        "all_passed": all(run.passed for run in eval_runs),
        "themes": THEMES,
        "token_budget": token_runs,
        "live_openalex": live_runs,
        "live_openalex_expand": expand_runs,
        "live_meta": meta_runs,
    }
    report = build_report(payload)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    if args.json_out:
        json_out = Path(args.json_out)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"report: {out}")
    print(f"iterations: {payload['iterations']}")
    print(f"mean_score: {payload['mean_score']}")
    print(f"all_passed: {str(payload['all_passed']).lower()}")
    if live_runs:
        print(f"live_openalex_runs: {len(live_runs)}")
    if meta_runs:
        print(f"live_meta_runs: {len(meta_runs)}")
    token_passed = all(row.get("ok") for row in token_runs)
    return 0 if payload["all_passed"] and token_passed else 1


def run_token_budget() -> list[dict]:
    completed = subprocess.run(
        # Windows cannot exec a shebang script directly, so name the interpreter.
        [sys.executable, str(ROOT / "scripts" / "benchmark-token-budget.py"), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return [
            {
                "name": "benchmark-token-budget",
                "ok": False,
                "error": (completed.stderr or completed.stdout).strip()[:500],
            }
        ]
    return json.loads(completed.stdout)


def run_live_openalex(limit: int) -> list[dict]:
    rows = []
    for theme in LIVE_THEMES:
        try:
            results = live_search_with_retry(theme, provider="openalex", limit=limit)
            rows.append(
                {
                    "theme": theme,
                    "ok": True,
                    "result_count": len(results),
                    "top_url": results[0].url if results else "",
                    "top_score": results[0].score if results else 0,
                }
            )
        except Exception as exc:
            rows.append({"theme": theme, "ok": False, "error": str(exc)})
    return rows


def run_live_openalex_expand(limit: int) -> list[dict]:
    """Expand the citation graph around whatever the first live OpenAlex query returned.

    Seeding from the live result instead of a pinned work id keeps the entry from rotting
    the day that id is merged or withdrawn.
    """
    try:
        seeds = live_search_with_retry(LIVE_THEMES[0], provider="openalex", limit=1)
    except Exception as exc:
        return [{"seed": LIVE_THEMES[0], "ok": False, "error": str(exc)}]
    if not seeds:
        return [{"seed": LIVE_THEMES[0], "ok": False, "error": "no seed work returned"}]
    seed = seeds[0].metadata.get("openalex_id") or seeds[0].url
    try:
        expanded = openalex_expand(seed, limit=limit)
    except Exception as exc:
        return [{"seed": seed, "ok": False, "error": str(exc)}]
    return [
        {
            "seed": seed,
            "ok": True,
            "referenced_count": len(expanded.get("referenced", [])),
            "citing_count": len(expanded.get("citing", [])),
        }
    ]


def run_live_meta(limit: int) -> list[dict]:
    rows = []
    for theme in LIVE_THEMES:
        try:
            results = live_search_with_retry(theme, provider="meta", limit=limit)
            source_counts: dict[str, int] = {}
            for result in results:
                source_counts[result.source] = source_counts.get(result.source, 0) + 1
            rows.append(
                {
                    "theme": theme,
                    "ok": True,
                    "result_count": len(results),
                    "source_counts": source_counts,
                    "top_url": results[0].url if results else "",
                    "top_score": results[0].score if results else 0,
                }
            )
        except Exception as exc:
            rows.append({"theme": theme, "ok": False, "error": str(exc)})
    return rows


def live_search_with_retry(theme: str, *, provider: str, limit: int) -> list:
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            return search(theme, provider=provider, limit=limit)
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("live search failed")


def build_report(payload: dict) -> str:
    lines = [
        "# Research Quality Benchmark Log",
        "",
        f"- date: {date.today().isoformat()}",
        "- scope: deterministic local evaluation plus optional OpenAlex/meta live checks",
        "- network required: no for deterministic eval; yes for `--live-openalex` or `--live-meta`",
        "- gate command: `scripts/verify.sh`",
        "",
        "## Deterministic Multi-Run Evaluation",
        "",
        f"- iterations: {payload['iterations']}",
        f"- case_count: {payload['case_count']}",
        f"- min_score: {payload['min_score']}",
        f"- max_score: {payload['max_score']}",
        f"- mean_score: {payload['mean_score']}",
        f"- all_passed: {str(payload['all_passed']).lower()}",
        "",
        "## Domain Category Scores",
        "",
    ]
    for category, scores in sorted(payload["category_scores"].items()):
        lines.append(f"- {category}: min={scores['min']} max={scores['max']} mean={scores['mean']}")
    lines.extend(
        [
            "",
            "## Themes",
            "",
        ]
    )
    for theme in payload["themes"]:
        lines.append(f"- {theme}")
    lines.extend(["", "## Token Budget Benchmark", ""])
    for row in payload["token_budget"]:
        if row.get("ok"):
            lines.append(
                f"- ok `{row['name']}` approx_tokens={row['approx_tokens']} budget={row['budget_tokens']} chars={row['chars']}"
            )
        else:
            lines.append(f"- fail `{row.get('name', 'unknown')}` error={row.get('error', '')}")
    lines.extend(["", "## Live OpenAlex", ""])
    if payload["live_openalex"]:
        for row in payload["live_openalex"]:
            if row["ok"]:
                lines.append(
                    f"- ok `{row['theme']}` count={row['result_count']} top_score={row['top_score']} top={row['top_url']}"
                )
            else:
                lines.append(f"- fail `{row['theme']}` error={row['error']}")
    else:
        lines.append("Not run in this benchmark pass.")
    lines.extend(["", "## Live OpenAlex Citation Expansion", ""])
    if payload["live_openalex_expand"]:
        for row in payload["live_openalex_expand"]:
            if row["ok"]:
                lines.append(
                    f"- ok `{row['seed']}` referenced={row['referenced_count']} citing={row['citing_count']}"
                )
            else:
                lines.append(f"- fail `{row['seed']}` error={row['error']}")
    else:
        lines.append("Not run in this benchmark pass.")
    lines.extend(["", "## Live Meta", ""])
    if payload["live_meta"]:
        for row in payload["live_meta"]:
            if row["ok"]:
                lines.append(
                    f"- ok `{row['theme']}` count={row['result_count']} sources={row['source_counts']} top_score={row['top_score']} top={row['top_url']}"
                )
            else:
                lines.append(f"- fail `{row['theme']}` error={row['error']}")
    else:
        lines.append("Not run in this benchmark pass.")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This benchmark applies the Katala-style Gate -> Scorer -> Selector discipline to research search: fail closed on unusable/retracted candidates, score with source and relevance features, then select with diversity caps so one host or source class cannot dominate every result.",
            "",
        ]
    )
    return "\n".join(lines)


def aggregate_category_scores(eval_runs: list) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[int]] = {}
    for run in eval_runs:
        for category, score in run.category_scores.items():
            grouped.setdefault(category, []).append(score)
    return {
        category: {
            "min": min(scores),
            "max": max(scores),
            "mean": round(statistics.mean(scores), 2),
        }
        for category, scores in grouped.items()
    }


if __name__ == "__main__":
    raise SystemExit(main())

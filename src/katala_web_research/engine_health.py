"""Per-engine failure, latency, and useful-result tracking for meta search routing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
from typing import Any


@dataclass(slots=True, frozen=True)
class EngineHealthStat:
    provider: str
    runs: int
    failures: int
    failure_rate: float
    useful_rate: float
    p95_latency_ms: int
    health_score: float
    last_error_kind: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_engine_runs(rows: list[dict]) -> list[EngineHealthStat]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["provider"], []).append(row)
    stats = [_stat_for(provider, provider_rows) for provider, provider_rows in grouped.items()]
    return sorted(stats, key=lambda stat: (-stat.health_score, stat.provider))


def weak_engines(
    stats: list[EngineHealthStat],
    *,
    min_runs: int = 5,
    max_failure_rate: float = 0.5,
    max_p95_latency_ms: int = 5_000,
    min_useful_rate: float = 0.2,
) -> list[str]:
    """Engines with enough history to have earned a demotion.

    `min_runs` is the whole safety margin: one bad afternoon on a healthy engine should
    not get it routed around, and a brand new engine has no record to be judged on.
    """
    return [
        stat.provider
        for stat in stats
        if stat.runs >= min_runs
        and (
            stat.failure_rate > max_failure_rate
            or stat.p95_latency_ms > max_p95_latency_ms
            or stat.useful_rate < min_useful_rate
        )
    ]


def percentile_ms(values: list[int], percent: float) -> int:
    """Nearest-rank percentile.

    Interpolating between two samples reports a latency no engine ever produced, which is
    worse than useless at the handful-of-samples scale this ledger operates at.
    """
    if not values:
        return 0
    ordered = sorted(values)
    index = max(1, ceil(percent / 100 * len(ordered)))
    return ordered[min(index, len(ordered)) - 1]


def _stat_for(provider: str, rows: list[dict]) -> EngineHealthStat:
    runs = len(rows)
    failures = sum(1 for row in rows if row["status"] == "error")
    useful = sum(1 for row in rows if int(row["result_count"]) > 0)
    p95 = percentile_ms([int(row["latency_ms"]) for row in rows], 95)
    failure_rate = failures / runs
    useful_rate = useful / runs
    return EngineHealthStat(
        provider=provider,
        runs=runs,
        failures=failures,
        failure_rate=round(failure_rate, 4),
        useful_rate=round(useful_rate, 4),
        p95_latency_ms=p95,
        health_score=round(
            (1 - failure_rate) * 0.5 + useful_rate * 0.35 + _latency_factor(p95) * 0.15, 4
        ),
        last_error_kind=next(
            (row["error_kind"] for row in reversed(rows) if row.get("error_kind")), ""
        ),
    )


def _latency_factor(p95_latency_ms: int) -> float:
    if p95_latency_ms < 1_000:
        return 1.0
    if p95_latency_ms < 2_000:
        return 0.6
    if p95_latency_ms < 5_000:
        return 0.3
    return 0.0

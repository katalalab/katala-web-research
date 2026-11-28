from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ProjectItem, utc_now_iso

PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
GH_SEARCH_FIELDS = "repository,number,title,state,updatedAt,url,labels"


def parse_gh_search_items(payload: list[dict[str, Any]], *, kind: str) -> list[ProjectItem]:
    items = []
    for row in payload:
        labels = _label_names(row.get("labels") or [])
        title = str(row.get("title") or "")
        items.append(
            ProjectItem(
                kind=kind,
                repository=_repository_name(row.get("repository") or {}),
                number=int(row.get("number") or 0),
                title=title,
                url=str(row.get("url") or ""),
                state=str(row.get("state") or ""),
                updated_at=str(row.get("updatedAt") or row.get("updated_at") or ""),
                labels=labels,
                priority=infer_priority(title=title, labels=labels),
                status=infer_status(labels=labels),
            )
        )
    return items


def load_project_items_json(path: str | Path, *, kind: str) -> list[ProjectItem]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("GitHub search JSON must be a list")
    return parse_gh_search_items(payload, kind=kind)


def fetch_github_project_items(
    *,
    owner: str,
    state: str = "open",
    limit: int = 50,
    include: str = "both",
) -> list[ProjectItem]:
    if include not in {"issues", "prs", "both"}:
        raise ValueError("include must be one of: issues, prs, both")
    selected = []
    if include in {"issues", "both"}:
        selected.extend(_gh_search("issues", owner=owner, state=state, limit=limit))
    if include in {"prs", "both"}:
        selected.extend(_gh_search("prs", owner=owner, state=state, limit=limit))
    return selected


def _gh_search(kind: str, *, owner: str, state: str, limit: int) -> list[ProjectItem]:
    cmd = [
        "gh",
        "search",
        kind,
        "--owner",
        owner,
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        GH_SEARCH_FIELDS,
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"gh search {kind} failed: {detail}")
    payload = json.loads(completed.stdout or "[]")
    return parse_gh_search_items(payload, kind="pr" if kind == "prs" else "issue")


def infer_priority(*, title: str, labels: list[str]) -> str:
    haystack = " ".join([title, *labels]).lower()
    if "priority/p0" in haystack or "p0" in haystack:
        return "p0"
    if "priority/p1" in haystack or "p1-critical" in haystack or "critical" in haystack:
        return "p1"
    if "priority/p2" in haystack or "p2-important" in haystack:
        return "p2"
    return "p3"


def infer_status(*, labels: list[str]) -> str:
    for label in labels:
        lowered = label.lower()
        if lowered.startswith("blocked") or lowered.startswith("status:"):
            return label
    return ""


def project_sort_key(item: ProjectItem) -> tuple[int, int, str, float, int]:
    return (
        PRIORITY_ORDER.get(item.priority, 9),
        _phase_order(item.labels),
        "" if item.status.startswith("blocked") else "z",
        _updated_desc(item.updated_at),
        -item.number,
    )


def build_project_radar(
    items: list[ProjectItem],
    *,
    archive_path: str,
    owner: str = "",
    generated_at: str | None = None,
) -> str:
    generated = generated_at or utc_now_iso()
    sorted_items = sorted(items, key=project_sort_key)
    lines = [
        "# Katala Project Radar",
        "",
        f"- generated_at: {generated}",
        f"- archive: `{archive_path}`",
    ]
    if owner:
        lines.append(f"- owner: {owner}")
    lines.extend(
        [
            f"- total_items: {len(sorted_items)}",
            "",
            "## Summary",
            "",
        ]
    )
    for priority in ("p0", "p1", "p2", "p3"):
        count = sum(1 for item in sorted_items if item.priority == priority)
        lines.append(f"- {priority}: {count}")

    for priority in ("p0", "p1", "p2", "p3"):
        priority_items = [item for item in sorted_items if item.priority == priority]
        if not priority_items:
            continue
        lines.extend(["", f"## {priority.upper()}", ""])
        for item in priority_items:
            labels = ", ".join(item.labels) if item.labels else "-"
            status = f" status={item.status}" if item.status else ""
            lines.append(f"- [{item.repository}#{item.number}]({item.url}) {item.title}")
            lines.append(f"  - kind={item.kind} state={item.state} updated_at={item.updated_at}{status}")
            lines.append(f"  - labels={labels}")
    lines.append("")
    return "\n".join(lines)


def _label_names(labels: list[Any]) -> list[str]:
    names = []
    for label in labels:
        name = str((label.get("name") or "") if isinstance(label, dict) else label).strip()
        if name:
            names.append(name)
    return names


def _repository_name(repository: dict[str, Any]) -> str:
    return str(repository.get("nameWithOwner") or repository.get("name") or "")


def _phase_order(labels: list[str]) -> int:
    for label in labels:
        if label.startswith("phase/"):
            phase = label.split("/", 1)[1].split("-", 1)[0]
            if phase.isdigit():
                return int(phase)
    return 99


def _updated_desc(value: str) -> float:
    try:
        return -datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0

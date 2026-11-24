from __future__ import annotations

import os
import subprocess
from collections import deque
from hashlib import sha256
from pathlib import Path

from .models import RepoDocument, utc_now_iso
from .text import collapse_space

DEFAULT_INCLUDE_NAME_ORDER = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "README.md",
    "README",
    "SKILL.md",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "AGENTS.MD",
    "CLAUDE.MD",
    "GEMINI.MD",
    "README.MD",
)
DEFAULT_INCLUDE_NAMES = {
    "AGENTS.md",
    "AGENTS.MD",
    "CLAUDE.md",
    "CLAUDE.MD",
    "GEMINI.md",
    "GEMINI.MD",
    "README.md",
    "README.MD",
    "README",
    "SKILL.md",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
}

DEFAULT_INCLUDE_SUFFIXES = {".md", ".txt", ".rst", ".toml", ".json", ".yaml", ".yml"}
TEXT_DECODING_CANDIDATES = ("utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16")
DEFAULT_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "target",
    "vendor",
    "raw",
    "downloads",
    "logs",
    "sessions",
}
DEFAULT_SCAN_DIRS = ("docs", "doc", ".github", "skills", ".agents/skills", ".claude/skills")


class CorpusScanError(RuntimeError):
    pass


def scan_repos(
    root: str | Path,
    *,
    max_repos: int = 200,
    max_files_per_repo: int = 80,
    max_bytes_per_file: int = 80_000,
    existing_metadata: dict[tuple[str, str], tuple[int, int, str]] | None = None,
    stats: dict[str, int] | None = None,
) -> tuple[list[RepoDocument], list[str]]:
    root_path = Path(root).expanduser()
    if not root_path.exists():
        raise CorpusScanError(f"path does not exist: {root_path}")
    repos, warnings = find_git_repos(root_path, max_repos=max_repos)
    documents: list[RepoDocument] = []
    for repo in repos:
        try:
            documents.extend(
                scan_repo(
                    repo,
                    max_files=max_files_per_repo,
                    max_bytes_per_file=max_bytes_per_file,
                    existing_metadata=existing_metadata or {},
                    stats=stats,
                )
            )
        except OSError as exc:
            warnings.append(f"{repo}: {exc}")
    return documents, warnings


def find_git_repos(root: Path, *, max_repos: int = 200) -> tuple[list[Path], list[str]]:
    found, warnings = find_git_repos_direct_children(root, max_repos=max_repos, max_candidates=max(max_repos * 8, 100))
    if found:
        return found, warnings
    found, warnings = find_git_repos_with_find(root, max_repos=max_repos)
    if found:
        return found, warnings

    repos: list[Path] = []
    warnings = []
    seen: set[Path] = set()
    try:
        child_names = sorted(entry.name for entry in os.scandir(root) if entry.is_dir(follow_symlinks=False))
        for child_name in child_names:
            if len(repos) >= max_repos:
                warnings.append(f"max_repos reached: {max_repos}")
                return repos, warnings
            child = root / child_name
            if not child.is_dir() or child.name in DEFAULT_SKIP_DIRS:
                continue
            if (child / ".git").is_dir():
                repos.append(child)
                seen.add(child.resolve())
    except OSError as exc:
        raise CorpusScanError(f"cannot list {root}: {exc}") from exc

    for dirpath, dirnames, _filenames in os.walk(root, topdown=True):
        path = Path(dirpath)
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            dirnames[:] = []
            continue
        if ".git" in dirnames:
            repos.append(path)
            seen.add(resolved)
            dirnames.remove(".git")
            dirnames[:] = []
            if len(repos) >= max_repos:
                warnings.append(f"max_repos reached: {max_repos}")
                break
            continue
        dirnames[:] = [name for name in dirnames if name not in DEFAULT_SKIP_DIRS and not name.startswith(".cache")]
    return repos, warnings


def find_git_repos_direct_children(
    root: Path, *, max_repos: int, max_candidates: int
) -> tuple[list[Path], list[str]]:
    repos: list[Path] = []
    warnings: list[str] = []
    checked = 0
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                if checked >= max_candidates or len(repos) >= max_repos:
                    break
                if not entry.is_dir(follow_symlinks=False):
                    continue
                checked += 1
                if entry.name in DEFAULT_SKIP_DIRS:
                    continue
                child = root / entry.name
                if (child / ".git").is_dir():
                    repos.append(child)
    except OSError:
        return [], []
    if len(repos) >= max_repos:
        warnings.append(f"max_repos reached: {max_repos}")
    elif checked >= max_candidates:
        warnings.append(f"max_candidates reached before max_repos: {max_candidates}")
    return repos, warnings


def find_git_repos_with_find(root: Path, *, max_repos: int) -> tuple[list[Path], list[str]]:
    repos: list[Path] = []
    warnings: list[str] = []
    try:
        completed = subprocess.run(
            ["/usr/bin/find", str(root), "-maxdepth", "2", "-name", ".git", "-type", "d"],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], []
    for line in completed.stdout.splitlines()[:max_repos]:
        git_dir = Path(line.strip())
        if git_dir:
            repos.append(git_dir.parent)
    if len(repos) >= max_repos:
        warnings.append(f"max_repos reached: {max_repos}")
    return repos, warnings


def scan_repo(
    repo: Path,
    *,
    max_files: int,
    max_bytes_per_file: int,
    existing_metadata: dict[tuple[str, str], tuple[int, int, str]] | None = None,
    stats: dict[str, int] | None = None,
) -> list[RepoDocument]:
    indexed_at = utc_now_iso()
    docs: list[RepoDocument] = []
    repo_name = repo.name
    considered = 0
    try:
        repo_path_str = str(repo.resolve())
    except OSError:
        repo_path_str = str(repo)
    existing_metadata = existing_metadata or {}
    for path in iter_candidate_files(repo):
        if considered >= max_files:
            break
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size <= 0 or stat.st_size > max_bytes_per_file:
            continue
        rel_path = path.relative_to(repo).as_posix()
        key = (repo_path_str, rel_path)
        old = existing_metadata.get(key)
        if old and old[0] == stat.st_size and old[1] == stat.st_mtime_ns:
            if stats is not None:
                stats["skipped_unchanged"] = stats.get("skipped_unchanged", 0) + 1
            continue
        try:
            raw = path.read_bytes()
            content = decode_text(raw)
        except UnicodeDecodeError:
            continue
        except OSError:
            continue
        content_sha = sha256(raw).hexdigest()
        if old and old[0] == stat.st_size and old[2] == content_sha:
            if stats is not None:
                stats["skipped_unchanged"] = stats.get("skipped_unchanged", 0) + 1
            continue
        title = extract_title(content, fallback=rel_path)
        kind = classify_file(path)
        considered += 1
        docs.append(
            RepoDocument(
                repo_path=repo_path_str,
                repo_name=repo_name,
                rel_path=rel_path,
                title=title,
                content=content,
                kind=kind,
                indexed_at=indexed_at,
                context=build_document_context(
                    repo_name=repo_name,
                    rel_path=rel_path,
                    kind=kind,
                    title=title,
                    content=content,
                ),
                file_size=stat.st_size,
                file_mtime_ns=stat.st_mtime_ns,
                content_sha256=content_sha,
            )
        )
    return docs


def decode_text(raw: bytes) -> str:
    for encoding in TEXT_DECODING_CANDIDATES:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("repo-corpus", raw, 0, len(raw), "unsupported text encoding")


def iter_candidate_files(repo: Path):
    seen: set[Path] = set()
    seen_file_ids: set[tuple[int, int]] = set()
    for name in DEFAULT_INCLUDE_NAME_ORDER:
        path = repo / name
        if should_include(path):
            try:
                resolved = path.resolve()
                stat = path.stat()
            except OSError:
                resolved = path
                stat = None
            file_id = (stat.st_dev, stat.st_ino) if stat else None
            if resolved not in seen and path.is_file() and (file_id is None or file_id not in seen_file_ids):
                seen.add(resolved)
                if file_id is not None:
                    seen_file_ids.add(file_id)
                yield path
    for rel_dir in DEFAULT_SCAN_DIRS:
        base = repo / rel_dir
        if not base.is_dir():
            continue
        for path in iter_limited_files(base, max_depth=2):
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen:
                continue
            try:
                stat = path.stat()
            except OSError:
                stat = None
            file_id = (stat.st_dev, stat.st_ino) if stat else None
            if file_id is not None and file_id in seen_file_ids:
                continue
            seen.add(resolved)
            if file_id is not None:
                seen_file_ids.add(file_id)
            if should_include(path):
                yield path


def iter_limited_files(base: Path, *, max_depth: int, max_dirs: int = 50, max_entries_per_dir: int = 200):
    queue: deque[tuple[Path, int]] = deque([(base, 0)])
    visited = 0
    while queue and visited < max_dirs:
        current, depth = queue.popleft()
        visited += 1
        try:
            with os.scandir(current) as entries:
                for idx, entry in enumerate(entries):
                    if idx >= max_entries_per_dir:
                        break
                    name = entry.name
                    if entry.is_file(follow_symlinks=False):
                        yield current / name
                    elif depth < max_depth and entry.is_dir(follow_symlinks=False):
                        if name in DEFAULT_SKIP_DIRS:
                            continue
                        if name.startswith(".") and name not in {".github", ".agents", ".claude"}:
                            continue
                        queue.append((current / name, depth + 1))
        except OSError:
            continue


def should_include(path: Path) -> bool:
    if path.name in DEFAULT_INCLUDE_NAMES:
        return True
    return path.suffix.lower() in DEFAULT_INCLUDE_SUFFIXES and len(path.parts) <= 12


def extract_title(content: str, *, fallback: str) -> str:
    for line in content.splitlines()[:60]:
        stripped = line.strip()
        if stripped.startswith("#"):
            return collapse_space(stripped.lstrip("#"))
        if stripped and not stripped.startswith(("{", "[", "<!--")):
            return collapse_space(stripped)[:140]
    return fallback


def classify_file(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("readme"):
        return "readme"
    if name in {"agents.md", "claude.md", "gemini.md"}:
        return "agent-context"
    if name == "skill.md":
        return "skill"
    if name in {"pyproject.toml", "package.json", "go.mod", "cargo.toml"}:
        return "manifest"
    if path.suffix.lower() == ".md":
        return "docs"
    return "text"


def build_document_context(*, repo_name: str, rel_path: str, kind: str, title: str, content: str) -> str:
    parts = [
        f"repo:{repo_name}",
        f"path:{rel_path}",
        f"kind:{kind}",
        f"title:{title}",
    ]
    heading_path = extract_heading_path(content)
    if heading_path:
        parts.append(f"headings:{heading_path}")
    return "\n".join(parts)


def extract_heading_path(content: str, *, limit: int = 4) -> str:
    headings: list[str] = []
    for line in content.splitlines()[:120]:
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        heading = collapse_space(stripped.lstrip("#"))
        if heading:
            headings.append(heading)
        if len(headings) >= limit:
            break
    return " > ".join(headings)

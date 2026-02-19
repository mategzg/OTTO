#!/usr/bin/env python3
"""Canonical repository root resolution utilities."""

from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

REQUIRED_MARKERS: Sequence[str] = (
    "CEO.md",
    "INDEX.md",
    "openclaw",
    "scripts",
)

SETROOT_REQUIRED_MARKERS: Sequence[str] = (
    "CEO.md",
    "INDEX.md",
    "openclaw",
    "ops",
    "scripts",
)

SCORING_MARKERS: Sequence[str] = (
    "CEO.md",
    "INDEX.md",
    "openclaw",
    "ops",
    "scripts",
    "brain",
    "AGENTS.md",
    "SOUL.md",
)

TOPLEVEL_ALLOWLIST = {
    "brain",
    "openclaw",
    "scripts",
    "docs",
    "ops",
    "tests",
    "workers",
    "plugins",
    "vault",
}

HARD_EXCLUDE_PREFIXES = (
    "vault/_quarantine",
    "vault/_salvage",
    ".git",
    "__pycache__",
)

CANONICAL_ROOT_MARKER = ".openclaw/CANONICAL_ROOT.json"
PATHLIKE_RE = re.compile(r"(:\\|\\users\\|\\|:)" , re.IGNORECASE)


@dataclass(frozen=True)
class RepoRootInfo:
    root_realpath: str
    resolver: str
    marker_score: int
    markers_found: List[str]


@dataclass(frozen=True)
class RootCandidate:
    candidate_id: str
    path: str
    realpath: str
    score: int
    markers_found: List[str]
    has_git: bool
    reason: str
    safe_for_pin: bool
    clean: bool


def _normalize_anchor(start: Optional[str | Path]) -> Path:
    anchor = Path(start) if start is not None else Path.cwd()
    anchor = anchor.resolve()
    if anchor.is_file():
        return anchor.parent
    return anchor


def is_pathlike_component(name: str) -> bool:
    value = name.strip().lower()
    if not value:
        return False
    if PATHLIKE_RE.search(value):
        return True
    if value.startswith("c:") or value.startswith("d:"):
        return True
    return False


def is_clean_root(path: str | Path) -> bool:
    candidate = Path(path).resolve()
    for part in candidate.parts:
        if is_pathlike_component(part):
            return False
    return True


def assert_safe_dir_name(name: str) -> str:
    if is_pathlike_component(name):
        raise RuntimeError(f"Unsafe directory name blocked by guardrail: {name}")
    return name


def is_within_root(path: str | Path, root: str | Path) -> bool:
    path_resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    try:
        path_resolved.relative_to(root_resolved)
        return True
    except ValueError:
        return False


def _score_markers(path: Path) -> Tuple[int, List[str]]:
    found: List[str] = []
    for marker in SCORING_MARKERS:
        try:
            exists = (path / marker).exists()
        except OSError:
            exists = False
        if exists:
            found.append(marker)
    return len(found), found


def _has_required_markers(path: Path) -> bool:
    for marker in REQUIRED_MARKERS:
        try:
            if not (path / marker).exists():
                return False
        except OSError:
            return False
    return True


def _has_setroot_markers(path: Path) -> bool:
    for marker in SETROOT_REQUIRED_MARKERS:
        try:
            if not (path / marker).exists():
                return False
        except OSError:
            return False
    return True


def _has_git(path: Path) -> bool:
    try:
        return (path / ".git").exists()
    except OSError:
        return False


def _iter_ancestors(path: Path) -> Iterable[Path]:
    current = path
    while True:
        yield current
        if current.parent == current:
            break
        current = current.parent


def _try_git_root(anchor: Path) -> Optional[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    if not output:
        return None

    candidate = Path(output).resolve()
    if not candidate.exists():
        return None
    return candidate


def _stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def _repetition_penalty(path: Path) -> int:
    text = str(path).lower()
    penalty = 0

    repeated_windows = max(0, text.count("c:\\users") - 1)
    penalty += repeated_windows * 6

    parts = [part.lower() for part in path.parts if part]
    counts = {}
    for part in parts:
        counts[part] = counts.get(part, 0) + 1
    penalty += sum((count - 1) for count in counts.values() if count > 1)

    for width in (1, 2, 3):
        for i in range(0, max(0, len(parts) - (2 * width) + 1)):
            left = parts[i : i + width]
            right = parts[i + width : i + (2 * width)]
            if left == right:
                penalty += 3

    normalized = path.as_posix().lower()
    if len(normalized) >= 24:
        long_repeat = re.search(r"(.{12,}?)(?:\1){1,}", normalized)
        if long_repeat:
            penalty += 8

    if not is_clean_root(path):
        penalty += 50

    return penalty


def _effective_score(path: Path) -> Tuple[int, List[str], int]:
    marker_score, markers_found = _score_markers(path)
    penalty = _repetition_penalty(path)
    effective = marker_score * 10 - penalty
    return effective, markers_found, penalty


def _read_marker(marker_path: Path) -> Optional[dict]:
    if not marker_path.is_file():
        return None
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def get_pinned_root(start: Optional[str | Path] = None, *, require_clean: bool = False) -> Optional[Path]:
    anchor = _normalize_anchor(start)
    candidates: List[Tuple[int, Path]] = []
    marker_paths: List[Path] = []

    for ancestor in _iter_ancestors(anchor):
        marker_paths.append(ancestor / CANONICAL_ROOT_MARKER)

    home = Path.home().resolve()
    marker_paths.append(home / ".openclaw" / "workspace" / CANONICAL_ROOT_MARKER)
    marker_paths.append(home / ".openclaw" / CANONICAL_ROOT_MARKER)

    seen_markers = set()
    for marker_path in marker_paths:
        key = str(marker_path.resolve()) if marker_path.exists() else str(marker_path)
        if key in seen_markers:
            continue
        seen_markers.add(key)

        payload = _read_marker(marker_path)
        if payload is None:
            continue

        declared = str(payload.get("root_realpath", "")).strip()
        if not declared:
            continue

        try:
            declared_path = Path(declared).resolve()
        except OSError:
            continue

        marker_root = marker_path.parent.parent.resolve()
        if declared_path != marker_root:
            continue
        if require_clean and not is_clean_root(declared_path):
            continue

        score, _, _ = _effective_score(declared_path)
        candidates.append((score, declared_path.resolve()))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], str(item[1])), reverse=True)
    return candidates[0][1]


def _resolve_by_markers(anchor: Path, *, require_clean: bool = False) -> RepoRootInfo:
    best_path: Optional[Path] = None
    best_score = -10_000
    best_found: List[str] = []

    for candidate in _iter_ancestors(anchor):
        if require_clean and not is_clean_root(candidate):
            continue

        effective, found, _penalty = _effective_score(candidate)
        if _has_required_markers(candidate):
            return RepoRootInfo(
                root_realpath=str(candidate.resolve()),
                resolver="markers",
                marker_score=effective,
                markers_found=found,
            )

        if effective > best_score:
            best_path = candidate
            best_score = effective
            best_found = found

    if best_path is not None and best_score >= 24:
        return RepoRootInfo(
            root_realpath=str(best_path.resolve()),
            resolver="markers",
            marker_score=best_score,
            markers_found=best_found,
        )

    raise RuntimeError("Unable to resolve repository root by markers.")


def resolve_repo_root(start: Optional[str | Path] = None, *, require_clean: bool = False) -> RepoRootInfo:
    anchor = _normalize_anchor(start)

    pinned = get_pinned_root(anchor, require_clean=require_clean)
    if pinned is not None:
        score, found, _penalty = _effective_score(pinned)
        return RepoRootInfo(
            root_realpath=str(pinned.resolve()),
            resolver="pinned_marker",
            marker_score=score,
            markers_found=found,
        )

    marker_info = _resolve_by_markers(anchor, require_clean=require_clean)

    git_candidate = _try_git_root(anchor)
    if git_candidate is None:
        return marker_info

    if require_clean and not is_clean_root(git_candidate):
        return marker_info

    git_score, git_found, _penalty = _effective_score(git_candidate)
    if (_has_required_markers(git_candidate) or _has_git(git_candidate)) and git_score >= marker_info.marker_score:
        return RepoRootInfo(
            root_realpath=str(git_candidate.resolve()),
            resolver="git",
            marker_score=git_score,
            markers_found=git_found,
        )

    return marker_info


def propose_clean_root(start: Optional[str | Path] = None) -> List[RootCandidate]:
    candidates = list_root_candidates(start, include_unclean=False)
    return [c for c in candidates if c.clean and c.safe_for_pin]


def resolve_clean_repo_root(start: Optional[str | Path] = None) -> RepoRootInfo:
    info = resolve_repo_root(start, require_clean=True)
    if not is_clean_root(info.root_realpath):
        raise RuntimeError(f"Resolved root is not clean: {info.root_realpath}")
    return info


def get_canonical_root(start: Optional[str | Path] = None) -> Path:
    return Path(resolve_clean_repo_root(start).root_realpath)


def assert_repo_root(expected: Optional[str | Path] = None, *, require_clean: bool = False) -> Path:
    anchor = _normalize_anchor(expected)
    info = resolve_repo_root(anchor, require_clean=require_clean)
    root = Path(info.root_realpath)

    if not is_within_root(anchor, root):
        raise RuntimeError(
            f"Resolved canonical root {root} does not contain anchor {anchor}. "
            "Run /repo roots and /repo setroot <id>."
        )

    if require_clean and not is_clean_root(root):
        raise RuntimeError(
            f"Resolved root is pathlike/invalid: {root}. "
            "Run /repo roots and /repo setroot <id> with a clean root."
        )

    return root


def list_root_candidates(start: Optional[str | Path] = None, *, include_unclean: bool = True) -> List[RootCandidate]:
    anchor = _normalize_anchor(start)
    raw: List[Path] = []

    ancestors = list(_iter_ancestors(anchor))
    raw.extend(ancestors)
    home = Path.home().resolve()
    raw.append(home / ".openclaw" / "workspace")
    raw.append(home / ".openclaw")
    raw.append(home)

    for ancestor in ancestors[:6]:
        try:
            children = sorted([p for p in ancestor.iterdir() if p.is_dir()], key=lambda p: p.name)
        except OSError:
            continue
        for child in children:
            marker_score, _ = _score_markers(child)
            has_git = _has_git(child)
            if marker_score >= 2 or has_git:
                raw.append(child)
            if child.name == ".openclaw":
                try:
                    grandchildren = sorted([p for p in child.iterdir() if p.is_dir()], key=lambda p: p.name)
                except OSError:
                    grandchildren = []
                for grandchild in grandchildren:
                    gscore, _ = _score_markers(grandchild)
                    ggit = _has_git(grandchild)
                    if gscore >= 2 or ggit:
                        raw.append(grandchild)

    dedup: List[Path] = []
    seen_real = set()
    for path in raw:
        resolved = path.resolve()
        key = str(resolved)
        if key in seen_real:
            continue
        seen_real.add(key)
        dedup.append(resolved)

    out: List[RootCandidate] = []
    for path in sorted(dedup, key=lambda p: str(p)):
        clean = is_clean_root(path)
        if not include_unclean and not clean:
            continue

        score, markers_found, penalty = _effective_score(path)
        has_git = _has_git(path)
        if len(markers_found) < 2 and not has_git:
            continue

        safe_for_pin = clean and (_has_setroot_markers(path) or has_git)
        reason = "marker-rich"
        if penalty > 0:
            reason = f"marker-rich_penalized:{penalty}"
        if has_git and not _has_setroot_markers(path):
            reason = "git_only_or_partial"
        if not clean:
            reason = f"pathlike_invalid:{reason}"

        out.append(
            RootCandidate(
                candidate_id=_stable_id(str(path)),
                path=str(path),
                realpath=str(path),
                score=score,
                markers_found=sorted(markers_found),
                has_git=has_git,
                reason=reason,
                safe_for_pin=safe_for_pin,
                clean=clean,
            )
        )

    out.sort(key=lambda c: (-int(c.safe_for_pin), -c.score, len(Path(c.path).parts), c.path))
    return out


def set_canonical_root(
    root_path: str | Path,
    *,
    created_by: str = "telegram",
    host_hint: Optional[str] = None,
    reason: str = "manual_set",
) -> dict:
    root = Path(root_path).resolve()
    if not root.is_dir():
        raise RuntimeError(f"Cannot pin root: not a directory: {root}")
    if not is_clean_root(root):
        raise RuntimeError(f"Cannot pin root: pathlike/invalid root: {root}")

    has_markers = _has_setroot_markers(root)
    has_git = _has_git(root)
    if not (has_markers or has_git):
        raise RuntimeError(
            "Cannot pin root: requires .git or markers CEO.md, INDEX.md, openclaw/, ops/, scripts/."
        )

    marker_path = root / CANONICAL_ROOT_MARKER
    marker_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "root_realpath": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
        "host_hint": host_hint or socket.gethostname(),
        "reason": reason,
    }
    marker_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"marker_path": str(marker_path), "payload": payload}


__all__ = [
    "CANONICAL_ROOT_MARKER",
    "RepoRootInfo",
    "RootCandidate",
    "TOPLEVEL_ALLOWLIST",
    "HARD_EXCLUDE_PREFIXES",
    "assert_repo_root",
    "assert_safe_dir_name",
    "get_canonical_root",
    "get_pinned_root",
    "is_clean_root",
    "is_pathlike_component",
    "is_within_root",
    "list_root_candidates",
    "propose_clean_root",
    "resolve_repo_root",
    "resolve_clean_repo_root",
    "set_canonical_root",
]

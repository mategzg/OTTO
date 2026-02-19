#!/usr/bin/env python3
"""Detect ghost roots, salvage unique files, and quarantine bad copies deterministically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import (
    HARD_EXCLUDE_PREFIXES,
    assert_safe_dir_name,
    get_canonical_root,
    get_pinned_root,
    is_clean_root,
    is_pathlike_component,
    is_within_root,
)
from scripts.workspace_hygiene_policy import assert_policy_root, load_policy

SCAN_MARKERS: Sequence[str] = (
    "CEO.md",
    "INDEX.md",
    "openclaw",
    "ops",
    "scripts",
    "brain",
    "AGENTS.md",
    "SOUL.md",
)

HIGH_SCORE_THRESHOLD = 5
CONFLICT_THRESHOLD_DEFAULT = 50

ALLOWLIST_FILE = "state/repo_reality_allowlist.json"
STATE_FILE = "state/repo_reality_state.json"

VALUE_EXTENSIONS: Set[str] = {
    ".md",
    ".txt",
    ".json",
    ".ndjson",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".py",
    ".js",
    ".ts",
    ".sh",
    ".ps1",
    ".sql",
    ".csv",
}

CANONICAL_DIRS: Set[str] = {
    "docs",
    "openclaw",
    "scripts",
    "tests",
    "ops",
    "brain",
    "plugins",
    "templates",
}

EXCLUDED_DIR_NAMES: Set[str] = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".vscode",
    ".idea",
    ".claude",
    ".codex",
    "inbox_raw",
    "dist",
    "build",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.is_file():
        return dict(default)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(default)
    if not isinstance(payload, dict):
        return dict(default)
    merged = dict(default)
    merged.update(payload)
    return merged


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_id(abs_path: Path) -> str:
    return hashlib.sha1(str(abs_path.resolve()).encode("utf-8")).hexdigest()[:10]


def _score_markers(path: Path) -> Tuple[int, List[str]]:
    found: List[str] = []
    for marker in SCAN_MARKERS:
        try:
            exists = (path / marker).exists()
        except OSError:
            exists = False
        if exists:
            found.append(marker)
    return len(found), found


def _load_allowlist(root: Path) -> Dict[str, Any]:
    default = {"version": 1, "kept_ids": [], "kept_paths": {}, "updated_at": ""}
    payload = _load_json(root / ALLOWLIST_FILE, default)
    payload["kept_ids"] = sorted({str(x) for x in payload.get("kept_ids", []) if str(x).strip()})
    kept_paths = payload.get("kept_paths", {})
    if not isinstance(kept_paths, dict):
        kept_paths = {}
    payload["kept_paths"] = {str(k): str(v) for k, v in kept_paths.items()}
    return payload


def _save_allowlist(root: Path, payload: Dict[str, Any]) -> None:
    out = dict(payload)
    out["updated_at"] = _utc_now()
    _save_json(root / ALLOWLIST_FILE, out)


def _load_state(root: Path) -> Dict[str, Any]:
    default = {
        "version": 2,
        "approved_quarantine_ids": [],
        "quarantined_ids": [],
        "quarantine_moves": [],
        "salvage_last_plan": "",
        "salvage_last_apply": "",
        "updated_at": "",
    }
    payload = _load_json(root / STATE_FILE, default)
    payload["approved_quarantine_ids"] = sorted(
        {str(x) for x in payload.get("approved_quarantine_ids", []) if str(x).strip()}
    )
    payload["quarantined_ids"] = sorted(
        {str(x) for x in payload.get("quarantined_ids", []) if str(x).strip()}
    )
    moves = payload.get("quarantine_moves", [])
    if not isinstance(moves, list):
        moves = []
    payload["quarantine_moves"] = moves
    return payload


def _save_state(root: Path, payload: Dict[str, Any]) -> None:
    out = dict(payload)
    out["updated_at"] = _utc_now()
    _save_json(root / STATE_FILE, out)


def _default_scan_base(canonical_root: Path) -> Path:
    if canonical_root.parent.name == ".openclaw":
        return canonical_root.parent.parent.resolve()
    if canonical_root.parent.parent == canonical_root.parent:
        return canonical_root.parent.resolve()
    return canonical_root.parent.resolve()


def _is_pathlike_dir(path: Path) -> bool:
    return is_pathlike_component(path.name)


def _is_backup_dir(path: Path) -> bool:
    return path.name.startswith("_OLD_BAD_PATH_BACKUP")


def _classify_candidate(path: Path) -> Tuple[Optional[str], int, List[str]]:
    score, markers = _score_markers(path)
    has_git = (path / ".git").exists()

    if _is_backup_dir(path):
        return "old_backup_root", score, markers
    if _is_pathlike_dir(path):
        return "pathlike_folder", score, markers

    if has_git:
        # Ignore unrelated repos unless they look like OpenClaw-shaped content.
        if score >= 2 or (path / "SOUL.md").exists() or (path / "AGENTS.md").exists() or (path / "TOOLS.md").exists():
            return "nested_repo_git", score, markers
        return None, score, markers

    if score >= HIGH_SCORE_THRESHOLD:
        return "nested_repo_copy_high_score", score, markers

    return None, score, markers


def _effective_excluded_dir_names(canonical_root: Path) -> Set[str]:
    names = set(EXCLUDED_DIR_NAMES)
    policy = load_policy(canonical_root, create_if_missing=False)
    assert_policy_root(canonical_root, policy)
    for name in policy.get("tooling_dirs", []):
        clean = str(name).strip().strip("/")
        if clean and "/" not in clean:
            names.add(clean)
    return names


def _iter_scan_dirs(scan_base: Path, max_depth: int, *, excluded_dir_names: Set[str]) -> Iterable[Path]:
    base = scan_base.resolve()
    seen: Set[str] = set()

    for dirpath, dirnames, _files in os.walk(base, topdown=True, followlinks=False):
        current = Path(dirpath)
        current_real = str(current.resolve())
        if current_real in seen:
            dirnames[:] = []
            continue
        seen.add(current_real)

        rel = "." if current == base else current.resolve().relative_to(base).as_posix()
        depth = 0 if rel == "." else rel.count("/") + 1

        pruned: List[str] = []
        for name in sorted(dirnames):
            if name in excluded_dir_names:
                continue
            if is_pathlike_component(name) and name in {".git", ".venv"}:
                continue
            pruned.append(name)
        dirnames[:] = pruned

        if depth >= max_depth:
            dirnames[:] = []

        yield current


def _count_tree(path: Path, *, excluded_dir_names: Set[str]) -> Tuple[int, int, bool]:
    files = 0
    total = 0
    has_symlink = False
    for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        d = Path(dirpath)
        pruned: List[str] = []
        for name in sorted(dirnames):
            if name in excluded_dir_names:
                continue
            child = d / name
            if child.is_symlink():
                has_symlink = True
                continue
            pruned.append(name)
        dirnames[:] = pruned

        for fname in filenames:
            fp = d / fname
            if fp.is_symlink():
                has_symlink = True
                continue
            files += 1
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return files, total, has_symlink


def _analyze_candidate(canonical_root: Path, scan_base: Path, path: Path, candidate_type: str, score: int, markers: List[str]) -> Dict[str, Any]:
    files, total_bytes, has_symlink = _count_tree(path, excluded_dir_names=_effective_excluded_dir_names(canonical_root))
    abs_path = path.resolve()

    safe_to_move = True
    reason = ""
    if abs_path == canonical_root.resolve():
        safe_to_move = False
        reason = "matches_canonical_root"
    elif is_within_root(canonical_root, abs_path):
        safe_to_move = False
        reason = "contains_canonical_root"
    elif has_symlink:
        safe_to_move = False
        reason = "symlink_risk"

    candidate = {
        "candidate_id": _candidate_id(abs_path),
        "candidate_type": candidate_type,
        "classification": candidate_type,
        "has_git_dir": (path / ".git").is_dir(),
        "has_git_file": (path / ".git").is_file(),
        "markers_found": sorted(markers),
        "needs_user": not safe_to_move,
        "path": str(abs_path),
        "rel_path": abs_path.relative_to(scan_base.resolve()).as_posix() if is_within_root(abs_path, scan_base) else str(abs_path),
        "realpath": str(abs_path),
        "safe_to_move": safe_to_move,
        "safety_reason": reason,
        "score": score,
        "size_estimate_bytes": total_bytes,
        "file_count": files,
        "contains_symlink": has_symlink,
        "clean_path": is_clean_root(abs_path),
    }
    return candidate


def _discover_candidates(canonical_root: Path, scan_base: Path, max_depth: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen_paths: Set[str] = set()
    excluded_dir_names = _effective_excluded_dir_names(canonical_root)

    quarantine_root = canonical_root / "vault" / "_quarantine"
    salvage_root = canonical_root / "vault" / "_salvage"

    for current in _iter_scan_dirs(scan_base, max_depth=max_depth, excluded_dir_names=excluded_dir_names):
        abs_current = current.resolve()

        if abs_current == scan_base.resolve():
            continue
        if abs_current == canonical_root.resolve():
            continue
        if is_within_root(abs_current, quarantine_root) or is_within_root(abs_current, salvage_root):
            continue

        candidate_type, score, markers = _classify_candidate(abs_current)
        if not candidate_type:
            continue

        key = str(abs_current)
        if key in seen_paths:
            continue
        seen_paths.add(key)

        out.append(_analyze_candidate(canonical_root, scan_base, abs_current, candidate_type, score, markers))

    out.sort(key=lambda item: item["path"])
    return out


def run_doctor(
    root: Path,
    *,
    apply: bool = False,
    max_depth: int = 6,
    scan_base: Optional[Path] = None,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    actual_scan_base = (scan_base or _default_scan_base(canonical_root)).resolve()

    allowlist = _load_allowlist(canonical_root)
    state = _load_state(canonical_root)
    kept_ids = set(allowlist.get("kept_ids", []))
    quarantined_ids = set(state.get("quarantined_ids", []))

    candidates = _discover_candidates(canonical_root, actual_scan_base, max_depth=max_depth)

    for item in candidates:
        cid = item["candidate_id"]
        if cid in quarantined_ids:
            disposition = "quarantined"
        elif cid in kept_ids:
            disposition = "kept"
        else:
            disposition = "pending"
        item["disposition"] = disposition

    pending = [item for item in candidates if item["disposition"] == "pending"]

    summary = {
        "candidate_count": len(candidates),
        "pending_count": len(pending),
        "kept_count": sum(1 for c in candidates if c["disposition"] == "kept"),
        "quarantined_count": sum(1 for c in candidates if c["disposition"] == "quarantined"),
        "needs_user_count": sum(1 for c in pending if c["needs_user"]),
        "nested_git_count": sum(1 for c in pending if c["candidate_type"] == "nested_repo_git"),
        "pathlike_count": sum(1 for c in pending if c["candidate_type"] == "pathlike_folder"),
        "backup_count": sum(1 for c in pending if c["candidate_type"] == "old_backup_root"),
        "safe_to_move_count": sum(1 for c in pending if c["safe_to_move"]),
        "symlink_flag_count": sum(1 for c in pending if c["contains_symlink"]),
    }

    report: Dict[str, Any] = {
        "canonical_root": str(canonical_root),
        "pinned_root": str(get_pinned_root(canonical_root, require_clean=True) or ""),
        "scan_base": str(actual_scan_base),
        "candidates": candidates,
        "scan": {
            "high_score_threshold": HIGH_SCORE_THRESHOLD,
            "max_depth": max_depth,
            "markers": list(SCAN_MARKERS),
        },
        "state": {
            "allowlist_file": ALLOWLIST_FILE,
            "kept_ids": sorted(kept_ids),
            "quarantined_ids": sorted(quarantined_ids),
            "state_file": STATE_FILE,
        },
        "summary": summary,
        "version": 3,
    }

    if apply:
        approved = state.get("approved_quarantine_ids", [])
        apply_result = _apply_quarantine_ids(canonical_root, report, approved)
        report["apply"] = apply_result
    else:
        report["apply"] = {
            "applied": False,
            "approved_ids": state.get("approved_quarantine_ids", []),
            "moved": [],
            "quarantine_root": "",
            "skipped": [],
        }

    return report


def _should_salvage_file(candidate_root: Path, file_path: Path) -> bool:
    rel = file_path.resolve().relative_to(candidate_root.resolve())
    if not rel.parts:
        return False
    top = rel.parts[0]
    if top in CANONICAL_DIRS:
        return True
    return file_path.suffix.lower() in VALUE_EXTENSIONS


def _build_candidate_salvage(canonical_root: Path, candidate: Dict[str, Any], stamp: str) -> Dict[str, Any]:
    candidate_root = Path(candidate["path"]).resolve()
    candidate_id = candidate["candidate_id"]

    stage_root = canonical_root / "vault" / "_salvage" / f"{stamp}_{candidate_id}"
    staged_dir = stage_root / "staged"
    staged_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []
    excluded_dir_names = _effective_excluded_dir_names(canonical_root)

    for dirpath, dirnames, filenames in os.walk(candidate_root, topdown=True, followlinks=False):
        current = Path(dirpath)
        pruned = []
        for name in sorted(dirnames):
            if name in excluded_dir_names:
                continue
            pruned.append(name)
        dirnames[:] = pruned

        for filename in sorted(filenames):
            src = current / filename
            if src.is_symlink():
                continue
            if not _should_salvage_file(candidate_root, src):
                continue

            rel = src.resolve().relative_to(candidate_root.resolve()).as_posix()
            target_rel = rel
            target = canonical_root / target_rel

            src_hash = _sha256(src)
            conflict = False
            existing_hash = ""
            if target.exists() and target.is_file():
                try:
                    existing_hash = _sha256(target)
                except OSError:
                    existing_hash = ""
                if existing_hash and existing_hash != src_hash:
                    conflict = True

            if conflict:
                staged_rel = f"{target_rel}__from_{candidate_id}"
                action = "conflict"
                conflicts.append(
                    {
                        "candidate_id": candidate_id,
                        "existing_path": target_rel,
                        "existing_sha256": existing_hash,
                        "incoming_path": rel,
                        "incoming_sha256": src_hash,
                        "staged_rel": staged_rel,
                    }
                )
            else:
                staged_rel = target_rel
                action = "promote"

            staged_path = staged_dir / staged_rel
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, staged_path)

            stat = src.stat()
            manifest_entries.append(
                {
                    "action": action,
                    "candidate_id": candidate_id,
                    "mtime": stat.st_mtime,
                    "rel_path": rel,
                    "sha256": src_hash,
                    "size": stat.st_size,
                    "source_path": str(src),
                    "staged_rel": staged_rel,
                    "target_rel": target_rel,
                }
            )

    manifest_entries.sort(key=lambda item: (item["target_rel"], item["source_path"]))
    conflicts.sort(key=lambda item: (item["existing_path"], item["incoming_path"]))

    manifest = {
        "candidate_id": candidate_id,
        "candidate_path": str(candidate_root),
        "created_at": _utc_now(),
        "entries": manifest_entries,
    }
    conflicts_payload = {
        "candidate_id": candidate_id,
        "candidate_path": str(candidate_root),
        "conflicts": conflicts,
    }

    manifest_path = stage_root / "MANIFEST.json"
    conflicts_path = stage_root / "CONFLICTS.json"
    _save_json(manifest_path, manifest)
    _save_json(conflicts_path, conflicts_payload)

    return {
        "candidate_id": candidate_id,
        "candidate_path": str(candidate_root),
        "candidate_type": candidate["candidate_type"],
        "conflict_count": len(conflicts),
        "entry_count": len(manifest_entries),
        "manifest_path": str(manifest_path),
        "conflicts_path": str(conflicts_path),
        "stage_root": str(stage_root),
    }


def _render_salvage_markdown(plan: Dict[str, Any], rel_json: str, rel_log: str) -> str:
    lines = [
        "# Repo Salvage Plan",
        "",
        f"- Canonical root: `{plan['canonical_root']}`",
        f"- Scan base: `{plan['scan_base']}`",
        f"- Candidate count: {plan['summary']['candidate_count']}",
        f"- Salvage candidates: {plan['summary']['salvage_candidate_count']}",
        f"- Entry count: {plan['summary']['entry_count']}",
        f"- Conflict count: {plan['summary']['conflict_count']}",
        f"- Blocked: {plan['summary']['blocked']}",
        f"- JSON report: `{rel_json}`",
        f"- Log report: `{rel_log}`",
        "",
        "## Candidates",
        "",
    ]

    if not plan.get("salvage", {}).get("candidates"):
        lines.append("- No salvage candidates found.")
    else:
        for item in plan["salvage"]["candidates"]:
            lines.append(
                f"- `{item['candidate_path']}` ({item['candidate_type']}) | id={item['candidate_id']} "
                f"| entries={item['entry_count']} | conflicts={item['conflict_count']} | manifest=`{item['manifest_path']}`"
            )

    if plan.get("apply_result"):
        lines.append("")
        lines.append("## Apply")
        lines.append("")
        apply_result = plan["apply_result"]
        lines.append(f"- Promoted files: {apply_result.get('promoted_count', 0)}")
        lines.append(f"- Skipped conflicts: {apply_result.get('skipped_conflicts', 0)}")

    return "\n".join(lines) + "\n"


def write_salvage_reports(plan: Dict[str, Any], canonical_root: Path) -> Dict[str, str]:
    docs_dir = canonical_root / "docs" / "_inbox"
    logs_dir = canonical_root / "logs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    json_path = docs_dir / "repo_salvage_plan_latest.json"
    md_path = docs_dir / "repo_salvage_plan_latest.md"
    log_path = logs_dir / "repo_salvage_latest.json"

    _save_json(json_path, plan)
    _save_json(log_path, plan)

    md_text = _render_salvage_markdown(
        plan,
        rel_json=json_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        rel_log=log_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
    )
    md_path.write_text(md_text, encoding="utf-8")

    return {
        "json": json_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "markdown": md_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "log": log_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }


def build_salvage_plan(
    root: Path,
    *,
    max_depth: int = 6,
    scan_base: Optional[Path] = None,
    conflict_threshold: int = CONFLICT_THRESHOLD_DEFAULT,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    report = run_doctor(canonical_root, apply=False, max_depth=max_depth, scan_base=scan_base)

    candidates = [
        item
        for item in report["candidates"]
        if item["disposition"] == "pending"
        and item["candidate_type"] in {"pathlike_folder", "old_backup_root", "nested_repo_git", "nested_repo_copy_high_score"}
    ]

    stamp = _stamp()
    salvage_candidates: List[Dict[str, Any]] = []
    entry_count = 0
    conflict_count = 0

    for candidate in candidates:
        staged = _build_candidate_salvage(canonical_root, candidate, stamp)
        salvage_candidates.append(staged)
        entry_count += staged["entry_count"]
        conflict_count += staged["conflict_count"]

    blocked = conflict_count > conflict_threshold

    plan: Dict[str, Any] = {
        "canonical_root": str(canonical_root),
        "scan_base": report["scan_base"],
        "created_at": _utc_now(),
        "doctor_summary": report["summary"],
        "salvage": {
            "candidates": sorted(salvage_candidates, key=lambda item: item["candidate_path"]),
            "conflict_threshold": conflict_threshold,
        },
        "summary": {
            "blocked": blocked,
            "candidate_count": report["summary"]["candidate_count"],
            "salvage_candidate_count": len(salvage_candidates),
            "entry_count": entry_count,
            "conflict_count": conflict_count,
        },
        "version": 1,
    }

    paths = write_salvage_reports(plan, canonical_root)
    plan["paths"] = paths
    _save_json(canonical_root / paths["json"], plan)
    _save_json(canonical_root / paths["log"], plan)

    state = _load_state(canonical_root)
    state["salvage_last_plan"] = paths["json"]
    _save_state(canonical_root, state)

    return plan


def apply_salvage_plan(root: Path, *, plan_path: Optional[Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    selected_path = plan_path or (canonical_root / "docs" / "_inbox" / "repo_salvage_plan_latest.json")

    if not selected_path.is_file():
        return {
            "ok": False,
            "reason": "missing_plan",
            "plan_path": str(selected_path),
            "promoted_count": 0,
            "skipped_conflicts": 0,
        }

    plan = json.loads(selected_path.read_text(encoding="utf-8"))

    if plan.get("summary", {}).get("blocked", False):
        result = {
            "ok": False,
            "reason": "blocked_by_conflicts",
            "plan_path": str(selected_path),
            "promoted_count": 0,
            "skipped_conflicts": int(plan.get("summary", {}).get("conflict_count", 0)),
        }
        plan["apply_result"] = result
        paths = write_salvage_reports(plan, canonical_root)
        plan["paths"] = paths
        _save_json(canonical_root / paths["json"], plan)
        _save_json(canonical_root / paths["log"], plan)
        return result

    promoted = 0
    skipped_conflicts = 0
    skipped_guardrail = 0

    for candidate in plan.get("salvage", {}).get("candidates", []):
        manifest_path = Path(candidate["manifest_path"])
        if not manifest_path.is_file():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = sorted(payload.get("entries", []), key=lambda item: (item["target_rel"], item["source_path"]))

        stage_root = manifest_path.parent / "staged"
        for entry in entries:
            action = entry.get("action", "")
            staged_rel = entry.get("staged_rel", "")
            target_rel = entry.get("target_rel", "")
            if not staged_rel or not target_rel:
                continue

            if action == "conflict":
                skipped_conflicts += 1
                continue

            src = stage_root / staged_rel
            dst = canonical_root / target_rel
            if not src.is_file():
                continue

            # Guardrail: never recreate pathlike directory/file names in canonical root.
            target_parts = Path(target_rel).parts
            if any(is_pathlike_component(part) for part in target_parts):
                skipped_guardrail += 1
                continue

            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and dst.is_file():
                try:
                    if _sha256(dst) == _sha256(src):
                        continue
                except OSError:
                    continue

            shutil.copy2(src, dst)
            promoted += 1

    result = {
        "ok": True,
        "reason": "applied",
        "plan_path": str(selected_path),
        "promoted_count": promoted,
        "skipped_conflicts": skipped_conflicts,
        "skipped_guardrail": skipped_guardrail,
    }

    plan["apply_result"] = result
    paths = write_salvage_reports(plan, canonical_root)
    plan["paths"] = paths
    _save_json(canonical_root / paths["json"], plan)
    _save_json(canonical_root / paths["log"], plan)

    state = _load_state(canonical_root)
    state["salvage_last_apply"] = _utc_now()
    _save_state(canonical_root, state)

    return result


def _quarantine_bucket(candidate_type: str) -> str:
    if candidate_type == "pathlike_folder":
        return "bad_path_roots"
    if candidate_type == "old_backup_root":
        return "old_backups"
    return "nested_repo_copies"


def _write_quarantine_readme(dest: Path, item: Dict[str, Any], salvage_path: str) -> None:
    readme = dest / "README.md"
    content = [
        "# Quarantine Record",
        "",
        f"- source: `{item['path']}`",
        f"- candidate_id: `{item['candidate_id']}`",
        f"- candidate_type: `{item['candidate_type']}`",
        f"- quarantined_at: `{_utc_now()}`",
        f"- file_count_estimate: {item.get('file_count', 0)}",
        f"- size_estimate_bytes: {item.get('size_estimate_bytes', 0)}",
        f"- salvage_plan: `{salvage_path}`",
    ]
    readme.write_text("\n".join(content) + "\n", encoding="utf-8")


def _move_candidate_to_quarantine(canonical_root: Path, item: Dict[str, Any], salvage_path: str, stamp: str) -> Dict[str, str]:
    src = Path(item["path"]).resolve()
    if not src.exists() or not src.is_dir():
        raise RuntimeError("missing_source")

    if src == canonical_root.resolve():
        raise RuntimeError("matches_canonical_root")
    if is_within_root(canonical_root, src):
        raise RuntimeError("contains_canonical_root")

    bucket = _quarantine_bucket(item["candidate_type"])
    dest_root = canonical_root / "vault" / "_quarantine" / bucket
    dest_root.mkdir(parents=True, exist_ok=True)

    dest = dest_root / f"{stamp}_{item['candidate_id']}"
    suffix = 1
    while dest.exists():
        dest = dest_root / f"{stamp}_{item['candidate_id']}_{suffix}"
        suffix += 1

    shutil.move(str(src), str(dest))
    _write_quarantine_readme(dest, item, salvage_path)

    return {
        "candidate_id": item["candidate_id"],
        "from": str(src),
        "to": str(dest.resolve()),
        "bucket": bucket,
    }


def _apply_quarantine_ids(canonical_root: Path, report: Dict[str, Any], approved_ids: Sequence[str]) -> Dict[str, Any]:
    state = _load_state(canonical_root)
    candidate_map = {item["candidate_id"]: item for item in report["candidates"]}
    stamp = _stamp()

    moved: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    for candidate_id in sorted(set(approved_ids)):
        item = candidate_map.get(candidate_id)
        if item is None:
            skipped.append({"candidate_id": candidate_id, "reason": "missing_in_scan"})
            continue
        if item.get("disposition") != "pending":
            skipped.append({"candidate_id": candidate_id, "path": item["path"], "reason": "not_pending"})
            continue
        if not item.get("safe_to_move", False):
            skipped.append({"candidate_id": candidate_id, "path": item["path"], "reason": item.get("safety_reason", "unsafe")})
            continue

        try:
            move = _move_candidate_to_quarantine(
                canonical_root,
                item,
                salvage_path=state.get("salvage_last_plan", ""),
                stamp=stamp,
            )
        except RuntimeError as exc:
            skipped.append({"candidate_id": candidate_id, "path": item["path"], "reason": str(exc)})
            continue

        moved.append(move)

    moved_ids = {item["candidate_id"] for item in moved}
    quarantined = set(state.get("quarantined_ids", []))
    quarantined.update(moved_ids)
    state["quarantined_ids"] = sorted(quarantined)

    moves = list(state.get("quarantine_moves", []))
    for item in moved:
        moves.append(
            {
                "at": _utc_now(),
                "candidate_id": item["candidate_id"],
                "from": item["from"],
                "to": item["to"],
                "bucket": item["bucket"],
            }
        )
    state["quarantine_moves"] = moves
    state["approved_quarantine_ids"] = [cid for cid in sorted(set(approved_ids)) if cid not in moved_ids]
    _save_state(canonical_root, state)

    return {
        "applied": True,
        "approved_ids": sorted(set(approved_ids)),
        "moved": moved,
        "quarantine_root": "vault/_quarantine",
        "skipped": skipped,
    }


def keep_candidate_ids(root: Path, candidate_ids: Sequence[str], *, max_depth: int = 6, scan_base: Optional[Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    report = run_doctor(canonical_root, apply=False, max_depth=max_depth, scan_base=scan_base)
    candidate_map = {item["candidate_id"]: item for item in report["candidates"]}

    allowlist = _load_allowlist(canonical_root)
    kept_ids = set(allowlist.get("kept_ids", []))
    kept_paths = dict(allowlist.get("kept_paths", {}))

    kept: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    for candidate_id in sorted(set(candidate_ids)):
        item = candidate_map.get(candidate_id)
        if item is None:
            skipped.append({"candidate_id": candidate_id, "reason": "missing_in_scan"})
            continue
        kept_ids.add(candidate_id)
        kept_paths[candidate_id] = item["path"]
        kept.append({"candidate_id": candidate_id, "path": item["path"]})

    allowlist["kept_ids"] = sorted(kept_ids)
    allowlist["kept_paths"] = kept_paths
    _save_allowlist(canonical_root, allowlist)

    return {
        "ok": True,
        "kept": kept,
        "skipped": skipped,
        "allowlist_path": ALLOWLIST_FILE,
    }


def approve_candidate_ids(root: Path, candidate_ids: Sequence[str], *, max_depth: int = 6, scan_base: Optional[Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    report = run_doctor(canonical_root, apply=False, max_depth=max_depth, scan_base=scan_base)
    candidate_map = {item["candidate_id"]: item for item in report["candidates"]}

    state = _load_state(canonical_root)
    approved = set(state.get("approved_quarantine_ids", []))

    approved_now: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    for candidate_id in sorted(set(candidate_ids)):
        item = candidate_map.get(candidate_id)
        if item is None:
            skipped.append({"candidate_id": candidate_id, "reason": "missing_in_scan"})
            continue
        if item.get("disposition") != "pending":
            skipped.append({"candidate_id": candidate_id, "path": item["path"], "reason": "not_pending"})
            continue
        approved.add(candidate_id)
        approved_now.append({"candidate_id": candidate_id, "path": item["path"]})

    state["approved_quarantine_ids"] = sorted(approved)
    _save_state(canonical_root, state)

    return {
        "ok": True,
        "approved": approved_now,
        "skipped": skipped,
        "state_path": STATE_FILE,
    }


def apply_approved_quarantine(root: Path, *, max_depth: int = 6, scan_base: Optional[Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = _load_state(canonical_root)
    approved = sorted(set(state.get("approved_quarantine_ids", [])))

    report_before = run_doctor(canonical_root, apply=False, max_depth=max_depth, scan_base=scan_base)
    apply_result = _apply_quarantine_ids(canonical_root, report_before, approved)
    report_after = run_doctor(canonical_root, apply=False, max_depth=max_depth, scan_base=scan_base)

    return {
        "apply": apply_result,
        "report": report_after,
        "state_path": STATE_FILE,
    }


def apply_default_quarantine(
    root: Path,
    *,
    max_depth: int = 6,
    scan_base: Optional[Path] = None,
    include_types: Sequence[str] = ("pathlike_folder", "old_backup_root", "nested_repo_git", "nested_repo_copy_high_score"),
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    report = run_doctor(canonical_root, apply=False, max_depth=max_depth, scan_base=scan_base)

    approved = [
        item["candidate_id"]
        for item in report["candidates"]
        if item.get("disposition") == "pending"
        and item.get("candidate_type") in set(include_types)
    ]

    state = _load_state(canonical_root)
    state["approved_quarantine_ids"] = sorted(set(state.get("approved_quarantine_ids", [])).union(set(approved)))
    _save_state(canonical_root, state)

    return apply_approved_quarantine(canonical_root, max_depth=max_depth, scan_base=scan_base)


def run_full_fix(root: Path, *, max_depth: int = 6, scan_base: Optional[Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    salvage_plan = build_salvage_plan(canonical_root, max_depth=max_depth, scan_base=scan_base)

    if salvage_plan["summary"].get("blocked", False):
        report = run_doctor(canonical_root, apply=False, max_depth=max_depth, scan_base=scan_base)
        return {
            "status": "blocked",
            "reason": "salvage_conflict_threshold",
            "salvage_plan": salvage_plan,
            "report": report,
        }

    salvage_apply = apply_salvage_plan(canonical_root)
    quarantine = apply_default_quarantine(canonical_root, max_depth=max_depth, scan_base=scan_base)
    final_report = quarantine["report"]

    return {
        "status": "ok",
        "salvage_plan": salvage_plan,
        "salvage_apply": salvage_apply,
        "quarantine": quarantine,
        "report": final_report,
    }


def write_fix_log(result: Dict[str, Any], root: Path) -> str:
    canonical_root = get_canonical_root(root)
    logs_dir = canonical_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    fix_path = logs_dir / "repo_reality_fix_latest.json"
    _save_json(fix_path, result)
    return fix_path.resolve().relative_to(canonical_root.resolve()).as_posix()


def _render_markdown(report: Dict[str, Any], json_rel_path: str, log_rel_path: str) -> str:
    lines: List[str] = []
    lines.append("# Repo Reality Report")
    lines.append("")
    lines.append(f"- Canonical root: `{report['canonical_root']}`")
    lines.append(f"- Pinned root: `{report.get('pinned_root', '') or '(not set)'}`")
    lines.append(f"- Scan base: `{report.get('scan_base', '')}`")
    lines.append(f"- Candidate count: {report['summary']['candidate_count']}")
    lines.append(f"- Pending count: {report['summary']['pending_count']}")
    lines.append(f"- Pathlike pending: {report['summary'].get('pathlike_count', 0)}")
    lines.append(f"- Backup pending: {report['summary'].get('backup_count', 0)}")
    lines.append(f"- Nested git pending: {report['summary']['nested_git_count']}")
    lines.append(f"- Needs user count: {report['summary']['needs_user_count']}")
    lines.append(f"- JSON report: `{json_rel_path}`")
    lines.append(f"- Log report: `{log_rel_path}`")
    lines.append("")
    lines.append("## Candidates")
    lines.append("")

    if not report["candidates"]:
        lines.append("- No nested repo candidates found.")
    else:
        for item in report["candidates"]:
            lines.append(
                "- `{path}` | id={candidate_id} | type={candidate_type} | disposition={disposition} | "
                "score={score} | safe_to_move={safe_to_move} | needs_user={needs_user}".format(**item)
            )

    return "\n".join(lines) + "\n"


def write_reports(report: Dict[str, Any], root: Path) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    docs_dir = canonical_root / "docs" / "_inbox"
    logs_dir = canonical_root / "logs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    json_path = docs_dir / "repo_reality_report_latest.json"
    md_path = docs_dir / "repo_reality_report_latest.md"
    log_path = logs_dir / "repo_reality_doctor_latest.json"

    _save_json(json_path, report)
    _save_json(log_path, report)

    md_payload = _render_markdown(
        report,
        json_rel_path=json_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        log_rel_path=log_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
    )
    md_path.write_text(md_payload, encoding="utf-8")

    return {
        "json": json_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "log": log_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "markdown": md_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repo Reality Doctor")
    parser.add_argument("--root", default=".", help="Anchor path")
    parser.add_argument("--scan", action="store_true", help="Scan candidates")
    parser.add_argument("--apply", action="store_true", help="Apply approved quarantine queue")
    parser.add_argument("--salvage", action="store_true", help="Build salvage plan")
    parser.add_argument("--apply-salvage", action="store_true", help="Apply latest salvage plan")
    parser.add_argument("--fix", action="store_true", help="Run salvage + apply + quarantine defaults")
    parser.add_argument("--json", action="store_true", help="Print machine summary")
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--scan-base", default="")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    scan_base = Path(args.scan_base).resolve() if args.scan_base else None

    if args.fix:
        result = run_full_fix(root, max_depth=max(2, args.max_depth), scan_base=scan_base)
        fix_path = write_fix_log(result, root)
        report = result.get("report", run_doctor(root, apply=False, max_depth=max(2, args.max_depth), scan_base=scan_base))
        paths = write_reports(report, root)
        summary = {
            "canonical_root": report["canonical_root"],
            "paths": paths,
            "status": result.get("status", "ok"),
            "fix_log": fix_path,
            "summary": report["summary"],
        }
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if result.get("status") != "blocked" else 3

    if args.salvage:
        plan = build_salvage_plan(root, max_depth=max(2, args.max_depth), scan_base=scan_base)
        print(json.dumps({"canonical_root": plan["canonical_root"], "paths": plan.get("paths", {}), "summary": plan["summary"]}, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.apply_salvage:
        result = apply_salvage_plan(root)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if result.get("ok") else 3

    if args.apply:
        applied = apply_approved_quarantine(root, max_depth=max(2, args.max_depth), scan_base=scan_base)
        report = applied["report"]
        fix_path = write_fix_log(applied, root)
    else:
        report = run_doctor(root, apply=False, max_depth=max(2, args.max_depth), scan_base=scan_base)
        fix_path = ""

    paths = write_reports(report, root)

    summary = {
        "canonical_root": report["canonical_root"],
        "paths": paths,
        "summary": report["summary"],
    }
    if fix_path:
        summary["fix_log"] = fix_path

    if args.json or args.scan or (not args.apply and not args.salvage and not args.apply_salvage):
        print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        for key in ["markdown", "json", "log"]:
            print(paths[key])
        if fix_path:
            print(fix_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

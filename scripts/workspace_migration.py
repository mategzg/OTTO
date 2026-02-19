#!/usr/bin/env python3
"""Deterministic workspace migration with no-loss and no-overwrite semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root, is_pathlike_component

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
    "brain",
    "memory",
    "docs",
    "openclaw",
    "scripts",
    "tests",
    "ops",
    "vault",
    "state",
    "logs",
    "workers",
    "dashboard",
    "plans",
    "templates",
    "copilots",
}

EXCLUDED_DIR_NAMES: Set[str] = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
}

ROOT_DOTFILES_ALLOWLIST: Set[str] = {
    ".gitignore",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _stable_source_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:10]


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_copy(rel: Path) -> bool:
    if not rel.parts:
        return False
    top = rel.parts[0]
    if top in CANONICAL_DIRS:
        return True
    if len(rel.parts) == 1 and rel.name in ROOT_DOTFILES_ALLOWLIST:
        return True
    return rel.suffix.lower() in VALUE_EXTENSIONS


def _iter_source_files(source_root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(source_root, topdown=True, followlinks=False):
        current = Path(dirpath)
        pruned = []
        for name in sorted(dirnames):
            if name in EXCLUDED_DIR_NAMES:
                continue
            pruned.append(name)
        dirnames[:] = pruned

        for filename in sorted(filenames):
            src = current / filename
            if src.is_symlink():
                continue
            rel = src.resolve().relative_to(source_root.resolve())
            if not _should_copy(rel):
                continue
            yield src


def _guard_target_rel(rel_text: str) -> bool:
    rel = Path(rel_text)
    return any(is_pathlike_component(part) for part in rel.parts)


def run_workspace_migration(source_root: Path, canonical_root: Path) -> Dict[str, Any]:
    if source_root.resolve() == canonical_root.resolve():
        raise RuntimeError("Source and destination roots must be different.")

    stamp = _stamp()
    source_id = _stable_source_id(source_root)
    stage_root = canonical_root / "vault" / "_salvage" / f"{stamp}_{source_id}"
    staged_dir = stage_root / "staged"
    staged_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []

    for src in _iter_source_files(source_root):
        rel = src.resolve().relative_to(source_root.resolve()).as_posix()
        target = canonical_root / rel
        src_hash = _sha256(src)
        existing_hash = ""
        conflict = False

        if target.exists() and target.is_file():
            try:
                existing_hash = _sha256(target)
            except OSError:
                existing_hash = ""
            if existing_hash and existing_hash != src_hash:
                conflict = True

        if conflict:
            staged_rel = f"{rel}__from_{source_id}"
            action = "conflict"
            conflicts.append(
                {
                    "existing_path": rel,
                    "existing_sha256": existing_hash,
                    "incoming_path": rel,
                    "incoming_sha256": src_hash,
                    "staged_rel": staged_rel,
                }
            )
        else:
            staged_rel = rel
            action = "promote"

        staged_path = staged_dir / staged_rel
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, staged_path)
        stat = src.stat()
        manifest_entries.append(
            {
                "action": action,
                "mtime": stat.st_mtime,
                "rel_path": rel,
                "sha256": src_hash,
                "size": stat.st_size,
                "source_path": str(src),
                "staged_rel": staged_rel,
                "target_rel": rel,
            }
        )

    manifest_entries.sort(key=lambda item: (item["target_rel"], item["source_path"]))
    conflicts.sort(key=lambda item: (item["existing_path"], item["incoming_path"]))

    manifest_payload = {
        "created_at": _utc_now(),
        "destination_root": str(canonical_root.resolve()),
        "entries": manifest_entries,
        "source_id": source_id,
        "source_path": str(source_root.resolve()),
        "version": 1,
    }
    conflicts_payload = {
        "conflicts": conflicts,
        "destination_root": str(canonical_root.resolve()),
        "source_id": source_id,
        "source_path": str(source_root.resolve()),
        "version": 1,
    }

    manifest_path = stage_root / "MANIFEST.json"
    conflicts_path = stage_root / "CONFLICTS.json"
    _save_json(manifest_path, manifest_payload)
    _save_json(conflicts_path, conflicts_payload)

    promoted_count = 0
    skipped_identical = 0
    skipped_conflicts = 0
    skipped_guardrail = 0
    for entry in manifest_entries:
        if entry["action"] == "conflict":
            skipped_conflicts += 1
            continue
        if _guard_target_rel(entry["target_rel"]):
            skipped_guardrail += 1
            continue

        src = staged_dir / entry["staged_rel"]
        dst = canonical_root / entry["target_rel"]
        if not src.is_file():
            continue

        if dst.exists() and dst.is_file():
            try:
                if _sha256(dst) == _sha256(src):
                    skipped_identical += 1
                    continue
            except OSError:
                continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        promoted_count += 1

    report: Dict[str, Any] = {
        "created_at": _utc_now(),
        "destination_root": str(canonical_root.resolve()),
        "source_id": source_id,
        "source_root": str(source_root.resolve()),
        "summary": {
            "entry_count": len(manifest_entries),
            "conflict_count": len(conflicts),
            "promoted_count": promoted_count,
            "skipped_conflicts": skipped_conflicts,
            "skipped_guardrail": skipped_guardrail,
            "skipped_identical": skipped_identical,
        },
        "top_paths": [entry["target_rel"] for entry in manifest_entries[:25]],
        "paths": {
            "manifest": manifest_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "conflicts": conflicts_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        },
        "version": 1,
    }

    docs_dir = canonical_root / "docs" / "_inbox"
    logs_dir = canonical_root / "logs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    md_path = docs_dir / "workspace_migration_report_latest.md"
    json_path = docs_dir / "workspace_migration_report_latest.json"
    log_path = logs_dir / "workspace_migration_latest.json"

    _save_json(json_path, report)
    _save_json(log_path, report)

    lines = [
        "# Workspace Migration Report",
        "",
        f"- Source root: `{report['source_root']}`",
        f"- Destination root: `{report['destination_root']}`",
        f"- Source id: `{report['source_id']}`",
        f"- Entry count: {report['summary']['entry_count']}",
        f"- Conflict count: {report['summary']['conflict_count']}",
        f"- Promoted count: {report['summary']['promoted_count']}",
        f"- Skipped identical: {report['summary']['skipped_identical']}",
        f"- Skipped conflicts: {report['summary']['skipped_conflicts']}",
        f"- Manifest: `{report['paths']['manifest']}`",
        f"- Conflicts: `{report['paths']['conflicts']}`",
        f"- JSON report: `{json_path.resolve().relative_to(canonical_root.resolve()).as_posix()}`",
        f"- Log report: `{log_path.resolve().relative_to(canonical_root.resolve()).as_posix()}`",
        "",
        "## Top Paths",
        "",
    ]
    if report["top_paths"]:
        lines.extend([f"- `{path}`" for path in report["top_paths"]])
    else:
        lines.append("- No files selected.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate canonical workspace with deterministic salvage manifests.")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    canonical_root = get_canonical_root(args.root)
    source_root = Path(args.source_root).resolve()
    report = run_workspace_migration(source_root, canonical_root)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

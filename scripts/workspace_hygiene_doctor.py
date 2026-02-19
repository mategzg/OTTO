#!/usr/bin/env python3
"""Workspace hygiene scan and no-destructive cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root, is_pathlike_component
from scripts.workspace_hygiene_policy import (
    POLICY_PATH,
    assert_policy_root,
    is_ignored_relpath,
    is_sensitive_excluded_relpath,
    is_tooling_name,
    load_policy,
    matches_patterns,
)

REPORT_JSON = "docs/_inbox/workspace_hygiene_report_latest.json"
REPORT_MD = "docs/_inbox/workspace_hygiene_report_latest.md"
REPORT_LOG = "logs/workspace_hygiene_latest.json"

PROTECTED_PREFIXES: Tuple[str, ...] = ("vault/_quarantine", "vault/_salvage", ".git")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_id(rel_path: str, classification: str) -> str:
    raw = f"{classification}:{rel_path}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _is_protected(rel_path: str) -> bool:
    rel = rel_path.strip().strip("/")
    for prefix in PROTECTED_PREFIXES:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    return False


def _classify_name(name: str, *, sensitive_patterns: Sequence[str]) -> Tuple[str, str]:
    if matches_patterns(name, sensitive_patterns):
        return "sensitive", "sensitive_name_pattern"
    if is_pathlike_component(name):
        return "junk", "pathlike_name"
    if name.startswith("_OLD_BAD_PATH_BACKUP"):
        return "junk", "legacy_backup_name"
    return "junk", "not_allowlisted_root_entry"


def _sorted_entries(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda item: (item["rel_path"], item.get("classification", ""), item.get("reason", "")))


def _scan_nested_candidates(root: Path, policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: Dict[str, Dict[str, Any]] = {}
    tooling_dirs = set(policy.get("tooling_dirs", []))
    sensitive_patterns = policy.get("sensitive_name_patterns", [])

    for top in sorted(policy.get("allowlist_root_dirs", [])):
        if top in tooling_dirs:
            continue
        start = root / top
        if not start.exists() or not start.is_dir():
            continue

        for dirpath, dirnames, filenames in os.walk(start, topdown=True, followlinks=False):
            current = Path(dirpath)
            rel_current = current.resolve().relative_to(root.resolve()).as_posix()

            pruned: List[str] = []
            for dirname in sorted(dirnames):
                child = current / dirname
                child_rel = child.resolve().relative_to(root.resolve()).as_posix()
                if is_tooling_name(dirname, policy):
                    continue
                if _is_protected(child_rel):
                    continue
                if is_ignored_relpath(child_rel, policy):
                    continue
                pruned.append(dirname)
            dirnames[:] = pruned

            if _is_protected(rel_current) or is_ignored_relpath(rel_current, policy):
                continue

            if is_pathlike_component(current.name):
                candidates[rel_current] = {
                    "candidate_id": _candidate_id(rel_current, "junk"),
                    "classification": "junk",
                    "kind": "dir",
                    "reason": "pathlike_name",
                    "rel_path": rel_current,
                    "safe_to_move": True,
                    "scope": "nested",
                }

            for filename in sorted(filenames):
                file_path = current / filename
                if file_path.is_symlink():
                    continue
                rel = file_path.resolve().relative_to(root.resolve()).as_posix()
                if _is_protected(rel) or is_ignored_relpath(rel, policy):
                    continue
                if matches_patterns(filename, sensitive_patterns) and not is_sensitive_excluded_relpath(rel, policy):
                    candidates[rel] = {
                        "candidate_id": _candidate_id(rel, "sensitive"),
                        "classification": "sensitive",
                        "kind": "file",
                        "reason": "sensitive_name_pattern",
                        "rel_path": rel,
                        "safe_to_move": True,
                        "scope": "nested",
                    }
                elif is_pathlike_component(filename):
                    candidates[rel] = {
                        "candidate_id": _candidate_id(rel, "junk"),
                        "classification": "junk",
                        "kind": "file",
                        "reason": "pathlike_name",
                        "rel_path": rel,
                        "safe_to_move": True,
                        "scope": "nested",
                    }
    return _sorted_entries(candidates.values())


def scan_workspace(root: Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_policy(canonical_root, create_if_missing=True)
    assert_policy_root(canonical_root, policy)

    allow_dirs = set(policy.get("allowlist_root_dirs", []))
    allow_files = set(policy.get("allowlist_root_files", []))
    sensitive_patterns = policy.get("sensitive_name_patterns", [])

    entries: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    top_level = sorted(canonical_root.iterdir(), key=lambda p: p.name)

    for item in top_level:
        name = item.name
        rel = name
        kind = "dir" if item.is_dir() else "file"

        if _is_protected(rel):
            classification = "tooling"
            reason = "protected_prefix"
            safe_to_move = False
        elif is_tooling_name(name, policy) or (name.startswith(".") and name not in allow_dirs and name not in allow_files):
            classification = "tooling"
            reason = "tooling_dir"
            safe_to_move = False
        elif kind == "dir" and name in allow_dirs:
            classification = "canon"
            reason = "allowlist_root_dir"
            safe_to_move = False
        elif kind == "file" and name in allow_files:
            classification = "canon"
            reason = "allowlist_root_file"
            safe_to_move = False
        else:
            classification, reason = _classify_name(name, sensitive_patterns=sensitive_patterns)
            safe_to_move = True

        entry = {
            "candidate_id": _candidate_id(rel, classification),
            "classification": classification,
            "kind": kind,
            "reason": reason,
            "rel_path": rel,
            "safe_to_move": safe_to_move,
            "scope": "root",
        }
        entries.append(entry)
        if classification in {"junk", "sensitive"}:
            candidates.append(entry)

    nested_candidates = _scan_nested_candidates(canonical_root, policy)
    entries.extend(nested_candidates)
    candidates.extend(nested_candidates)

    entries = _sorted_entries(entries)

    unique_candidates: Dict[str, Dict[str, Any]] = {}
    for item in candidates:
        rel = item["rel_path"]
        if rel not in unique_candidates:
            unique_candidates[rel] = item
            continue
        current = unique_candidates[rel]
        priority = {"sensitive": 2, "junk": 1}
        if priority.get(item["classification"], 0) > priority.get(current["classification"], 0):
            unique_candidates[rel] = item

    clean_candidates = _sorted_entries(unique_candidates.values())

    summary = {
        "canon_count": sum(1 for item in entries if item["classification"] == "canon"),
        "tooling_count": sum(1 for item in entries if item["classification"] == "tooling"),
        "junk_count": sum(1 for item in entries if item["classification"] == "junk"),
        "sensitive_count": sum(1 for item in entries if item["classification"] == "sensitive"),
        "candidate_count": len(clean_candidates),
    }

    return {
        "canonical_root": str(canonical_root),
        "created_at": _utc_now(),
        "entries": entries,
        "clean_candidates": clean_candidates,
        "policy": {
            "path": POLICY_PATH.as_posix(),
            "version": policy.get("version", 1),
        },
        "summary": summary,
        "version": 1,
    }


def _manifest_entries_for_payload(payload: Path, *, source_abs: Path, rel_path: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []

    if payload.is_file():
        stat = payload.stat()
        entries.append(
            {
                "mtime": stat.st_mtime,
                "rel_path": rel_path,
                "sha256": _sha256(payload),
                "size": stat.st_size,
                "source_path": str(source_abs),
            }
        )
        return entries

    for dirpath, _dirnames, filenames in os.walk(payload, topdown=True, followlinks=False):
        current = Path(dirpath)
        for filename in sorted(filenames):
            fp = current / filename
            if fp.is_symlink():
                continue
            sub = fp.resolve().relative_to(payload.resolve()).as_posix()
            source_path = source_abs / sub
            stat = fp.stat()
            entries.append(
                {
                    "mtime": stat.st_mtime,
                    "rel_path": f"{rel_path}/{sub}",
                    "sha256": _sha256(fp),
                    "size": stat.st_size,
                    "source_path": str(source_path),
                }
            )

    entries.sort(key=lambda item: item["rel_path"])
    return entries


def _write_quarantine_bundle(
    root: Path,
    *,
    source_rel: str,
    classification: str,
    reason: str,
    candidate_id: str,
    stamp: str,
) -> Dict[str, Any]:
    source = root / source_rel
    if not source.exists():
        return {"moved": False, "reason": "missing_source", "source_rel": source_rel}

    bucket = "secrets" if classification == "sensitive" else "root_junk"
    dest = root / "vault" / "_quarantine" / bucket / f"{stamp}_{candidate_id}"
    suffix = 1
    while dest.exists():
        dest = root / "vault" / "_quarantine" / bucket / f"{stamp}_{candidate_id}_{suffix}"
        suffix += 1
    dest.mkdir(parents=True, exist_ok=True)

    payload = dest / "payload"
    source_abs = source.resolve()
    shutil.move(str(source), str(payload))

    manifest_entries = _manifest_entries_for_payload(payload, source_abs=source_abs, rel_path=source_rel)
    manifest = {
        "candidate_id": candidate_id,
        "classification": classification,
        "created_at": _utc_now(),
        "entries": manifest_entries,
        "reason": reason,
        "source_rel": source_rel,
    }
    manifest_path = dest / "MANIFEST.json"
    _save_json(manifest_path, manifest)

    readme = dest / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Workspace Quarantine",
                "",
                f"- Source rel: `{source_rel}`",
                f"- Classification: `{classification}`",
                f"- Reason: `{reason}`",
                f"- Candidate ID: `{candidate_id}`",
                f"- Created at: `{manifest['created_at']}`",
                f"- File count: {len(manifest_entries)}",
                "- Payload path: `payload`",
                "- Manifest path: `MANIFEST.json`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "moved": True,
        "classification": classification,
        "candidate_id": candidate_id,
        "source_rel": source_rel,
        "reason": reason,
        "manifest": manifest_path.resolve().relative_to(root.resolve()).as_posix(),
        "readme": readme.resolve().relative_to(root.resolve()).as_posix(),
        "quarantine_path": dest.resolve().relative_to(root.resolve()).as_posix(),
    }


def write_workspace_reports(report: Dict[str, Any], root: Path) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    json_path = canonical_root / REPORT_JSON
    md_path = canonical_root / REPORT_MD
    log_path = canonical_root / REPORT_LOG

    _save_json(json_path, report)
    _save_json(log_path, report)

    lines = [
        "# Workspace Hygiene Report",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Candidate count: {report['summary']['candidate_count']}",
        f"- Junk: {report['summary']['junk_count']}",
        f"- Sensitive: {report['summary']['sensitive_count']}",
        f"- Tooling: {report['summary']['tooling_count']}",
        f"- Canon: {report['summary']['canon_count']}",
        f"- JSON report: `{REPORT_JSON}`",
        f"- Log report: `{REPORT_LOG}`",
        "",
        "## Candidates",
        "",
    ]
    if not report["clean_candidates"]:
        lines.append("- No clean candidates.")
    else:
        for item in report["clean_candidates"]:
            lines.append(
                f"- `{item['rel_path']}` | class={item['classification']} | reason={item['reason']} | safe={item['safe_to_move']}"
            )

    if report.get("clean_result"):
        lines.extend(["", "## Clean Result", ""])
        result = report["clean_result"]
        lines.append(f"- Status: `{result['status']}`")
        lines.append(f"- Moved count: {result.get('moved_count', 0)}")
        lines.append(f"- Skipped missing: {result.get('skipped_missing', 0)}")
        lines.append(f"- Blocked reason: `{result.get('blocked_reason', '')}`")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": REPORT_JSON, "markdown": REPORT_MD, "log": REPORT_LOG}


def run_workspace_scan(root: Path) -> Dict[str, Any]:
    report = scan_workspace(root)
    paths = write_workspace_reports(report, root)
    return {"report": report, "paths": paths, "status": "ok"}


def run_workspace_clean(root: Path, *, max_moves: int = 500) -> Dict[str, Any]:
    report = scan_workspace(root)
    canonical_root = Path(report["canonical_root"]).resolve()
    policy = load_policy(canonical_root, create_if_missing=True)

    candidates = [item for item in report["clean_candidates"] if item.get("safe_to_move")]
    if len(candidates) > max_moves:
        result = {
            "status": "blocked",
            "blocked_reason": "move_limit_exceeded",
            "candidate_count": len(candidates),
            "moved_count": 0,
            "moved": [],
            "skipped_missing": 0,
        }
        report["clean_result"] = result
        paths = write_workspace_reports(report, canonical_root)
        return {"status": "blocked", "report": report, "paths": paths, "result": result}

    allow_roots = set(policy.get("allowlist_root_dirs", []) + policy.get("allowlist_root_files", []))
    for item in candidates:
        top = item["rel_path"].split("/", 1)[0]
        if item["classification"] == "junk" and top in allow_roots:
            result = {
                "status": "blocked",
                "blocked_reason": "canon_candidate_detected",
                "candidate_count": len(candidates),
                "moved_count": 0,
                "moved": [],
                "skipped_missing": 0,
            }
            report["clean_result"] = result
            paths = write_workspace_reports(report, canonical_root)
            return {"status": "blocked", "report": report, "paths": paths, "result": result}

    moved: List[Dict[str, Any]] = []
    skipped_missing = 0
    stamp = _stamp()

    for item in sorted(candidates, key=lambda c: (-c["rel_path"].count("/"), c["rel_path"])):
        rel = item["rel_path"]
        if _is_protected(rel):
            continue
        source = canonical_root / rel
        if not source.exists():
            skipped_missing += 1
            continue
        move_out = _write_quarantine_bundle(
            canonical_root,
            source_rel=rel,
            classification=item["classification"],
            reason=item["reason"],
            candidate_id=item["candidate_id"],
            stamp=stamp,
        )
        if move_out.get("moved"):
            moved.append(move_out)
        elif move_out.get("reason") == "missing_source":
            skipped_missing += 1

    result = {
        "status": "ok",
        "blocked_reason": "",
        "candidate_count": len(candidates),
        "moved_count": len(moved),
        "moved": sorted(moved, key=lambda item: item["source_rel"]),
        "skipped_missing": skipped_missing,
    }
    report["clean_result"] = result
    paths = write_workspace_reports(report, canonical_root)
    return {"status": "ok", "report": report, "paths": paths, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Workspace hygiene doctor")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--max-moves", type=int, default=500)
    args = parser.parse_args()

    if args.scan and args.clean:
        parser.error("Choose --scan or --clean, not both.")

    if args.clean:
        result = run_workspace_clean(Path(args.root), max_moves=max(1, args.max_moves))
        print(
            json.dumps(
                {
                    "canonical_root": result["report"]["canonical_root"],
                    "paths": result["paths"],
                    "result": result["result"],
                    "summary": result["report"]["summary"],
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 0 if result["status"] == "ok" else 3

    out = run_workspace_scan(Path(args.root))
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "paths": out["paths"],
                "summary": out["report"]["summary"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

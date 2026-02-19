#!/usr/bin/env python3
"""Instruction surface doctor: detect and quarantine reserved instruction files outside allowlist."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root
from scripts.workspace_hygiene_policy import assert_policy_root, is_ignored_relpath, load_policy

POLICY_PATH = Path("state/instruction_surface_policy.json")
REPORT_JSON = Path("docs/_inbox/instruction_surface_report_latest.json")
REPORT_MD = Path("docs/_inbox/instruction_surface_report_latest.md")
REPORT_LOG = Path("logs/instruction_surface_latest.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "reserved_filenames": [
        "AGENTS.md",
        "AGENTS.override.md",
        "CLAUDE.md",
        "CLAUDE.local.md",
    ],
    "allowed_locations": {
        "codex": ["AGENTS.md", "AGENTS.override.md"],
        "claude_code": ["CLAUDE.md", "CLAUDE.local.md", ".claude/CLAUDE.md", ".claude/rules/**"],
    },
    "quarantine_root": "vault/_quarantine/instruction_drift",
    "severity_rules": {
        "drift_grave_prefixes": ["brain/", "openclaw/", "scripts/", "memory/"],
        "drift_default": "drift",
        "drift_grave": "drift_grave",
    },
    "fix_mode_default": "auto_quarantine",
}


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


def _normalize_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(DEFAULT_POLICY)
    merged.update(policy or {})
    merged["allowed_locations"] = dict(DEFAULT_POLICY["allowed_locations"]) | dict(merged.get("allowed_locations", {}))
    merged["severity_rules"] = dict(DEFAULT_POLICY["severity_rules"]) | dict(merged.get("severity_rules", {}))
    merged["reserved_filenames"] = list(merged.get("reserved_filenames", DEFAULT_POLICY["reserved_filenames"]))
    return merged


def load_instruction_surface_policy(root: Path, *, create_if_missing: bool = True) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    path = canonical_root / POLICY_PATH

    payload: Dict[str, Any] = {}
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed

    policy = _normalize_policy(payload)
    if create_if_missing and not path.is_file():
        _save_json(path, policy)
    return policy


def _allowed_patterns(policy: Dict[str, Any]) -> List[str]:
    allowed: List[str] = []
    for _owner, patterns in sorted(policy.get("allowed_locations", {}).items()):
        for pattern in patterns:
            text = str(pattern).strip().strip("/")
            if text:
                allowed.append(text)
    return sorted(set(allowed))


def _is_allowed(rel_path: str, patterns: Sequence[str]) -> bool:
    rel = rel_path.strip().strip("/")
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
    return False


def _is_drift_grave(rel_path: str, policy: Dict[str, Any]) -> bool:
    rel = rel_path.strip().strip("/")
    for prefix in policy.get("severity_rules", {}).get("drift_grave_prefixes", []):
        clean = str(prefix).strip().strip("/")
        if not clean:
            continue
        if rel == clean or rel.startswith(clean + "/"):
            return True
    return False


def _looks_like_accidental_dump(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False

    if b"\x00" in data:
        return True
    if len(data) > 200_000:
        return True

    text = data.decode("utf-8", errors="ignore")
    if text.count("\n") > 2000:
        return True
    if "BEGIN PGP" in text or "PRIVATE KEY" in text:
        return True
    return False


def _iter_reserved_files(root: Path, policy: Dict[str, Any], hygiene_policy: Dict[str, Any]) -> Iterable[Path]:
    reserved = {name.lower() for name in policy.get("reserved_filenames", [])}
    tooling = set(hygiene_policy.get("tooling_dirs", []))

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        rel_current = current.resolve().relative_to(root.resolve()).as_posix()

        kept_dirs: List[str] = []
        for dirname in sorted(dirnames):
            if dirname in tooling and dirname != ".claude":
                continue
            child = current / dirname
            child_rel = child.resolve().relative_to(root.resolve()).as_posix()
            if is_ignored_relpath(child_rel, hygiene_policy):
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        if is_ignored_relpath(rel_current, hygiene_policy):
            continue

        for filename in sorted(filenames):
            if filename.lower() not in reserved:
                continue
            file_path = current / filename
            if file_path.is_symlink():
                continue
            yield file_path


def build_surface_scan_report(root: Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_instruction_surface_policy(canonical_root, create_if_missing=True)
    hygiene_policy = load_policy(canonical_root, create_if_missing=True)
    assert_policy_root(canonical_root, hygiene_policy)

    allowed_patterns = _allowed_patterns(policy)
    items: List[Dict[str, Any]] = []

    for file_path in _iter_reserved_files(canonical_root, policy, hygiene_policy):
        rel = file_path.resolve().relative_to(canonical_root.resolve()).as_posix()
        stat = file_path.stat()
        allowed = _is_allowed(rel, allowed_patterns)

        if allowed:
            classification = "allowed"
            severity = "allowed"
        elif _is_drift_grave(rel, policy):
            classification = "drift_grave"
            severity = policy.get("severity_rules", {}).get("drift_grave", "drift_grave")
        else:
            classification = "drift"
            severity = policy.get("severity_rules", {}).get("drift_default", "drift")

        needs_user = allowed and _looks_like_accidental_dump(file_path)

        items.append(
            {
                "candidate_id": hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10],
                "classification": classification,
                "filename": file_path.name,
                "mtime": stat.st_mtime,
                "needs_user": needs_user,
                "path": rel,
                "severity": severity,
                "sha256": _sha256(file_path),
                "size": stat.st_size,
            }
        )

    items.sort(key=lambda item: item["path"])

    drift_items = [item for item in items if item["classification"] in {"drift", "drift_grave"}]
    summary = {
        "allowed_count": sum(1 for item in items if item["classification"] == "allowed"),
        "drift_count": len(drift_items),
        "drift_grave_count": sum(1 for item in items if item["classification"] == "drift_grave"),
        "needs_user_count": sum(1 for item in items if item.get("needs_user")),
        "reserved_found": len(items),
    }

    return {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "items": items,
        "policy_path": POLICY_PATH.as_posix(),
        "quarantine_root": str(policy.get("quarantine_root", DEFAULT_POLICY["quarantine_root"])),
        "summary": summary,
        "version": 1,
    }


def _write_surface_reports(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines: List[str] = [
        "# Instruction Surface Report",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Policy: `{report['policy_path']}`",
        f"- Reserved found: {report['summary']['reserved_found']}",
        f"- Drift count: {report['summary']['drift_count']}",
        f"- Drift grave count: {report['summary']['drift_grave_count']}",
        f"- Allowed count: {report['summary']['allowed_count']}",
        f"- Needs user count: {report['summary']['needs_user_count']}",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Items",
        "",
    ]

    if not report["items"]:
        lines.append("- No reserved filenames found.")
    else:
        for item in report["items"]:
            lines.append(
                f"- `{item['path']}` | class={item['classification']} | needs_user={item['needs_user']} | size={item['size']}"
            )

    if report.get("fix_actions"):
        lines.extend(["", "## Fix Actions", ""])
        for action in report["fix_actions"]:
            lines.append(
                f"- moved `{action['origin_path']}` -> `{action['quarantine_path']}` | severity={action['severity']} | manifest=`{action['manifest_path']}`"
            )

    md_path = canonical_root / REPORT_MD
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()}


def run_surface_scan(root: Path) -> Dict[str, Any]:
    report = build_surface_scan_report(root)
    paths = _write_surface_reports(root, report)
    return {"report": report, "paths": paths}


def _safe_quarantine_dest(bucket_source_root: Path, rel_path: str, candidate_id: str) -> Path:
    dst = bucket_source_root / rel_path
    if not dst.exists():
        return dst

    base = dst.with_suffix("") if dst.suffix else dst
    ext = dst.suffix
    idx = 1
    while True:
        candidate = Path(f"{base}__from_{candidate_id}_{idx}{ext}")
        if not candidate.exists():
            return candidate
        idx += 1


def _write_quarantine_docs(
    *,
    bucket: Path,
    origin_abs: Path,
    origin_rel: str,
    quarantine_rel: str,
    item: Dict[str, Any],
) -> Dict[str, str]:
    manifest = {
        "created_at": _utc_now(),
        "entries": [
            {
                "mtime": item["mtime"],
                "origin_path": str(origin_abs),
                "rel_path": origin_rel,
                "quarantine_rel_path": quarantine_rel,
                "severity": item["severity"],
                "sha256": item["sha256"],
                "size": item["size"],
            }
        ],
        "entry_count": 1,
        "version": 1,
    }
    manifest_path = bucket / "MANIFEST.json"
    _save_json(manifest_path, manifest)

    readme_path = bucket / "README.md"
    readme_path.write_text(
        "\n".join(
            [
                "# Instruction Drift Quarantine",
                "",
                f"- Origin path: `{origin_abs}`",
                f"- Origin rel: `{origin_rel}`",
                f"- Severity: `{item['severity']}`",
                f"- Candidate id: `{item['candidate_id']}`",
                "- Reason: reserved instruction filename found outside allowlist.",
                "- Policy: `state/instruction_surface_policy.json`.",
                "- Manifest: `MANIFEST.json`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "manifest_path": manifest_path,
        "readme_path": readme_path,
    }


def run_surface_fix(root: Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    pre_report = build_surface_scan_report(canonical_root)
    policy = load_instruction_surface_policy(canonical_root, create_if_missing=True)
    quarantine_root_rel = str(policy.get("quarantine_root", DEFAULT_POLICY["quarantine_root"])).strip("/")
    quarantine_root = canonical_root / quarantine_root_rel

    actions: List[Dict[str, Any]] = []
    stamp = _stamp()

    for item in [x for x in pre_report["items"] if x["classification"] in {"drift", "drift_grave"}]:
        rel = item["path"]
        src = canonical_root / rel
        if not src.exists():
            continue

        # Safety: never move policy-allowed locations.
        if _is_allowed(rel, _allowed_patterns(policy)):
            continue

        bucket = quarantine_root / f"{stamp}_{item['candidate_id']}"
        bucket_source = bucket / "source"
        bucket_source.mkdir(parents=True, exist_ok=True)

        dst = _safe_quarantine_dest(bucket_source, rel, item["candidate_id"])
        dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(src), str(dst))

        quarantine_rel = dst.resolve().relative_to(canonical_root.resolve()).as_posix()
        docs = _write_quarantine_docs(
            bucket=bucket,
            origin_abs=src,
            origin_rel=rel,
            quarantine_rel=quarantine_rel,
            item=item,
        )

        actions.append(
            {
                "candidate_id": item["candidate_id"],
                "manifest_path": docs["manifest_path"].resolve().relative_to(canonical_root.resolve()).as_posix(),
                "origin_path": rel,
                "quarantine_path": quarantine_rel,
                "readme_path": docs["readme_path"].resolve().relative_to(canonical_root.resolve()).as_posix(),
                "severity": item["severity"],
            }
        )

    actions.sort(key=lambda item: item["origin_path"])
    post_report = build_surface_scan_report(canonical_root)
    post_report["fix_actions"] = actions
    post_report["fix_summary"] = {
        "moved_count": len(actions),
        "pre_drift_count": pre_report["summary"]["drift_count"],
        "post_drift_count": post_report["summary"]["drift_count"],
        "post_drift_grave_count": post_report["summary"]["drift_grave_count"],
    }
    paths = _write_surface_reports(canonical_root, post_report)

    return {
        "paths": paths,
        "pre_report": pre_report,
        "report": post_report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Instruction surface doctor")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()

    if args.scan and args.fix:
        parser.error("Use either --scan or --fix")

    root = Path(args.root)
    if args.fix:
        out = run_surface_fix(root)
        print(
            json.dumps(
                {
                    "canonical_root": out["report"]["canonical_root"],
                    "paths": out["paths"],
                    "summary": out["report"]["summary"],
                    "fix_summary": out["report"].get("fix_summary", {}),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 0 if out["report"]["summary"]["drift_grave_count"] == 0 else 3

    out = run_surface_scan(root)
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

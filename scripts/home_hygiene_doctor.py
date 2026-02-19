#!/usr/bin/env python3
"""Home hygiene scan and obvious-junk quarantine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root, is_pathlike_component
from scripts.workspace_hygiene_policy import (
    POLICY_PATH,
    assert_policy_root,
    load_policy,
    matches_patterns,
)

REPORT_JSON = "docs/_inbox/home_hygiene_report_latest.json"
REPORT_MD = "docs/_inbox/home_hygiene_report_latest.md"
REPORT_LOG = "logs/home_hygiene_latest.json"


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


def _candidate_id(abs_path: Path) -> str:
    return hashlib.sha1(str(abs_path.resolve()).encode("utf-8")).hexdigest()[:10]


def _is_obvious_junk_name(name: str, patterns: Sequence[str]) -> bool:
    if is_pathlike_component(name):
        return True
    if name.startswith("_OLD_BAD_PATH_BACKUP"):
        return True
    return matches_patterns(name, patterns)


def _classify_home_entry(path: Path, *, patterns: Sequence[str], sensitive_patterns: Sequence[str]) -> Dict[str, Any]:
    name = path.name
    if path.is_file() and matches_patterns(name, sensitive_patterns):
        return {"classification": "sensitive", "reason": "sensitive_name_pattern"}
    if _is_obvious_junk_name(name, patterns):
        return {"classification": "junk", "reason": "obvious_junk_name"}
    return {"classification": "canon", "reason": "not_obvious_junk"}


def scan_home(workspace_root: Path, home_root: Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(workspace_root)
    policy = load_policy(canonical_root, create_if_missing=True)
    assert_policy_root(canonical_root, policy)

    entries: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []
    skipped_dotdirs = 0

    for item in sorted(home_root.iterdir(), key=lambda p: p.name):
        name = item.name
        if name.startswith("."):
            skipped_dotdirs += 1
            entries.append(
                {
                    "candidate_id": _candidate_id(item),
                    "classification": "tooling",
                    "kind": "dir" if item.is_dir() else "file",
                    "path": str(item.resolve()),
                    "reason": "dot_dir_or_dot_file_skipped",
                    "safe_to_move": False,
                }
            )
            continue

        if item.resolve() == canonical_root.resolve():
            entries.append(
                {
                    "candidate_id": _candidate_id(item),
                    "classification": "canon",
                    "kind": "dir" if item.is_dir() else "file",
                    "path": str(item.resolve()),
                    "reason": "canonical_workspace",
                    "safe_to_move": False,
                }
            )
            continue

        c = _classify_home_entry(
            item,
            patterns=policy.get("obvio_junk_patterns_home", []),
            sensitive_patterns=policy.get("sensitive_name_patterns", []),
        )
        entry = {
            "candidate_id": _candidate_id(item),
            "classification": c["classification"],
            "kind": "dir" if item.is_dir() else "file",
            "path": str(item.resolve()),
            "reason": c["reason"],
            "safe_to_move": c["classification"] in {"junk", "sensitive"},
        }
        entries.append(entry)
        if entry["safe_to_move"]:
            candidates.append(entry)

    entries.sort(key=lambda item: item["path"])
    candidates.sort(key=lambda item: item["path"])

    summary = {
        "entry_count": len(entries),
        "candidate_count": len(candidates),
        "junk_count": sum(1 for item in candidates if item["classification"] == "junk"),
        "sensitive_count": sum(1 for item in candidates if item["classification"] == "sensitive"),
        "skipped_dotdirs": skipped_dotdirs,
    }
    return {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "home_root": str(home_root.resolve()),
        "entries": entries,
        "candidates": candidates,
        "policy": {"path": POLICY_PATH.as_posix(), "version": policy.get("version", 1)},
        "summary": summary,
        "version": 1,
    }


def _manifest_entries(payload: Path, source_abs: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if payload.is_file():
        stat = payload.stat()
        out.append(
            {
                "mtime": stat.st_mtime,
                "rel_path": source_abs.name,
                "sha256": _sha256(payload),
                "size": stat.st_size,
                "source_path": str(source_abs),
            }
        )
        return out

    for dirpath, _dirnames, filenames in os.walk(payload, topdown=True, followlinks=False):
        current = Path(dirpath)
        for filename in sorted(filenames):
            fp = current / filename
            if fp.is_symlink():
                continue
            sub = fp.resolve().relative_to(payload.resolve()).as_posix()
            stat = fp.stat()
            out.append(
                {
                    "mtime": stat.st_mtime,
                    "rel_path": f"{source_abs.name}/{sub}",
                    "sha256": _sha256(fp),
                    "size": stat.st_size,
                    "source_path": str(source_abs / sub),
                }
            )
    out.sort(key=lambda item: item["rel_path"])
    return out


def _move_to_quarantine(workspace_root: Path, candidate: Dict[str, Any], stamp: str) -> Dict[str, Any]:
    source = Path(candidate["path"]).resolve()
    if not source.exists():
        return {"moved": False, "reason": "missing_source", "path": str(source)}

    cid = candidate["candidate_id"]
    dest = workspace_root / "vault" / "_quarantine" / "home_junk" / f"{stamp}_{cid}"
    suffix = 1
    while dest.exists():
        dest = workspace_root / "vault" / "_quarantine" / "home_junk" / f"{stamp}_{cid}_{suffix}"
        suffix += 1
    dest.mkdir(parents=True, exist_ok=True)

    payload = dest / "payload"
    shutil.move(str(source), str(payload))

    entries = _manifest_entries(payload, source)
    manifest = {
        "candidate_id": cid,
        "classification": candidate["classification"],
        "created_at": _utc_now(),
        "entries": entries,
        "reason": candidate["reason"],
        "source_path": str(source),
    }
    manifest_path = dest / "MANIFEST.json"
    _save_json(manifest_path, manifest)

    readme = dest / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Home Junk Quarantine",
                "",
                f"- Source path: `{source}`",
                f"- Classification: `{candidate['classification']}`",
                f"- Reason: `{candidate['reason']}`",
                f"- Candidate ID: `{cid}`",
                f"- Created at: `{manifest['created_at']}`",
                f"- File count: {len(entries)}",
                "- Payload path: `payload`",
                "- Manifest path: `MANIFEST.json`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "moved": True,
        "candidate_id": cid,
        "classification": candidate["classification"],
        "source_path": str(source),
        "manifest": manifest_path.resolve().relative_to(workspace_root.resolve()).as_posix(),
        "readme": readme.resolve().relative_to(workspace_root.resolve()).as_posix(),
        "quarantine_path": dest.resolve().relative_to(workspace_root.resolve()).as_posix(),
    }


def write_home_reports(report: Dict[str, Any], workspace_root: Path) -> Dict[str, str]:
    canonical_root = get_canonical_root(workspace_root)
    json_path = canonical_root / REPORT_JSON
    md_path = canonical_root / REPORT_MD
    log_path = canonical_root / REPORT_LOG
    _save_json(json_path, report)
    _save_json(log_path, report)

    lines = [
        "# Home Hygiene Report",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Home root: `{report['home_root']}`",
        f"- Candidates: {report['summary']['candidate_count']}",
        f"- Junk: {report['summary']['junk_count']}",
        f"- Sensitive: {report['summary']['sensitive_count']}",
        f"- Skipped dot-dirs: {report['summary']['skipped_dotdirs']}",
        f"- JSON report: `{REPORT_JSON}`",
        f"- Log report: `{REPORT_LOG}`",
        "",
        "## Candidates",
        "",
    ]
    if not report["candidates"]:
        lines.append("- No obvious junk found.")
    else:
        for item in report["candidates"]:
            lines.append(
                f"- `{item['path']}` | class={item['classification']} | reason={item['reason']} | safe={item['safe_to_move']}"
            )

    if report.get("clean_result"):
        lines.extend(["", "## Clean Result", ""])
        result = report["clean_result"]
        lines.append(f"- Status: `{result['status']}`")
        lines.append(f"- Moved count: {result.get('moved_count', 0)}")
        lines.append(f"- Blocked reason: `{result.get('blocked_reason', '')}`")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": REPORT_JSON, "markdown": REPORT_MD, "log": REPORT_LOG}


def run_home_scan(workspace_root: Path, home_root: Path) -> Dict[str, Any]:
    report = scan_home(workspace_root, home_root)
    paths = write_home_reports(report, workspace_root)
    return {"status": "ok", "report": report, "paths": paths}


def run_home_clean_obvious(workspace_root: Path, home_root: Path, *, max_moves: int = 500) -> Dict[str, Any]:
    report = scan_home(workspace_root, home_root)
    candidates = list(report["candidates"])

    if any(Path(item["path"]).name.startswith(".") for item in candidates):
        result = {
            "status": "blocked",
            "blocked_reason": "dot_dir_candidate_detected",
            "moved_count": 0,
            "moved": [],
        }
        report["clean_result"] = result
        paths = write_home_reports(report, workspace_root)
        return {"status": "blocked", "report": report, "paths": paths, "result": result}

    if len(candidates) > max_moves:
        result = {
            "status": "blocked",
            "blocked_reason": "move_limit_exceeded",
            "moved_count": 0,
            "moved": [],
        }
        report["clean_result"] = result
        paths = write_home_reports(report, workspace_root)
        return {"status": "blocked", "report": report, "paths": paths, "result": result}

    moved: List[Dict[str, Any]] = []
    stamp = _stamp()
    for item in candidates:
        out = _move_to_quarantine(Path(report["canonical_root"]), item, stamp)
        if out.get("moved"):
            moved.append(out)

    moved.sort(key=lambda item: item["source_path"])
    result = {
        "status": "ok",
        "blocked_reason": "",
        "moved_count": len(moved),
        "moved": moved,
    }
    report["clean_result"] = result
    paths = write_home_reports(report, workspace_root)
    return {"status": "ok", "report": report, "paths": paths, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description="Home hygiene doctor")
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument("--root", default=str(Path.home()))
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--clean-obvious", action="store_true")
    parser.add_argument("--max-moves", type=int, default=500)
    args = parser.parse_args()

    if args.scan and args.clean_obvious:
        parser.error("Choose --scan or --clean-obvious, not both.")

    workspace_root = Path(args.workspace_root)
    home_root = Path(args.root).resolve()

    if args.clean_obvious:
        out = run_home_clean_obvious(workspace_root, home_root, max_moves=max(1, args.max_moves))
        print(
            json.dumps(
                {
                    "canonical_root": out["report"]["canonical_root"],
                    "home_root": out["report"]["home_root"],
                    "paths": out["paths"],
                    "result": out["result"],
                    "summary": out["report"]["summary"],
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
        )
        return 0 if out["status"] == "ok" else 3

    out = run_home_scan(workspace_root, home_root)
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "home_root": out["report"]["home_root"],
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

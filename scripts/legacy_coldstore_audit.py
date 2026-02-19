#!/usr/bin/env python3
"""Audit legacy cold storage in vault/_salvage and vault/_quarantine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

SALVAGE_ROOT = Path("vault/_salvage")
QUARANTINE_ROOT = Path("vault/_quarantine")

STATE_PATH = Path("state/legacy_coldstore_index.json")
REPORT_JSON = Path("docs/_inbox/legacy_coldstore_audit_latest.json")
REPORT_MD = Path("docs/_inbox/legacy_coldstore_audit_latest.md")
REPORT_LOG = Path("logs/legacy_coldstore_audit_latest.json")

TEXT_SAMPLE_BYTES = 96 * 1024
MANIFEST_NAMES = {"manifest.json", "conflicts.json", "readme.md"}

SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"api[ _-]*key",
        r"token",
        r"secret",
        r"password",
        r"bearer",
        r"private[ _-]*key",
        r"aws[_-]?secret",
        r"credential",
    ]
]

VALUE_KEYWORDS = [
    "skill",
    "plugin",
    "feature",
    "hook",
    "router",
    "doctor",
    "policy",
    "ingest",
    "memory",
    "outbox",
    "runtime",
    "openclaw",
    "heartbeat",
    "autonomy",
    "approval",
    "session",
]

RESERVED_INSTRUCTION_RE = re.compile(r"^(agents(\.override)?|claude(\.local)?)\.md$", re.IGNORECASE)

CODE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".sh",
    ".ps1",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".hpp",
    ".rb",
    ".php",
    ".sql",
}
DOC_EXTS = {".md", ".txt", ".pdf", ".html", ".rtf"}
DATA_EXTS = {".json", ".ndjson", ".csv"}
CONFIG_EXTS = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_sample(path: Path, max_bytes: int = TEXT_SAMPLE_BYTES) -> str:
    try:
        raw = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    return raw.decode("utf-8", errors="ignore")


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    out: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        current = Path(dirpath)
        for filename in sorted(filenames):
            path = current / filename
            if path.is_symlink():
                continue
            out.append(path)
    return out


def _kind_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in CODE_EXTS:
        return "code"
    if ext in DOC_EXTS:
        return "doc"
    if ext in DATA_EXTS:
        return "data"
    if ext in CONFIG_EXTS:
        return "config"
    return "unknown"


def _value_score(path: Path, sample: str) -> Tuple[int, List[str]]:
    haystack = f"{path.as_posix().lower()}\n{sample[:4000].lower()}"
    hits = [kw for kw in VALUE_KEYWORDS if kw in haystack]
    return len(hits), sorted(set(hits))


def _is_sensitive(path: Path, sample: str) -> Tuple[bool, List[str]]:
    haystack = f"{path.name}\n{sample[:6000]}"
    reasons: List[str] = []
    if path.name.lower().startswith(".env"):
        reasons.append("filename_env")
    for pattern in SECRET_PATTERNS:
        if pattern.search(haystack):
            reasons.append(f"pattern:{pattern.pattern}")
    return bool(reasons), sorted(set(reasons))


def _instruction_hazard(path: Path) -> bool:
    return bool(RESERVED_INSTRUCTION_RE.match(path.name))


def _feature_signature(path: Path, value_keywords: List[str], kind: str) -> str:
    seed = f"{path.name.lower()}|{kind}|{','.join(value_keywords)}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _classify(*, kind: str, sensitive: bool, instruction_hazard: bool, value_score: int) -> str:
    if sensitive:
        return "sensitive_blocked"
    if instruction_hazard:
        return "instruction_drift_blocked"
    if kind in {"doc", "data"} and value_score >= 1:
        return "doc_recoverable"
    if kind in {"code", "config"} and value_score >= 1:
        return "code_candidate_review"
    return "junk_low_value"


def _collect_manifest_summaries(root: Path) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    if not root.is_dir():
        return summaries
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        if path.name.lower() not in MANIFEST_NAMES:
            continue
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        payload: Dict[str, Any] = {}
        if path.suffix.lower() == ".json":
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                loaded = {}
            if isinstance(loaded, dict):
                payload = {k: loaded.get(k) for k in ("file_count", "origin_path", "created_at", "version")}
        summaries.append({"path": rel, "kind": path.name.lower(), "summary": payload})
    return summaries


def build_audit_report(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    salvage = canonical_root / SALVAGE_ROOT
    quarantine = canonical_root / QUARANTINE_ROOT
    items: List[Dict[str, Any]] = []

    scan_roots = [("salvage", salvage), ("quarantine", quarantine)]
    for store_kind, store_root in scan_roots:
        if not store_root.is_dir():
            continue
        for path in _iter_files(store_root):
            rel = path.resolve().relative_to(canonical_root.resolve()).as_posix()
            stat = path.stat()
            sample = _read_sample(path)
            kind = _kind_for(path)
            sensitive, sensitive_reasons = _is_sensitive(path, sample)
            instruction_hazard = _instruction_hazard(path)
            value_score, value_keywords = _value_score(path, sample)
            classification = _classify(
                kind=kind,
                sensitive=sensitive,
                instruction_hazard=instruction_hazard,
                value_score=value_score,
            )
            items.append(
                {
                    "candidate_id": hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12],
                    "path": rel,
                    "store_kind": store_kind,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "sha256": _sha256_file(path),
                    "extension": path.suffix.lower(),
                    "kind_heuristic": kind,
                    "sensitivity": sensitive,
                    "sensitivity_reasons": sensitive_reasons,
                    "instruction_hazard": instruction_hazard,
                    "value_score": value_score,
                    "value_keywords": value_keywords,
                    "feature_signature": _feature_signature(path, value_keywords, kind),
                    "bucket": classification,
                }
            )

    items.sort(key=lambda item: item["path"])

    bucket_counts: Dict[str, int] = {}
    for item in items:
        bucket = item["bucket"]
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "roots": {
            "salvage": SALVAGE_ROOT.as_posix(),
            "quarantine": QUARANTINE_ROOT.as_posix(),
            "salvage_exists": salvage.is_dir(),
            "quarantine_exists": quarantine.is_dir(),
        },
        "manifest_summaries": {
            "salvage": _collect_manifest_summaries(salvage),
            "quarantine": _collect_manifest_summaries(quarantine),
        },
        "items": items,
        "summary": {
            "items_count": len(items),
            "bucket_counts": dict(sorted(bucket_counts.items())),
            "sensitive_count": bucket_counts.get("sensitive_blocked", 0),
            "instruction_hazard_count": bucket_counts.get("instruction_drift_blocked", 0),
            "doc_recoverable_count": bucket_counts.get("doc_recoverable", 0),
            "code_candidate_review_count": bucket_counts.get("code_candidate_review", 0),
        },
        "version": 1,
    }
    return report


def _write_reports(root: str | Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / STATE_PATH, report)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines = [
        "# Legacy Coldstore Audit",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Salvage exists: `{report['roots']['salvage_exists']}`",
        f"- Quarantine exists: `{report['roots']['quarantine_exists']}`",
        f"- Items: {report['summary']['items_count']}",
        f"- Buckets: `{json.dumps(report['summary']['bucket_counts'], sort_keys=True, ensure_ascii=False)}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Top Recoverable Docs",
        "",
    ]
    recoverable = [item for item in report["items"] if item["bucket"] == "doc_recoverable"]
    if not recoverable:
        lines.append("- none")
    else:
        for item in recoverable[:40]:
            lines.append(f"- `{item['path']}` | score={item['value_score']} | ext={item['extension']}")

    lines.extend(["", "## Top Code Candidates (review only)", ""])
    code_candidates = [item for item in report["items"] if item["bucket"] == "code_candidate_review"]
    if not code_candidates:
        lines.append("- none")
    else:
        for item in code_candidates[:40]:
            lines.append(f"- `{item['path']}` | score={item['value_score']} | ext={item['extension']}")

    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "state": STATE_PATH.as_posix(),
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": REPORT_LOG.as_posix(),
    }


def run_scan(root: str | Path) -> Dict[str, Any]:
    report = build_audit_report(root)
    paths = _write_reports(root, report)
    return {"report": report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit legacy coldstore in salvage/quarantine.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    args = parser.parse_args()

    out = run_scan(args.root)
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "summary": out["report"]["summary"],
                "paths": out["paths"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

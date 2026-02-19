#!/usr/bin/env python3
"""Deterministic triage for raw corpus sources pending ingestion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root
from scripts.workspace_hygiene_policy import assert_policy_root, load_policy

TRIAGE_JSON = "docs/_inbox/corpus_triage_latest.json"
TRIAGE_MD = "docs/_inbox/corpus_triage_latest.md"
TRIAGE_LOG = "logs/corpus_triage_latest.json"

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "this",
    "that",
    "json",
    "md",
    "txt",
    "log",
    "file",
    "files",
    "source",
}

LANGUAGE_HINTS = {
    ".md": "markdown",
    ".txt": "text",
    ".json": "json",
    ".ndjson": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "config",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".csv": "csv",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_id(path: Path, suffix: str = "") -> str:
    raw = f"{path.resolve()}::{suffix}" if suffix else str(path.resolve())
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _iter_source_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return

    for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted([name for name in dirnames if not name.startswith(".")])
        for filename in sorted(filenames):
            fp = current / filename
            if fp.is_symlink():
                continue
            yield fp


def _extract_keywords(parts: Sequence[str]) -> List[str]:
    scores: Dict[str, int] = {}
    for part in parts:
        for token in TOKEN_RE.findall(part.lower()):
            if len(token) < 4 or token in STOPWORDS:
                continue
            scores[token] = scores.get(token, 0) + 1
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _count in ranked[:20]]


def _recommend_domain(keywords: Sequence[str], exts: Sequence[str], *, suspected_kind: str = "") -> Tuple[str, bool]:
    corpus = set(keywords)
    if suspected_kind == "chatgpt_export":
        if corpus.intersection({"prefer", "preference", "decision", "project", "timeline", "mateo", "personal"}):
            return "memory_human", True
        return "external_ingest", True
    if corpus.intersection({"openclaw", "otto", "repo", "root", "hygiene", "quarantine", "router", "ledger"}):
        return "openclaw_ops", True
    if corpus.intersection({"prompt", "template", "style", "protocol", "guide", "injection"}):
        return "ingest_patterns", True
    if any(ext in {".md", ".txt", ".json", ".ndjson"} for ext in exts):
        return "external_ingest", True
    return "external_ingest", False


def _approx_language(ext_counts: Dict[str, int]) -> str:
    if not ext_counts:
        return "unknown"
    top = sorted(ext_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return LANGUAGE_HINTS.get(top, "unknown")


def _scan_source(root: Path, inbox_root: Path, source_path: Path, *, source_id_suffix: str = "") -> Dict[str, Any]:
    file_entries: List[Dict[str, Any]] = []
    ext_counts: Dict[str, int] = {}
    total_bytes = 0
    keyword_parts: List[str] = [source_path.name]

    for fp in sorted(_iter_source_files(source_path), key=lambda p: p.as_posix()):
        rel_to_source = fp.resolve().relative_to(source_path.resolve()).as_posix() if source_path.is_dir() else fp.name
        rel_to_root = fp.resolve().relative_to(root.resolve()).as_posix()
        stat = fp.stat()
        sha = _sha256(fp)
        ext = fp.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        total_bytes += stat.st_size
        keyword_parts.append(fp.name)
        file_entries.append(
            {
                "mtime": stat.st_mtime,
                "rel_path": rel_to_source,
                "root_rel_path": rel_to_root,
                "sha256": sha,
                "size": stat.st_size,
            }
        )

    file_entries.sort(key=lambda item: item["rel_path"])
    ext_counts = dict(sorted(ext_counts.items(), key=lambda item: item[0]))
    keywords = _extract_keywords(keyword_parts)
    domain, high_signal = _recommend_domain(keywords, list(ext_counts.keys()))
    source_hash_input = "\n".join(f"{item['rel_path']}:{item['sha256']}" for item in file_entries)
    source_hash = hashlib.sha256(source_hash_input.encode("utf-8")).hexdigest()

    return {
        "source_id": _source_id(source_path, suffix=source_id_suffix),
        "source_name": source_path.name,
        "source_path": str(source_path.resolve()),
        "inbox_rel_path": source_path.resolve().relative_to(inbox_root.resolve()).as_posix(),
        "kind": "dir" if source_path.is_dir() else "file",
        "file_count": len(file_entries),
        "total_bytes": total_bytes,
        "extensions": ext_counts,
        "approx_language": _approx_language(ext_counts),
        "keywords": keywords,
        "high_signal": high_signal,
        "recommended_domain": domain,
        "source_hash": source_hash,
        "files": file_entries,
    }


def _scan_slice_units(root: Path, inbox_root: Path, source_dir: Path, hints: Dict[str, Any]) -> List[Dict[str, Any]]:
    slices_index = _load_json(source_dir / "normalized" / "slices_index.json")
    slices = slices_index.get("slices", []) if isinstance(slices_index.get("slices", []), list) else []

    units: List[Dict[str, Any]] = []
    for idx, item in enumerate(slices, start=1):
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path", "")).strip()
        if not rel:
            continue
        slice_path = source_dir / rel
        if not slice_path.is_file():
            continue

        stat = slice_path.stat()
        sha = _sha256(slice_path)
        slice_id = str(item.get("slice_id", f"slice_{idx:03d}"))
        domain_hint = str(hints.get("recommended_domain", "external_ingest"))

        source_hash = hashlib.sha256(f"{slice_id}:{sha}".encode("utf-8")).hexdigest()
        units.append(
            {
                "source_id": _source_id(slice_path, suffix=slice_id),
                "source_name": f"{source_dir.name}:{slice_id}",
                "source_path": str(slice_path.resolve()),
                "inbox_rel_path": slice_path.resolve().relative_to(inbox_root.resolve()).as_posix(),
                "kind": "slice",
                "file_count": 1,
                "total_bytes": stat.st_size,
                "extensions": {slice_path.suffix.lower(): 1},
                "approx_language": _approx_language({slice_path.suffix.lower(): 1}),
                "keywords": sorted(set(["chatgpt", "slice", slice_id.lower()])),
                "high_signal": True,
                "recommended_domain": domain_hint,
                "source_hash": source_hash,
                "files": [
                    {
                        "mtime": stat.st_mtime,
                        "rel_path": slice_path.name,
                        "root_rel_path": slice_path.resolve().relative_to(root.resolve()).as_posix(),
                        "sha256": sha,
                        "size": stat.st_size,
                    }
                ],
                "source_kind": "chatgpt_slice",
                "parent_source_rel": source_dir.resolve().relative_to(root.resolve()).as_posix(),
                "slice_id": slice_id,
            }
        )

    return sorted(units, key=lambda unit: unit["inbox_rel_path"])


def _load_event_meta(source_dir: Path) -> Dict[str, Any]:
    candidates = [
        source_dir / "source" / "EVENT_META.json",
        source_dir / "source" / "source" / "EVENT_META.json",
        source_dir / "EVENT_META.json",
    ]
    for candidate in candidates:
        payload = _load_json(candidate)
        if payload:
            return payload
    return {}


def _scan_intake_source(root: Path, inbox_root: Path, source_dir: Path) -> List[Dict[str, Any]]:
    hints = _load_json(source_dir / "HINTS.json")
    event_meta = _load_event_meta(source_dir)
    suspected_kind = str(hints.get("suspected_kind", "")).strip()
    meta_domain = str(event_meta.get("recommended_domain", "")).strip()
    hint_domain = str(hints.get("recommended_domain", "")).strip()
    preferred_domain = meta_domain or hint_domain

    if suspected_kind == "chatgpt_export" and (source_dir / "normalized" / "slices_index.json").is_file():
        if preferred_domain:
            hints = dict(hints)
            hints["recommended_domain"] = preferred_domain
        units = _scan_slice_units(root, inbox_root, source_dir, hints)
        if units:
            return units

    payload = source_dir / "source"
    scan_target = payload if payload.exists() else source_dir
    base = _scan_source(root, inbox_root, source_dir, source_id_suffix="intake")
    payload_scan = _scan_source(root, inbox_root, scan_target, source_id_suffix="payload")

    base["files"] = payload_scan["files"]
    base["file_count"] = payload_scan["file_count"]
    base["total_bytes"] = payload_scan["total_bytes"]
    base["extensions"] = payload_scan["extensions"]
    base["approx_language"] = payload_scan["approx_language"]
    base["keywords"] = sorted(set(payload_scan["keywords"] + TOKEN_RE.findall(suspected_kind.lower())))
    base["source_hash"] = payload_scan["source_hash"]

    if suspected_kind:
        domain, high_signal = _recommend_domain(base["keywords"], list(base["extensions"].keys()), suspected_kind=suspected_kind)
        base["recommended_domain"] = domain
        base["high_signal"] = high_signal
        base["source_kind"] = suspected_kind

    if preferred_domain:
        base["recommended_domain"] = preferred_domain
        base["high_signal"] = True
        base["recommended_domain_source"] = "event_meta" if meta_domain else "hints"

    return [base]


def build_triage_report(root: Path, *, inbox_rel: str = "vault/inbox_raw") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_policy(canonical_root, create_if_missing=True)
    assert_policy_root(canonical_root, policy)

    inbox_root = canonical_root / inbox_rel
    inbox_root.mkdir(parents=True, exist_ok=True)

    tooling = set(policy.get("tooling_dirs", []))
    suspicious_entries: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []

    sources_root = inbox_root / "sources"
    if sources_root.is_dir():
        for source_dir in sorted(sources_root.iterdir(), key=lambda p: p.name):
            if not source_dir.is_dir() or source_dir.name.startswith("."):
                continue
            sources.extend(_scan_intake_source(canonical_root, inbox_root, source_dir))

    for entry in sorted(inbox_root.iterdir(), key=lambda p: p.name):
        if entry.name in {"_processed", "_pending_drop", "sources"}:
            continue
        if entry.name.startswith(".") or entry.name in tooling:
            suspicious_entries.append(
                {
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "reason": "dot_or_tooling_entry_in_inbox",
                }
            )
            continue
        if not (entry.is_file() or entry.is_dir()):
            continue
        sources.append(_scan_source(canonical_root, inbox_root, entry))

    sources.sort(key=lambda item: item["inbox_rel_path"])
    suspicious_entries.sort(key=lambda item: item["name"])

    has_slice_units = any(str(item.get("source_kind", "")) == "chatgpt_slice" for item in sources)
    summary = {
        "pending_sources": len(sources),
        "pending_files": sum(item["file_count"] for item in sources),
        "pending_total_bytes": sum(item["total_bytes"] for item in sources),
        "high_signal_sources": sum(1 for item in sources if item["high_signal"]),
        "suspicious_entries": len(suspicious_entries),
        "slice_units": sum(1 for item in sources if str(item.get("source_kind", "")) == "chatgpt_slice"),
        "suggested_units_per_tick": 1 if has_slice_units else 2,
    }

    return {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "inbox_rel": inbox_rel,
        "sources": sources,
        "suspicious_entries": suspicious_entries,
        "summary": summary,
        "version": 2,
    }


def write_triage_reports(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    json_path = canonical_root / TRIAGE_JSON
    md_path = canonical_root / TRIAGE_MD
    log_path = canonical_root / TRIAGE_LOG

    _save_json(json_path, report)
    _save_json(log_path, report)

    lines: List[str] = [
        "# Corpus Triage Report",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Inbox rel: `{report['inbox_rel']}`",
        f"- Pending sources: {report['summary']['pending_sources']}",
        f"- Pending files: {report['summary']['pending_files']}",
        f"- Pending bytes: {report['summary']['pending_total_bytes']}",
        f"- High signal sources: {report['summary']['high_signal_sources']}",
        f"- Slice units: {report['summary'].get('slice_units', 0)}",
        f"- Suggested units/tick: {report['summary'].get('suggested_units_per_tick', 1)}",
        f"- Suspicious inbox entries: {report['summary']['suspicious_entries']}",
        f"- JSON report: `{TRIAGE_JSON}`",
        f"- Log report: `{TRIAGE_LOG}`",
        "",
        "## Sources",
        "",
    ]
    if not report["sources"]:
        lines.append("- No pending sources.")
    else:
        for item in report["sources"]:
            lines.append(
                f"- `{item['inbox_rel_path']}` | id={item['source_id']} | files={item['file_count']} | bytes={item['total_bytes']} "
                f"| domain={item['recommended_domain']} | high_signal={item['high_signal']}"
            )

    lines.extend(["", "## Suspicious Entries", ""])
    if not report["suspicious_entries"]:
        lines.append("- None.")
    else:
        for item in report["suspicious_entries"]:
            lines.append(f"- `{item['name']}` | reason={item['reason']} | path=`{item['path']}`")

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": TRIAGE_JSON, "markdown": TRIAGE_MD, "log": TRIAGE_LOG}


def run_triage(root: Path, *, inbox_rel: str = "vault/inbox_raw") -> Dict[str, Any]:
    report = build_triage_report(root, inbox_rel=inbox_rel)
    paths = write_triage_reports(root, report)
    return {"report": report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic triage for pending corpora.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--inbox", default="vault/inbox_raw")
    args = parser.parse_args()

    out = run_triage(Path(args.root), inbox_rel=args.inbox)
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

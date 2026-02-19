#!/usr/bin/env python3
"""Deterministic intake from vault/inbox_raw/_pending_drop into vault/inbox_raw/sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

PENDING_DROP = Path("vault/inbox_raw/_pending_drop")
INGESTED_ROOT = Path("vault/inbox_raw/_pending_drop/_ingested")
SOURCES_ROOT = Path("vault/inbox_raw/sources")
STATE_PATH = Path("state/intake_state.json")

REPORT_JSON = Path("docs/_inbox/dropbox_intake_report_latest.json")
REPORT_MD = Path("docs/_inbox/dropbox_intake_report_latest.md")
REPORT_LOG = Path("logs/dropbox_intake_latest.json")

DEFAULT_MAX_ENTRIES = 200
HASH_READ_LIMIT = 64 * 1024
ZIP_MAX_FILES = 5000
ZIP_MAX_TOTAL_BYTES = 500 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def _default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "last_run_utc": "",
        "last_status": "never",
        "ingested_count_total": 0,
        "duplicate_count_total": 0,
        "seen_fingerprints": {},
        "sources": {},
    }


def _load_state(root: Path) -> Dict[str, Any]:
    state = _default_state()
    state.update(_load_json(root / STATE_PATH))
    if not isinstance(state.get("seen_fingerprints"), dict):
        state["seen_fingerprints"] = {}
    if not isinstance(state.get("sources"), dict):
        state["sources"] = {}
    return state


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        current = Path(dirpath)
        for filename in sorted(filenames):
            fp = current / filename
            if fp.is_symlink():
                continue
            yield fp


def _sha256_file(path: Path, *, limit: int = 0) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        if limit > 0:
            digest.update(f.read(limit))
            return digest.hexdigest()
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guess_kind(path: Path, file_names: List[str]) -> str:
    lower_name = path.name.lower()
    if path.is_file() and path.suffix.lower() == ".zip":
        return "zip_archive"

    joined = "\n".join(name.lower() for name in file_names)
    if "conversations.json" in joined:
        return "chatgpt_export_candidate"
    if "chatgpt" in lower_name:
        return "chatgpt_export_candidate"
    if any(name.lower().endswith(".html") for name in file_names):
        return "html_bundle"
    if any(name.lower().endswith(".json") for name in file_names):
        return "json_export"
    if path.is_dir():
        return "mixed_dir"
    return "generic_corpus"


def _side_by_side_path(path: Path, marker: str) -> Path:
    if not path.exists():
        return path
    suffix = f"__from_{marker}"
    if path.suffix:
        candidate = Path(f"{path.with_suffix('')}{suffix}{path.suffix}")
    else:
        candidate = Path(f"{path}{suffix}")
    idx = 1
    final = candidate
    while final.exists():
        if path.suffix:
            final = Path(f"{path.with_suffix('')}{suffix}_{idx}{path.suffix}")
        else:
            final = Path(f"{path}{suffix}_{idx}")
        idx += 1
    return final


def _scan_entry(root: Path, pending_root: Path, entry: Path) -> Dict[str, Any]:
    files = sorted(_iter_files(entry), key=lambda p: p.as_posix())
    if not files:
        fingerprint = hashlib.sha256(f"empty:{entry.name}".encode("utf-8")).hexdigest()
        source_id = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:10]
        return {
            "entry_name": entry.name,
            "entry_path": str(entry.resolve()),
            "entry_rel": entry.resolve().relative_to(pending_root.resolve()).as_posix(),
            "kind": "empty_dir" if entry.is_dir() else "empty_file",
            "file_count": 0,
            "total_bytes": 0,
            "fingerprint": fingerprint,
            "source_id": source_id,
            "suspected_kind": "generic_corpus",
            "extensions": {},
            "sample_files": [],
        }

    ext_counts: Dict[str, int] = {}
    total_bytes = 0
    parts: List[str] = [entry.name]
    sample_files: List[str] = []

    for fp in files:
        stat = fp.stat()
        total_bytes += stat.st_size
        ext = fp.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        if entry.is_dir():
            rel = fp.resolve().relative_to(entry.resolve()).as_posix()
        else:
            rel = fp.name
        sample_files.append(rel)
        parts.append(
            f"{rel}|{stat.st_size}|{int(stat.st_mtime)}|{_sha256_file(fp, limit=HASH_READ_LIMIT)}"
        )

    if entry.is_file():
        fingerprint = hashlib.sha256(
            f"file|{entry.name}|{entry.stat().st_size}|{_sha256_file(entry)}".encode("utf-8")
        ).hexdigest()
    else:
        payload = "\n".join(sorted(parts))
        fingerprint = hashlib.sha256(f"dir|{entry.name}|{payload}".encode("utf-8")).hexdigest()

    source_id = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:10]
    suspected_kind = _guess_kind(entry, sample_files)

    return {
        "entry_name": entry.name,
        "entry_path": str(entry.resolve()),
        "entry_rel": entry.resolve().relative_to(pending_root.resolve()).as_posix(),
        "kind": "dir" if entry.is_dir() else "file",
        "file_count": len(files),
        "total_bytes": total_bytes,
        "fingerprint": fingerprint,
        "source_id": source_id,
        "suspected_kind": suspected_kind,
        "extensions": dict(sorted(ext_counts.items())),
        "sample_files": sorted(sample_files)[:20],
    }


def _safe_extract_zip(zip_path: Path, out_dir: Path) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    extracted_bytes = 0
    blocked: List[str] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()
        for info in infos:
            if extracted >= ZIP_MAX_FILES:
                blocked.append("max_files_limit")
                break
            if extracted_bytes + int(info.file_size) > ZIP_MAX_TOTAL_BYTES:
                blocked.append("max_total_bytes_limit")
                break
            name = info.filename
            if name.endswith("/"):
                continue
            candidate = out_dir / name
            resolved = candidate.resolve()
            try:
                resolved.relative_to(out_dir.resolve())
            except ValueError:
                blocked.append(f"path_traversal:{name}")
                continue
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, resolved.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted += 1
            extracted_bytes += int(info.file_size)

    return {
        "extracted_files": extracted,
        "extracted_bytes": extracted_bytes,
        "blocked": blocked,
    }


def _write_manifest(source_payload_root: Path, *, origin_path: str) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for fp in sorted(_iter_files(source_payload_root), key=lambda p: p.as_posix()):
        rel = fp.resolve().relative_to(source_payload_root.resolve()).as_posix()
        stat = fp.stat()
        entries.append(
            {
                "rel_path": rel,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "sha256": _sha256_file(fp),
            }
        )

    return {
        "created_at": _utc_now(),
        "origin_path": origin_path,
        "file_count": len(entries),
        "entries": entries,
        "version": 1,
    }


def _scan(root: Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    pending_root = canonical_root / PENDING_DROP
    pending_root.mkdir(parents=True, exist_ok=True)
    (canonical_root / SOURCES_ROOT).mkdir(parents=True, exist_ok=True)
    (canonical_root / INGESTED_ROOT).mkdir(parents=True, exist_ok=True)

    state = _load_state(canonical_root)
    seen = state.get("seen_fingerprints", {})

    candidates: List[Dict[str, Any]] = []
    for entry in sorted(pending_root.iterdir(), key=lambda p: p.name):
        if entry.name == "_ingested" or entry.name.startswith("."):
            continue
        if not (entry.is_file() or entry.is_dir()):
            continue

        item = _scan_entry(canonical_root, pending_root, entry)
        prior = seen.get(item["fingerprint"], {}) if isinstance(seen, dict) else {}
        duplicate = bool(prior)
        item["is_duplicate"] = duplicate
        item["seen_source_id"] = str(prior.get("source_id", "")) if duplicate else ""
        candidates.append(item)

    summary = {
        "pending_count": len(candidates),
        "new_count": sum(1 for c in candidates if not c["is_duplicate"]),
        "duplicate_count": sum(1 for c in candidates if c["is_duplicate"]),
        "pending_total_bytes": sum(int(c["total_bytes"]) for c in candidates),
        "pending_total_files": sum(int(c["file_count"]) for c in candidates),
    }

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "pending_root": PENDING_DROP.as_posix(),
        "sources_root": SOURCES_ROOT.as_posix(),
        "candidates": candidates,
        "summary": summary,
        "version": 1,
    }
    return {"report": report, "state": state}


def _write_reports(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines = [
        "# Dropbox Intake Report",
        "",
        f"- Canonical root: `{report['canonical_root']}`",
        f"- Pending count: {report['summary']['pending_count']}",
        f"- New count: {report['summary']['new_count']}",
        f"- Duplicate count: {report['summary']['duplicate_count']}",
        f"- Pending files: {report['summary']['pending_total_files']}",
        f"- Pending bytes: {report['summary']['pending_total_bytes']}",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Candidates",
        "",
    ]
    if not report["candidates"]:
        lines.append("- None.")
    else:
        for item in report["candidates"]:
            lines.append(
                f"- `{item['entry_rel']}` id={item['source_id']} dup={item['is_duplicate']} kind={item['suspected_kind']} files={item['file_count']} bytes={item['total_bytes']}"
            )

    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": REPORT_LOG.as_posix(),
        "state": STATE_PATH.as_posix(),
    }


def run_scan(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    out = _scan(canonical_root)
    paths = _write_reports(canonical_root, out["report"])
    return {"report": out["report"], "paths": paths}


def run_apply(root: str | Path, *, max_entries: int = DEFAULT_MAX_ENTRIES) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    scanned = _scan(canonical_root)
    report = scanned["report"]
    state = scanned["state"]

    sources_root = canonical_root / SOURCES_ROOT
    pending_root = canonical_root / PENDING_DROP
    ingested_root = canonical_root / INGESTED_ROOT
    sources_root.mkdir(parents=True, exist_ok=True)
    ingested_root.mkdir(parents=True, exist_ok=True)

    applied: List[Dict[str, Any]] = []
    max_take = max(1, int(max_entries))
    new_candidates = [item for item in report["candidates"] if not item["is_duplicate"]][:max_take]

    for item in new_candidates:
        source_id = item["source_id"]
        stamp = _stamp()
        source_dir = sources_root / f"{stamp}_{source_id}"
        source_dir = _side_by_side_path(source_dir, source_id)
        payload_dir = source_dir / "source"
        payload_dir.mkdir(parents=True, exist_ok=True)

        origin = Path(item["entry_path"])
        payload_target = payload_dir / origin.name
        if origin.is_file():
            shutil.copy2(origin, payload_target)
        else:
            shutil.copytree(origin, payload_target)

        zip_extract = {"extracted_files": 0, "extracted_bytes": 0, "blocked": []}
        if origin.is_file() and origin.suffix.lower() == ".zip":
            extract_dir = payload_dir / "extracted"
            zip_extract = _safe_extract_zip(payload_target, extract_dir)

        manifest = _write_manifest(payload_dir, origin_path=str(origin.resolve()))
        _save_json(source_dir / "MANIFEST.json", manifest)

        hints = {
            "source_id": source_id,
            "created_at": _utc_now(),
            "suspected_kind": item["suspected_kind"],
            "recommended_domain": "external_ingest",
            "suggested_router_mode": "slice_first" if "chatgpt" in item["suspected_kind"] else "default",
            "zip_extract": zip_extract,
            "version": 1,
        }
        _save_json(source_dir / "HINTS.json", hints)

        readme = source_dir / "README.md"
        readme.write_text(
            "\n".join(
                [
                    "# Intake Source",
                    "",
                    f"- Source ID: `{source_id}`",
                    f"- Origin: `{origin.resolve()}`",
                    f"- Suspected kind: `{item['suspected_kind']}`",
                    "- Next step: run chatgpt normalizer if suspected kind is chatgpt export.",
                    "- Then run triage/plan/apply via autonomy tick or heartbeat worker.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        ingested_dir = ingested_root / f"{stamp}_{source_id}" / "original"
        ingested_dir.mkdir(parents=True, exist_ok=True)
        move_target = _side_by_side_path(ingested_dir / origin.name, source_id)
        shutil.move(str(origin), str(move_target))

        state["seen_fingerprints"][item["fingerprint"]] = {
            "source_id": source_id,
            "ingested_at": _utc_now(),
            "source_rel": source_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
        }
        state["sources"][source_id] = {
            "source_rel": source_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "origin_rel": move_target.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "suspected_kind": item["suspected_kind"],
            "normalized": False,
            "ingested_at": _utc_now(),
        }

        applied.append(
            {
                "source_id": source_id,
                "source_rel": source_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
                "origin_rel": move_target.resolve().relative_to(canonical_root.resolve()).as_posix(),
                "manifest": (source_dir / "MANIFEST.json").resolve().relative_to(canonical_root.resolve()).as_posix(),
                "hints": (source_dir / "HINTS.json").resolve().relative_to(canonical_root.resolve()).as_posix(),
                "suspected_kind": item["suspected_kind"],
            }
        )

    state["ingested_count_total"] = int(state.get("ingested_count_total", 0)) + len(applied)
    state["duplicate_count_total"] = int(state.get("duplicate_count_total", 0)) + report["summary"]["duplicate_count"]
    state["last_run_utc"] = _utc_now()
    state["last_status"] = "success"
    _save_json(canonical_root / STATE_PATH, state)

    rescanned = _scan(canonical_root)
    final_report = rescanned["report"]
    final_report["apply"] = {
        "ingested_count": len(applied),
        "ingested": applied,
        "max_entries": max_take,
    }
    final_report["state_path"] = STATE_PATH.as_posix()

    paths = _write_reports(canonical_root, final_report)
    return {"report": final_report, "paths": paths}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dropbox intake from pending drop")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-entries", type=int, default=DEFAULT_MAX_ENTRIES)
    args = parser.parse_args()

    if args.scan and args.apply:
        parser.error("Use either --scan or --apply")

    if args.apply:
        out = run_apply(args.root, max_entries=max(1, args.max_entries))
    else:
        out = run_scan(args.root)

    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "summary": out["report"]["summary"],
                "paths": out["paths"],
                "apply": out["report"].get("apply", {}),
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

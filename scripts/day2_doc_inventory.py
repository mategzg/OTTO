#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

INVENTORY_PATH = Path("state/doc_inventory.json")
TOMBSTONES_PATH = Path("state/doc_tombstones.ndjson")
REPORT_JSON = Path("docs/_inbox/day2_inventory_latest.json")


SCAN_DIRS = ["brain", "memory", "repo_map", "docs"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as h:
        h.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _doc_id_from_key(key: str) -> str:
    return "doc-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def _scan_current(root: Path) -> Dict[str, Dict[str, Any]]:
    current: Dict[str, Dict[str, Any]] = {}
    for rel in SCAN_DIRS:
        base = root / rel
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            text = p.read_text(encoding="utf-8", errors="replace")
            rel_path = p.relative_to(root).as_posix()
            source_doc_key = _sha256(text)
            current[source_doc_key] = {
                "source_doc_key": source_doc_key,
                "path": rel_path,
                "content_hash": source_doc_key,
                "modified_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
            }
    return current


def run_day2_inventory_sync(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    prev = _load_json(canonical_root / INVENTORY_PATH)
    prev_docs = prev.get("docs", {}) if isinstance(prev.get("docs"), dict) else {}

    current = _scan_current(canonical_root)

    by_path_prev = {str(v.get("path", "")): k for k, v in prev_docs.items() if isinstance(v, dict)}

    created: List[str] = []
    modified: List[str] = []
    renamed: List[Dict[str, str]] = []
    deleted: List[str] = []
    doc_rot: List[str] = []

    next_docs: Dict[str, Dict[str, Any]] = {}

    for key, row in current.items():
        prev_row = prev_docs.get(key)
        if isinstance(prev_row, dict):
            if str(prev_row.get("path", "")) != str(row.get("path", "")):
                renamed.append({"from": str(prev_row.get("path", "")), "to": str(row.get("path", ""))})
            if str(prev_row.get("content_hash", "")) != str(row.get("content_hash", "")):
                modified.append(str(row.get("path", "")))
            doc_id = str(prev_row.get("doc_id", _doc_id_from_key(key)))
        else:
            # maybe rename by path match with changed key
            old_key = by_path_prev.get(str(row.get("path", "")))
            if old_key and old_key in prev_docs:
                old = prev_docs[old_key]
                doc_id = str(old.get("doc_id", _doc_id_from_key(old_key)))
                modified.append(str(row.get("path", "")))
            else:
                doc_id = _doc_id_from_key(key)
                created.append(str(row.get("path", "")))

        next_docs[key] = {
            "doc_id": doc_id,
            "source_doc_key": key,
            "path": str(row.get("path", "")),
            "modified_at": str(row.get("modified_at", "")),
            "content_hash": str(row.get("content_hash", "")),
            "deleted_at": "",
        }

        # doc rot detection
        try:
            text = (canonical_root / str(row.get("path", ""))).read_text(encoding="utf-8", errors="replace")
            non_empty = [ln for ln in text.splitlines() if ln.strip()]
            if len(non_empty) == 0:
                doc_rot.append(str(row.get("path", "")))
        except Exception:
            doc_rot.append(str(row.get("path", "")))

    for old_key, old_row in prev_docs.items():
        if old_key not in next_docs and isinstance(old_row, dict):
            p = str(old_row.get("path", ""))
            deleted.append(p)
            _append_ndjson(
                canonical_root / TOMBSTONES_PATH,
                {
                    "ts": _utc_now(),
                    "doc_id": str(old_row.get("doc_id", _doc_id_from_key(old_key))),
                    "source_doc_key": old_key,
                    "path": p,
                    "deleted_at": _utc_now(),
                },
            )

    inventory = {
        "version": 1,
        "updated_at": _utc_now(),
        "docs": next_docs,
        "summary": {
            "total_docs": len(next_docs),
            "created": len(created),
            "modified": len(modified),
            "renamed": len(renamed),
            "deleted": len(deleted),
            "doc_rot": len(doc_rot),
        },
    }
    _save_json(canonical_root / INVENTORY_PATH, inventory)

    report = {
        "created_at": _utc_now(),
        "status": "ok",
        "summary": inventory["summary"],
        "details": {
            "created": created,
            "modified": sorted(set(modified)),
            "renamed": renamed,
            "deleted": deleted,
            "doc_rot": sorted(set(doc_rot)),
        },
        "paths": {
            "inventory": INVENTORY_PATH.as_posix(),
            "tombstones": TOMBSTONES_PATH.as_posix(),
        },
        "version": 1,
    }
    _save_json(canonical_root / REPORT_JSON, report)
    return report

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

STATE_PATH = Path("state/sharepoint_sync_state.json")
SOURCE_FEED = Path("state/sharepoint_source_feed.json")
TARGET_ROOT = Path("brain/sg/source_docs")
MANIFEST_PATH = Path("state/sharepoint_manifest.json")
TOMBSTONES_PATH = Path("state/sharepoint_tombstones.ndjson")
REPORT_PATH = Path("docs/_inbox/sharepoint_sync_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _default_state() -> Dict[str, Any]:
    return {"version": 1, "last_delta_token": "", "items": {}, "last_run_at": ""}


def _to_markdown(item: Dict[str, Any]) -> str:
    audience = str(item.get("audience", "internal")).lower()
    if audience not in {"client", "staff", "internal"}:
        audience = "internal"
    title = str(item.get("title", item.get("id", "untitled")))
    body = str(item.get("content", "")).strip()
    return f"<!-- audience: {audience} -->\n# {title}\n\n{body}\n"


def _slug(doc_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in doc_id)
    return safe or "doc"


def run_sync(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = _default_state()
    state.update(_load_json(canonical_root / STATE_PATH))
    feed = _load_json(canonical_root / SOURCE_FEED)
    delta_token = str(feed.get("delta_token", "")).strip()
    changes = feed.get("changes", []) if isinstance(feed.get("changes", []), list) else []
    if not isinstance(state.get("items", {}), dict):
        state["items"] = {}

    target = canonical_root / TARGET_ROOT
    target.mkdir(parents=True, exist_ok=True)

    created = 0
    updated = 0
    deleted = 0
    renamed = 0

    for ch in changes:
        if not isinstance(ch, dict):
            continue
        doc_id = str(ch.get("id", "")).strip()
        if not doc_id:
            continue
        op = str(ch.get("op", "upsert")).strip().lower()
        prev = state["items"].get(doc_id, {}) if isinstance(state["items"].get(doc_id, {}), dict) else {}

        if op == "delete":
            old_rel = str(prev.get("path", "")).strip()
            if old_rel:
                p = canonical_root / old_rel
                if p.exists():
                    p.unlink()
            state["items"].pop(doc_id, None)
            _append_ndjson(canonical_root / TOMBSTONES_PATH, {"ts": _utc_now(), "id": doc_id, "op": "delete", "path": old_rel})
            deleted += 1
            continue

        filename = _slug(str(ch.get("name", doc_id))) + ".md"
        rel = (TARGET_ROOT / filename).as_posix()
        old_rel = str(prev.get("path", "")).strip()
        if old_rel and old_rel != rel:
            oldp = canonical_root / old_rel
            if oldp.exists():
                oldp.unlink()
            _append_ndjson(canonical_root / TOMBSTONES_PATH, {"ts": _utc_now(), "id": doc_id, "op": "rename", "from": old_rel, "to": rel})
            renamed += 1

        md = _to_markdown(ch)
        content_hash = hashlib.sha256(md.encode("utf-8")).hexdigest()
        if prev.get("content_hash") == content_hash and prev.get("path") == rel:
            continue

        (canonical_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (canonical_root / rel).write_text(md, encoding="utf-8")
        if prev:
            updated += 1
        else:
            created += 1
        state["items"][doc_id] = {
            "id": doc_id,
            "path": rel,
            "audience": str(ch.get("audience", "internal")).lower(),
            "etag": str(ch.get("etag", "")),
            "modified_at": str(ch.get("modified_at", "")),
            "content_hash": content_hash,
        }

    state["last_delta_token"] = delta_token or str(state.get("last_delta_token", ""))
    state["last_run_at"] = _utc_now()
    _save_json(canonical_root / STATE_PATH, state)
    _save_json(canonical_root / MANIFEST_PATH, {"version": 1, "items": sorted(state["items"].values(), key=lambda x: x["id"])})

    report = {
        "status": "ok",
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "renamed": renamed,
        "delta_token": state.get("last_delta_token", ""),
        "idempotent_rerun": created == 0 and updated == 0 and deleted == 0 and renamed == 0,
        "paths": {
            "state": STATE_PATH.as_posix(),
            "manifest": MANIFEST_PATH.as_posix(),
            "tombstones": TOMBSTONES_PATH.as_posix(),
        },
    }
    _save_json(canonical_root / REPORT_PATH, report)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="SharePoint incremental sync")
    p.add_argument("--root", default=".")
    args = p.parse_args()
    out = run_sync(args.root)
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

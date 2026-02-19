#!/usr/bin/env python3
"""Append-only outbox queue helpers with deterministic snapshots."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

OUTBOX_QUEUE_PATH = Path("docs/_inbox/outbox_queue.ndjson")
OUTBOX_LATEST_PATH = Path("docs/_inbox/outbox_latest.md")
OUTBOX_DELIVERED_DIR = Path("docs/_inbox/outbox_queue/_delivered")

PENDING_STATUSES = {"pending", "failed_retryable"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_ndjson(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _stable_id(channel: str, target: str, text: str, purpose: str, session_id: str, source_ref: str, created_at: str) -> str:
    raw = "|".join([channel, target, text, purpose, session_id, source_ref, created_at])
    return "obx_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_events(root: str | Path) -> List[Dict[str, Any]]:
    canonical_root = get_canonical_root(root)
    return _read_ndjson(canonical_root / OUTBOX_QUEUE_PATH)


def materialize_state(events: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    state: Dict[str, Dict[str, Any]] = {}
    for event in events:
        event_type = str(event.get("event_type", "enqueue")).strip().lower()
        item_id = str(event.get("id", "")).strip()
        if not item_id:
            continue
        if event_type == "enqueue":
            state[item_id] = dict(event)
            continue
        if event_type == "delivery":
            current = state.get(item_id)
            if not isinstance(current, dict):
                continue
            current["status"] = str(event.get("status", current.get("status", "pending")))
            current["delivered"] = bool(event.get("delivered", current.get("delivered", False)))
            current["attempt_count"] = int(event.get("attempt_count", current.get("attempt_count", 0)))
            current["last_attempt_at"] = str(event.get("last_attempt_at", current.get("last_attempt_at", "")))
            current["last_error"] = str(event.get("last_error", current.get("last_error", "")))
            current["updated_at"] = str(event.get("created_at", current.get("updated_at", current.get("created_at", ""))))
            if event.get("delivery_batch_id"):
                current["delivery_batch_id"] = str(event.get("delivery_batch_id", ""))
    return state


def materialized_items(root: str | Path) -> List[Dict[str, Any]]:
    state = materialize_state(load_events(root))
    rows = list(state.values())
    rows.sort(key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))))
    return rows


def summarize_items(items: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    total = 0
    pending = 0
    delivered = 0
    failed_retryable = 0
    failed_terminal = 0
    for row in items:
        total += 1
        status = str(row.get("status", "pending"))
        if status == "delivered":
            delivered += 1
        elif status == "failed_terminal":
            failed_terminal += 1
        elif status == "failed_retryable":
            failed_retryable += 1
            pending += 1
        else:
            pending += 1
    return {
        "total_count": total,
        "pending_count": pending,
        "delivered_count": delivered,
        "failed_retryable_count": failed_retryable,
        "failed_terminal_count": failed_terminal,
    }


def enqueue_message(
    root: str | Path,
    *,
    channel: str,
    target: str,
    text: str,
    purpose: str = "notify",
    session_id: str = "",
    source_ref: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    clean_text = text.strip()
    if not clean_text:
        raise RuntimeError("outbox text is required")

    created_at = utc_now()
    payload = {
        "event_type": "enqueue",
        "id": "",
        "created_at": created_at,
        "updated_at": created_at,
        "channel": str(channel).strip(),
        "target": str(target).strip(),
        "text": clean_text,
        "purpose": str(purpose).strip() or "notify",
        "session_id": str(session_id).strip(),
        "source_ref": str(source_ref).strip(),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "status": "pending",
        "delivered": False,
        "attempt_count": 0,
        "last_attempt_at": "",
        "last_error": "",
        "version": 1,
    }
    payload["id"] = _stable_id(
        payload["channel"],
        payload["target"],
        payload["text"],
        payload["purpose"],
        payload["session_id"],
        payload["source_ref"],
        payload["created_at"],
    )
    _append_ndjson(canonical_root / OUTBOX_QUEUE_PATH, payload)
    snapshot_path = write_latest_snapshot(canonical_root)
    return {
        "status": "queued",
        "queued": True,
        "item_id": payload["id"],
        "queue_path": OUTBOX_QUEUE_PATH.as_posix(),
        "snapshot_path": snapshot_path,
        "target": payload["target"],
    }


def append_delivery_event(
    root: str | Path,
    *,
    item_id: str,
    status: str,
    delivered: bool,
    attempt_count: int,
    last_error: str,
    delivery_batch_id: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    row = {
        "event_type": "delivery",
        "id": str(item_id).strip(),
        "created_at": utc_now(),
        "status": str(status).strip(),
        "delivered": bool(delivered),
        "attempt_count": int(attempt_count),
        "last_attempt_at": utc_now(),
        "last_error": str(last_error).strip(),
        "delivery_batch_id": str(delivery_batch_id).strip(),
        "source_ref": "scripts/outbox_delivery.py",
        "version": 1,
    }
    _append_ndjson(canonical_root / OUTBOX_QUEUE_PATH, row)
    return row


def archive_delivered_batch(
    root: str | Path,
    *,
    delivered_items: List[Dict[str, Any]],
    batch_id: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    if not delivered_items:
        return {"batch_id": "", "item_count": 0, "ndjson_path": "", "manifest_path": ""}

    clean_batch = batch_id.strip() or ("batch_" + hashlib.sha1((utc_now() + "|" + str(len(delivered_items))).encode("utf-8")).hexdigest()[:10])
    filename = f"{stamp()}_{clean_batch}.ndjson"
    ndjson_path = canonical_root / OUTBOX_DELIVERED_DIR / filename
    ndjson_path.parent.mkdir(parents=True, exist_ok=True)
    with ndjson_path.open("w", encoding="utf-8") as handle:
        for row in sorted(delivered_items, key=lambda item: (str(item.get("created_at", "")), str(item.get("id", "")))):
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")

    content = ndjson_path.read_bytes()
    manifest = {
        "batch_id": clean_batch,
        "created_at": utc_now(),
        "item_count": len(delivered_items),
        "ids": sorted(str(row.get("id", "")) for row in delivered_items),
        "ndjson_path": ndjson_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
        "version": 1,
    }
    manifest_path = ndjson_path.with_name(ndjson_path.stem + "_MANIFEST.json")
    _save_json(manifest_path, manifest)
    return {
        "batch_id": clean_batch,
        "item_count": len(delivered_items),
        "ndjson_path": manifest["ndjson_path"],
        "manifest_path": manifest_path.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }


def write_latest_snapshot(root: str | Path, *, max_items: int = 20) -> str:
    canonical_root = get_canonical_root(root)
    items = materialized_items(canonical_root)
    summary = summarize_items(items)
    pending_items = [row for row in items if str(row.get("status", "pending")) in PENDING_STATUSES]
    lines = [
        "# Outbox Latest",
        "",
        f"- Queue path: `{OUTBOX_QUEUE_PATH.as_posix()}`",
        f"- Total (materialized): {summary['total_count']}",
        f"- Pending: {summary['pending_count']}",
        f"- Delivered: {summary['delivered_count']}",
        f"- Failed retryable: {summary['failed_retryable_count']}",
        f"- Failed terminal: {summary['failed_terminal_count']}",
        "",
        "## Pending Items",
    ]
    if not pending_items:
        lines.append("")
        lines.append("- (none)")
    else:
        for item in pending_items[:max_items]:
            lines.extend(
                [
                    "",
                    f"- id: `{item.get('id', '')}`",
                    f"  channel: `{item.get('channel', '')}`",
                    f"  target: `{item.get('target', '') or '(missing)'}`",
                    f"  purpose: `{item.get('purpose', '')}`",
                    f"  attempt_count: {item.get('attempt_count', 0)}",
                    f"  last_error: `{item.get('last_error', '')}`",
                    f"  text_preview: `{str(item.get('text', ''))[:160]}`",
                ]
            )
    snapshot = canonical_root / OUTBOX_LATEST_PATH
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return OUTBOX_LATEST_PATH.as_posix()


def scan_queue(root: str | Path) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    items = materialized_items(root)
    return items, summarize_items(items)

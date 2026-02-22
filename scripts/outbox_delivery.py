#!/usr/bin/env python3
"""Deliver queued outbox messages in bounded deterministic batches."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.openclaw_cli import send_message
from scripts.outbox_queue import (
    OUTBOX_QUEUE_PATH,
    append_delivery_event,
    archive_delivered_batch,
    materialized_items,
    scan_queue,
    stamp,
    summarize_items,
    write_latest_snapshot,
)
from scripts.repo_root import get_canonical_root
from scripts.runtime_guardrails import load_guardrails

REPORT_JSON = Path("docs/_inbox/outbox_delivery_report_latest.json")
REPORT_MD = Path("docs/_inbox/outbox_delivery_report_latest.md")
LOG_JSON = Path("logs/outbox_delivery_latest.json")

PENDING_STATUSES = {"pending", "failed_retryable"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _select_pending(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pending = [row for row in items if str(row.get("status", "pending")) in PENDING_STATUSES and not bool(row.get("delivered", False))]
    pending.sort(key=lambda row: (str(row.get("created_at", "")), str(row.get("id", ""))))
    return pending


def _report_paths() -> Dict[str, str]:
    return {
        "json": REPORT_JSON.as_posix(),
        "markdown": REPORT_MD.as_posix(),
        "log": LOG_JSON.as_posix(),
        "queue": OUTBOX_QUEUE_PATH.as_posix(),
    }


def _should_block_send(item: Dict[str, Any], guardrails: Dict[str, Any]) -> bool:
    send_policy = guardrails.get("send_policy", {}) if isinstance(guardrails.get("send_policy", {}), dict) else {}
    source_ref = str(item.get("source_ref", "")).strip().lower()
    blocked_sources = [str(x).lower() for x in send_policy.get("block_sources", []) if str(x).strip()]
    if not any(source_ref.startswith(prefix) for prefix in blocked_sources):
        return False
    channel = str(item.get("channel", "")).strip().lower()
    protected_channels = [str(x).lower() for x in send_policy.get("protected_channels", []) if str(x).strip()]
    if protected_channels and not any(channel.startswith(pc) for pc in protected_channels):
        return False
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
    recipient_type = str(metadata.get("recipient_type", "client")).strip().lower() or "client"
    internal_types = {str(x).lower() for x in send_policy.get("internal_recipient_types", []) if str(x).strip()}
    return recipient_type not in internal_types


def _write_report(root: Path, report: Dict[str, Any]) -> None:
    _save_json(root / REPORT_JSON, report)
    _save_json(root / LOG_JSON, report)
    lines = [
        "# Outbox Delivery Report",
        "",
        f"- Status: `{report.get('status', '')}`",
        f"- Queue total: {report.get('summary', {}).get('queue_total', 0)}",
        f"- Queue pending: {report.get('summary', {}).get('queue_pending', 0)}",
        f"- Processed in run: {report.get('summary', {}).get('processed_in_run', 0)}",
        f"- Delivered in run: {report.get('summary', {}).get('delivered_in_run', 0)}",
        f"- Failed in run: {report.get('summary', {}).get('failed_in_run', 0)}",
        f"- Skipped missing target: {report.get('summary', {}).get('missing_target', 0)}",
        f"- Archive NDJSON: `{report.get('archive', {}).get('ndjson_path', '')}`",
        f"- Archive MANIFEST: `{report.get('archive', {}).get('manifest_path', '')}`",
        f"- Queue path: `{OUTBOX_QUEUE_PATH.as_posix()}`",
    ]
    (root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scan(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    items, summary = scan_queue(canonical_root)
    snapshot = write_latest_snapshot(canonical_root)
    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": "scanned",
        "summary": {
            "queue_total": summary["total_count"],
            "queue_pending": summary["pending_count"],
            "queue_delivered": summary["delivered_count"],
            "queue_failed_retryable": summary["failed_retryable_count"],
            "queue_failed_terminal": summary["failed_terminal_count"],
            "processed_in_run": 0,
            "delivered_in_run": 0,
            "failed_in_run": 0,
            "missing_target": 0,
            "blocked_by_policy": 0,
        },
        "snapshot_path": snapshot,
        "items_preview": [
            {
                "id": str(item.get("id", "")),
                "status": str(item.get("status", "")),
                "channel": str(item.get("channel", "")),
                "target": str(item.get("target", "")),
                "attempt_count": int(item.get("attempt_count", 0)),
            }
            for item in _select_pending(items)[:20]
        ],
        "archive": {"batch_id": "", "item_count": 0, "ndjson_path": "", "manifest_path": ""},
        "paths": _report_paths(),
        "version": 1,
    }
    _write_report(canonical_root, report)
    return {"report": report, "paths": _report_paths()}


def run_deliver(
    root: str | Path,
    *,
    max_items_per_run: int = 20,
    max_chars_per_item: int = 4000,
    max_runtime_seconds: int = 20,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    start = time.monotonic()
    items = materialized_items(canonical_root)
    pending = _select_pending(items)
    to_process = pending[: max(1, int(max_items_per_run))]
    processed = 0
    delivered_count = 0
    failed_count = 0
    missing_target = 0
    blocked_by_policy = 0
    failures: List[Dict[str, Any]] = []
    delivered_rows: List[Dict[str, Any]] = []
    batch_id = "deliver_" + stamp()
    guardrails = load_guardrails(canonical_root)

    for item in to_process:
        if (time.monotonic() - start) >= max(1, int(max_runtime_seconds)):
            break
        processed += 1
        item_id = str(item.get("id", ""))
        attempt_count = int(item.get("attempt_count", 0)) + 1
        target = str(item.get("target", "")).strip()
        text = str(item.get("text", ""))
        channel = str(item.get("channel", "telegram_owner"))

        if _should_block_send(item, guardrails):
            append_delivery_event(
                canonical_root,
                item_id=item_id,
                status="failed_terminal",
                delivered=False,
                attempt_count=attempt_count,
                last_error="blocked_send_policy",
            )
            blocked_by_policy += 1
            failed_count += 1
            failures.append({"id": item_id, "reason": "blocked_send_policy"})
            continue

        if not target:
            append_delivery_event(
                canonical_root,
                item_id=item_id,
                status="failed_retryable",
                delivered=False,
                attempt_count=attempt_count,
                last_error="missing_target",
            )
            missing_target += 1
            failed_count += 1
            failures.append({"id": item_id, "reason": "missing_target"})
            continue

        if len(text) > int(max_chars_per_item):
            append_delivery_event(
                canonical_root,
                item_id=item_id,
                status="failed_terminal",
                delivered=False,
                attempt_count=attempt_count,
                last_error=f"text_too_long:{len(text)}>{max_chars_per_item}",
            )
            failed_count += 1
            failures.append({"id": item_id, "reason": "text_too_long"})
            continue

        sent = send_message(channel, target, text)
        if sent.get("ok"):
            append_delivery_event(
                canonical_root,
                item_id=item_id,
                status="delivered",
                delivered=True,
                attempt_count=attempt_count,
                last_error="",
                delivery_batch_id=batch_id,
            )
            delivered_count += 1
            row_copy = dict(item)
            row_copy["status"] = "delivered"
            row_copy["delivered"] = True
            row_copy["attempt_count"] = attempt_count
            row_copy["updated_at"] = _utc_now()
            row_copy["delivery_batch_id"] = batch_id
            row_copy["delivery_info"] = {
                "cmd": sent.get("cmd", []),
                "returncode": sent.get("returncode", 0),
            }
            delivered_rows.append(row_copy)
            continue

        append_delivery_event(
            canonical_root,
            item_id=item_id,
            status="failed_retryable",
            delivered=False,
            attempt_count=attempt_count,
            last_error=str(sent.get("reason", "send_failed")),
        )
        failed_count += 1
        failures.append({"id": item_id, "reason": str(sent.get("reason", "send_failed"))})

    archive = archive_delivered_batch(canonical_root, delivered_items=delivered_rows, batch_id=batch_id)
    latest_items = materialized_items(canonical_root)
    summary = summarize_items(latest_items)
    snapshot = write_latest_snapshot(canonical_root)
    status = "success" if failed_count == 0 else ("partial" if delivered_count > 0 else "deferred")
    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": status,
        "summary": {
            "queue_total": summary["total_count"],
            "queue_pending": summary["pending_count"],
            "queue_delivered": summary["delivered_count"],
            "queue_failed_retryable": summary["failed_retryable_count"],
            "queue_failed_terminal": summary["failed_terminal_count"],
            "processed_in_run": processed,
            "delivered_in_run": delivered_count,
            "failed_in_run": failed_count,
            "missing_target": missing_target,
            "blocked_by_policy": blocked_by_policy,
        },
        "archive": archive,
        "snapshot_path": snapshot,
        "failures": failures[:50],
        "paths": _report_paths(),
        "version": 1,
    }
    _write_report(canonical_root, report)
    return {"report": report, "paths": _report_paths()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Outbox queue delivery")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--deliver", action="store_true")
    parser.add_argument("--max-items-per-run", type=int, default=20)
    parser.add_argument("--max-chars-per-item", type=int, default=4000)
    parser.add_argument("--max-runtime-seconds", type=int, default=20)
    args = parser.parse_args()

    if not args.scan and not args.deliver:
        parser.error("Use --scan or --deliver")

    if args.deliver:
        out = run_deliver(
            args.root,
            max_items_per_run=max(1, args.max_items_per_run),
            max_chars_per_item=max(100, args.max_chars_per_item),
            max_runtime_seconds=max(1, args.max_runtime_seconds),
        )
    else:
        out = run_scan(args.root)

    print(json.dumps(out["report"], indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if out["report"]["status"] in {"success", "scanned", "partial", "deferred"} else 3


if __name__ == "__main__":
    raise SystemExit(main())

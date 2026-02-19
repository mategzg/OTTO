#!/usr/bin/env python3
"""Workspace hook backlog: append-only capture + deterministic replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/hook_backlog_policy.json")
STATE_PATH = Path("state/hook_backlog_state.json")
BACKLOG_DIR = Path("state/hook_backlog")
EVENTS_PATH = BACKLOG_DIR / "events.ndjson"
ACKS_PATH = BACKLOG_DIR / "acks.ndjson"
PAYLOADS_DIR = BACKLOG_DIR / "payloads"
PROCESSED_DIR = BACKLOG_DIR / "_processed"

REPORT_JSON = Path("docs/_inbox/hook_backlog_report_latest.json")
REPORT_MD = Path("docs/_inbox/hook_backlog_report_latest.md")
REPORT_LOG = Path("logs/hook_backlog_latest.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "fail_open": True,
    "max_events_per_replay_tick": 25,
    "max_runtime_seconds": 20,
    "max_content_preview_chars": 64,
    "max_bytes_per_backlog_file": 10_000_000,
    "max_retry_attempts": 5,
    "archive_strategy": "batch_ndjson_manifest",
}

DEFAULT_STATE: Dict[str, Any] = {
    "version": 1,
    "last_run_utc": "",
    "last_status": "",
    "last_error": "",
    "consecutive_failures": 0,
    "stall_ticks": 0,
    "last_pending_count": 0,
    "last_replayed_count": 0,
    "last_processed_count": 0,
    "last_failed_count": 0,
}


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


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _read_ndjson(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        text = raw.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _load_policy(root: Path) -> Dict[str, Any]:
    path = root / POLICY_PATH
    policy = dict(DEFAULT_POLICY)
    policy.update(_load_json(path))
    if not path.is_file():
        _save_json(path, policy)
    return policy


def _load_state(root: Path) -> Dict[str, Any]:
    path = root / STATE_PATH
    state = dict(DEFAULT_STATE)
    state.update(_load_json(path))
    if not path.is_file():
        _save_json(path, state)
    return state


def _save_state(root: Path, state: Dict[str, Any]) -> None:
    _save_json(root / STATE_PATH, state)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _safe_preview(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1] + "…"


def _normalize_message_event(raw_event: Dict[str, Any]) -> Dict[str, Any]:
    event_type = str(raw_event.get("type", "")).strip().lower()
    action = str(raw_event.get("action", "")).strip().lower()
    if event_type not in {"message", "message:received", "message:sent"}:
        raise RuntimeError(f"unsupported_event_type:{event_type or '(empty)'}")
    if action not in {"received", "sent"}:
        if event_type == "message:received":
            action = "received"
        elif event_type == "message:sent":
            action = "sent"
        else:
            raise RuntimeError(f"unsupported_action:{action or '(empty)'}")

    context = raw_event.get("context", {})
    if not isinstance(context, dict):
        context = {}
    metadata = context.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    normalized = {
        "type": "message",
        "action": action,
        "timestamp": str(raw_event.get("timestamp", context.get("timestamp", ""))).strip() or _utc_now(),
        "sessionKey": str(raw_event.get("sessionKey", "")).strip(),
        "context": {
            "workspaceDir": str(context.get("workspaceDir", "")).strip(),
            "channelId": str(context.get("channelId", "")).strip(),
            "accountId": str(context.get("accountId", "")).strip(),
            "conversationId": str(context.get("conversationId", "")).strip(),
            "messageId": str(context.get("messageId", "")).strip(),
            "timestamp": str(context.get("timestamp", "")).strip(),
            "content": str(context.get("content", "")),
            "from": context.get("from", {}) if isinstance(context.get("from", {}), dict) else {},
            "to": context.get("to", {}) if isinstance(context.get("to", {}), dict) else {},
            "attachments": context.get("attachments", []) if isinstance(context.get("attachments", []), list) else [],
            "metadata": {
                "threadId": str(metadata.get("threadId", "")).strip(),
                "senderId": str(metadata.get("senderId", "")).strip(),
                "senderName": str(metadata.get("senderName", "")).strip(),
                "senderUsername": str(metadata.get("senderUsername", "")).strip(),
                "senderE164": str(metadata.get("senderE164", "")).strip(),
                "channelName": str(metadata.get("channelName", context.get("channelName", ""))).strip(),
            },
        },
    }
    return normalized


def _build_record(normalized_event: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    context = normalized_event["context"]
    metadata = context["metadata"]
    content = str(context.get("content", ""))
    payload_hash = _sha256_text(json.dumps(normalized_event, sort_keys=True, ensure_ascii=False))
    content_hash = _sha256_text(content)
    seed = "|".join(
        [
            normalized_event.get("action", ""),
            context.get("channelId", ""),
            context.get("accountId", ""),
            context.get("conversationId", ""),
            metadata.get("threadId", ""),
            context.get("messageId", ""),
            normalized_event.get("timestamp", ""),
            normalized_event.get("sessionKey", ""),
            content_hash,
        ]
    )
    event_id = "hkb_" + _sha1_text(seed)[:16]

    attachments = context.get("attachments", [])
    if not isinstance(attachments, list):
        attachments = []

    record = {
        "event_id": event_id,
        "created_at": _utc_now(),
        "source": "workspace_hook",
        "event_type": "message",
        "action": normalized_event.get("action", ""),
        "channel": context.get("channelId", ""),
        "account_id": context.get("accountId", ""),
        "conversation_id": context.get("conversationId", ""),
        "channel_id": context.get("channelId", ""),
        "thread_id": metadata.get("threadId", ""),
        "session_key": normalized_event.get("sessionKey", ""),
        "message_id": context.get("messageId", ""),
        "timestamp": normalized_event.get("timestamp", ""),
        "content_hash": content_hash,
        "content_preview": _safe_preview(content, int(policy.get("max_content_preview_chars", 64))),
        "attachments_meta": [
            {
                "name": str(item.get("name", ""))[:120],
                "path": str(item.get("path", ""))[:260],
                "url": str(item.get("url", ""))[:260],
            }
            for item in attachments
            if isinstance(item, dict)
        ],
        "workspace_dir_hint": context.get("workspaceDir", ""),
        "raw_context_hash": _sha256_text(json.dumps(context, sort_keys=True, ensure_ascii=False)),
        "payload_hash": payload_hash,
        "payload_relpath": f"{PAYLOADS_DIR.as_posix()}/{event_id}.json",
        "version": 1,
    }
    return record


def append_event(root: str | Path, raw_event: Dict[str, Any]) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    (canonical_root / BACKLOG_DIR).mkdir(parents=True, exist_ok=True)
    (canonical_root / PAYLOADS_DIR).mkdir(parents=True, exist_ok=True)

    normalized = _normalize_message_event(raw_event)
    record = _build_record(normalized, policy=policy)
    payload_path = canonical_root / record["payload_relpath"]

    max_bytes = int(policy.get("max_bytes_per_backlog_file", 10_000_000))
    current_file = canonical_root / EVENTS_PATH
    if current_file.is_file() and current_file.stat().st_size >= max(10_000, max_bytes):
        rotated = current_file.with_name(f"events_{_stamp()}.ndjson")
        current_file.rename(rotated)

    if not payload_path.is_file():
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(json.dumps(normalized, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    _append_ndjson(current_file, record)

    return {
        "status": "queued",
        "event_id": record["event_id"],
        "events_path": EVENTS_PATH.as_posix(),
        "payload_relpath": record["payload_relpath"],
        "canonical_root": str(canonical_root.resolve()),
    }


def _event_files(root: Path) -> List[Path]:
    if not (root / BACKLOG_DIR).is_dir():
        return []
    files = [
        path
        for path in sorted((root / BACKLOG_DIR).glob("events*.ndjson"), key=lambda p: p.name)
        if path.is_file()
    ]
    return files


def _load_event_records(root: Path) -> Dict[str, Dict[str, Any]]:
    events: Dict[str, Dict[str, Any]] = {}
    for path in _event_files(root):
        for row in _read_ndjson(path):
            event_id = str(row.get("event_id", "")).strip()
            if not event_id:
                continue
            if event_id not in events:
                events[event_id] = row
    return events


def _load_latest_acks(root: Path) -> Dict[str, Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}
    for row in _read_ndjson(root / ACKS_PATH):
        event_id = str(row.get("event_id", "")).strip()
        if not event_id:
            continue
        prev = latest.get(event_id)
        if not isinstance(prev, dict):
            latest[event_id] = row
            continue
        prev_attempt = int(prev.get("attempt", 0))
        now_attempt = int(row.get("attempt", 0))
        if now_attempt >= prev_attempt:
            latest[event_id] = row
    return latest


def _pending_events(root: Path, *, policy: Dict[str, Any]) -> List[Tuple[Dict[str, Any], int]]:
    events = _load_event_records(root)
    latest_acks = _load_latest_acks(root)
    max_retry = int(policy.get("max_retry_attempts", 5))
    pending: List[Tuple[Dict[str, Any], int]] = []
    for event_id, event in sorted(events.items(), key=lambda item: (str(item[1].get("created_at", "")), item[0])):
        ack = latest_acks.get(event_id, {})
        status = str(ack.get("status", "pending"))
        attempt = int(ack.get("attempt", 0))
        if status == "processed":
            continue
        if status == "failed_terminal":
            continue
        if status == "failed_retryable" and attempt >= max_retry:
            continue
        pending.append((event, attempt))
    return pending


def _archive_processed(root: Path, *, batch_id: str, processed_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not processed_rows:
        return {"batch_id": "", "item_count": 0, "ndjson_path": "", "manifest_path": ""}

    ts = _stamp()
    batch_dir = root / PROCESSED_DIR / f"{ts}_{batch_id}"
    payload_archive_dir = batch_dir / "payloads"
    payload_archive_dir.mkdir(parents=True, exist_ok=True)
    ndjson_path = batch_dir / "events.ndjson"
    manifest_path = batch_dir / "MANIFEST.json"

    with ndjson_path.open("w", encoding="utf-8") as handle:
        for row in sorted(processed_rows, key=lambda item: (str(item.get("created_at", "")), str(item.get("event_id", "")))):
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            payload_relpath = str(row.get("payload_relpath", ""))
            if payload_relpath:
                payload_src = root / payload_relpath
                if payload_src.is_file():
                    shutil.move(str(payload_src), str(payload_archive_dir / payload_src.name))

    manifest = {
        "batch_id": batch_id,
        "created_at": _utc_now(),
        "item_count": len(processed_rows),
        "ndjson_path": ndjson_path.resolve().relative_to(root.resolve()).as_posix(),
        "payload_dir": payload_archive_dir.resolve().relative_to(root.resolve()).as_posix(),
        "strategy": "batch_ndjson_manifest",
        "version": 1,
    }
    _save_json(manifest_path, manifest)
    return {
        "batch_id": batch_id,
        "item_count": len(processed_rows),
        "ndjson_path": manifest["ndjson_path"],
        "manifest_path": manifest_path.resolve().relative_to(root.resolve()).as_posix(),
    }


def _write_report(root: Path, report: Dict[str, Any]) -> None:
    _save_json(root / REPORT_JSON, report)
    _save_json(root / REPORT_LOG, report)
    lines = [
        "# Hook Backlog Report",
        "",
        f"- Status: `{report.get('status', '')}`",
        f"- Pending total: {report.get('summary', {}).get('pending_count', 0)}",
        f"- Replay selected: {report.get('summary', {}).get('selected_count', 0)}",
        f"- Replay processed: {report.get('summary', {}).get('processed_count', 0)}",
        f"- Replay failed: {report.get('summary', {}).get('failed_count', 0)}",
        f"- Consecutive failures: {report.get('state', {}).get('consecutive_failures', 0)}",
        f"- Stall ticks: {report.get('state', {}).get('stall_ticks', 0)}",
        f"- Archive manifest: `{report.get('archive', {}).get('manifest_path', '')}`",
        f"- Events path: `{EVENTS_PATH.as_posix()}`",
        f"- Acks path: `{ACKS_PATH.as_posix()}`",
    ]
    (root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scan(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    state = _load_state(canonical_root)
    pending = _pending_events(canonical_root, policy=policy)
    events_files = _event_files(canonical_root)
    total_event_rows = sum(len(_read_ndjson(path)) for path in events_files)
    ack_rows = _read_ndjson(canonical_root / ACKS_PATH)
    backlog_bytes = sum(path.stat().st_size for path in events_files if path.is_file())
    if (canonical_root / ACKS_PATH).is_file():
        backlog_bytes += (canonical_root / ACKS_PATH).stat().st_size
    payload_bytes = 0
    payload_count = 0
    for payload in sorted((canonical_root / PAYLOADS_DIR).glob("*.json")) if (canonical_root / PAYLOADS_DIR).is_dir() else []:
        payload_count += 1
        payload_bytes += payload.stat().st_size

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": "scanned",
        "summary": {
            "pending_count": len(pending),
            "event_rows_count": total_event_rows,
            "ack_rows_count": len(ack_rows),
            "payload_count": payload_count,
            "backlog_bytes": backlog_bytes + payload_bytes,
            "selected_count": 0,
            "processed_count": 0,
            "failed_count": 0,
        },
        "pending_preview": [
            {
                "event_id": item[0].get("event_id", ""),
                "action": item[0].get("action", ""),
                "channel": item[0].get("channel", ""),
                "message_id": item[0].get("message_id", ""),
                "created_at": item[0].get("created_at", ""),
                "attempt": item[1],
            }
            for item in pending[:30]
        ],
        "policy": policy,
        "state": state,
        "archive": {"batch_id": "", "item_count": 0, "ndjson_path": "", "manifest_path": ""},
        "paths": {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()},
        "version": 1,
    }
    _write_report(canonical_root, report)
    return {"report": report, "paths": report["paths"]}


def run_replay(root: str | Path, *, max_events: int | None = None, max_runtime_seconds: int | None = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    state = _load_state(canonical_root)

    selected_limit = max(1, int(max_events if max_events is not None else policy.get("max_events_per_replay_tick", 25)))
    max_seconds = max(1, int(max_runtime_seconds if max_runtime_seconds is not None else policy.get("max_runtime_seconds", 20)))
    pending_before = _pending_events(canonical_root, policy=policy)
    selected = pending_before[:selected_limit]
    start = time.monotonic()

    from scripts.channel_ingress_adapter import handle_runtime_event  # lazy import

    processed_rows: List[Dict[str, Any]] = []
    failed_rows: List[Dict[str, Any]] = []
    acks_written: List[Dict[str, Any]] = []

    for row, last_attempt in selected:
        if (time.monotonic() - start) >= max_seconds:
            break
        payload_relpath = str(row.get("payload_relpath", ""))
        payload_path = canonical_root / payload_relpath if payload_relpath else Path()
        attempt = int(last_attempt) + 1
        ack_status = "processed"
        error_summary = ""

        try:
            if not payload_relpath or not payload_path.is_file():
                raise RuntimeError("missing_payload")
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise RuntimeError("invalid_payload")
            out = handle_runtime_event(canonical_root, payload)
            if str(out.get("status", "")) != "success":
                raise RuntimeError(f"ingress_status:{out.get('status', '')}")
        except Exception as exc:  # pragma: no cover - exercised in unit tests with monkeypatch
            error_summary = str(exc)[:220]
            max_retry = int(policy.get("max_retry_attempts", 5))
            ack_status = "failed_terminal" if attempt >= max_retry else "failed_retryable"

        ack = {
            "event_id": str(row.get("event_id", "")),
            "acked_at": _utc_now(),
            "status": ack_status,
            "attempt": attempt,
            "error_code": ack_status,
            "error_summary": error_summary,
            "version": 1,
        }
        _append_ndjson(canonical_root / ACKS_PATH, ack)
        acks_written.append(ack)
        if ack_status == "processed":
            processed_rows.append(row)
        else:
            failed_rows.append({"event_id": row.get("event_id", ""), "status": ack_status, "error_summary": error_summary})

    archive = _archive_processed(
        canonical_root,
        batch_id="replay_" + _stamp(),
        processed_rows=processed_rows,
    )

    pending_after = _pending_events(canonical_root, policy=policy)
    processed_count = len(processed_rows)
    failed_count = len([item for item in acks_written if item.get("status") != "processed"])
    selected_count = len(acks_written)
    replay_seconds = round(time.monotonic() - start, 6)

    if failed_count > 0 and processed_count == 0 and selected_count > 0:
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
    else:
        state["consecutive_failures"] = 0

    if len(pending_after) >= len(pending_before) and selected_count == 0 and len(pending_before) > 0:
        state["stall_ticks"] = int(state.get("stall_ticks", 0)) + 1
    elif len(pending_after) < len(pending_before):
        state["stall_ticks"] = 0

    state["last_run_utc"] = _utc_now()
    state["last_status"] = "success" if failed_count == 0 else ("partial" if processed_count > 0 else "deferred")
    state["last_error"] = failed_rows[0]["error_summary"] if failed_rows else ""
    state["last_pending_count"] = len(pending_after)
    state["last_replayed_count"] = selected_count
    state["last_processed_count"] = processed_count
    state["last_failed_count"] = failed_count
    _save_state(canonical_root, state)

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": state["last_status"],
        "summary": {
            "pending_count": len(pending_after),
            "pending_before_count": len(pending_before),
            "selected_count": selected_count,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "replay_seconds": replay_seconds,
        },
        "failed_rows": failed_rows[:50],
        "archive": archive,
        "state": state,
        "policy": policy,
        "paths": {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()},
        "version": 1,
    }
    _write_report(canonical_root, report)
    return {"report": report, "paths": report["paths"]}


def run_append(root: str | Path, raw_event: Dict[str, Any]) -> Dict[str, Any]:
    out = append_event(root, raw_event)
    scan = run_scan(root)
    report = dict(scan["report"])
    report["status"] = "queued"
    report["append"] = out
    _write_report(get_canonical_root(root), report)
    return {"report": report, "paths": scan["paths"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Hook backlog capture/replay")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--event-json", default="")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--max-runtime-seconds", type=int, default=0)
    args = parser.parse_args()

    if not args.scan and not args.append and not args.replay:
        parser.error("Use one of --scan, --append, --replay")

    if args.append:
        if not args.event_json.strip():
            parser.error("--append requires --event-json")
        payload_raw = args.event_json.strip()
        maybe_path = Path(payload_raw)
        if maybe_path.is_file():
            payload = json.loads(maybe_path.read_text(encoding="utf-8"))
        else:
            payload = json.loads(payload_raw)
        if not isinstance(payload, dict):
            raise SystemExit("event-json must decode to object")
        out = run_append(args.root, payload)
    elif args.replay:
        out = run_replay(
            args.root,
            max_events=args.max_events if args.max_events > 0 else None,
            max_runtime_seconds=args.max_runtime_seconds if args.max_runtime_seconds > 0 else None,
        )
    else:
        out = run_scan(args.root)

    print(json.dumps(out["report"], indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if out["report"]["status"] in {"scanned", "queued", "success", "partial", "deferred"} else 3


if __name__ == "__main__":
    raise SystemExit(main())

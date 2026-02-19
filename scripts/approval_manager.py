#!/usr/bin/env python3
"""Natural-language approval manager for SG promotions and worker pairing."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root
from scripts.sg_promotion import approve_promotion
from scripts.telegram_delivery import send_message
from scripts.outbox_queue import enqueue_message

APPROVALS_QUEUE = Path("docs/_inbox/approvals_queue.ndjson")
APPROVALS_REPORT_JSON = Path("docs/_inbox/approvals_report_latest.json")
APPROVALS_REPORT_MD = Path("docs/_inbox/approvals_report_latest.md")
APPROVALS_LOG = Path("logs/approvals_latest.json")
APPROVALS_STATE = Path("state/approvals_state.json")
WORKER_PAIRINGS = Path("state/sg_worker_pairings.json")
SG_QUEUE = Path("docs/_inbox/sg_promotion_queue.ndjson")

POSITIVE_RE = re.compile(r"\b(si|sí|ok|dale|va|aprueba|aprobado|autoriza|go|yes)\b", re.IGNORECASE)
NEGATIVE_RE = re.compile(r"\b(no|rechaza|deny|deniega|cancel)\b", re.IGNORECASE)
LAST_RE = re.compile(r"\b(ultima|última|latest|last|la ultima|la última)\b", re.IGNORECASE)
ALL_RE = re.compile(r"\b(ambas|todos|todas|all)\b", re.IGNORECASE)
NONE_RE = re.compile(r"\b(ninguna|none)\b", re.IGNORECASE)
WORKER_RE = re.compile(r"\b(worker|trabajador|pair|pairing)\b", re.IGNORECASE)
PROMOTION_RE = re.compile(r"\b(promocion|promoción|promotion|sg)\b", re.IGNORECASE)


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


def _write_ndjson(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _make_approval_id(request_type: str, dedupe_key: str, source_ref: str) -> str:
    seed = f"{request_type}|{dedupe_key}|{source_ref}"
    return "apr_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _load_state(root: Path) -> Dict[str, Any]:
    state = {
        "version": 1,
        "last_owner_reply_at": "",
        "last_owner_reply_text": "",
        "last_resolution": "",
        "last_queue_sync_at": "",
    }
    state.update(_load_json(root / APPROVALS_STATE))
    if not (root / APPROVALS_STATE).is_file():
        _save_json(root / APPROVALS_STATE, state)
    return state


def _write_state(root: Path, state: Dict[str, Any]) -> None:
    _save_json(root / APPROVALS_STATE, state)


def _load_pairings(root: Path) -> Dict[str, Any]:
    payload = _load_json(root / WORKER_PAIRINGS)
    if not payload:
        payload = {"version": 1, "updated_at": "", "workers": {}}
    if not isinstance(payload.get("workers"), dict):
        payload["workers"] = {}
    return payload


def _save_pairings(root: Path, payload: Dict[str, Any]) -> None:
    payload["updated_at"] = _utc_now()
    _save_json(root / WORKER_PAIRINGS, payload)


def _worker_key(channel: str, account_id: str, peer_id: str) -> str:
    return "|".join(
        [
            str(channel).strip().lower() or "_",
            str(account_id).strip().lower() or "_",
            str(peer_id).strip().lower() or "_",
        ]
    )


def is_worker_paired(root: str | Path, *, channel: str, account_id: str, peer_id: str) -> bool:
    canonical_root = get_canonical_root(root)
    pairings = _load_pairings(canonical_root)
    key = _worker_key(channel, account_id, peer_id)
    item = pairings["workers"].get(key, {})
    return bool(isinstance(item, dict) and item.get("status") == "paired")


def _log_report(root: Path, report: Dict[str, Any]) -> None:
    _save_json(root / APPROVALS_REPORT_JSON, report)
    _save_json(root / APPROVALS_LOG, report)
    lines = [
        "# Approvals Report",
        "",
        f"- Status: `{report.get('status', '')}`",
        f"- Pending: {report.get('summary', {}).get('pending_count', 0)}",
        f"- Approved now: {report.get('summary', {}).get('approved_now', 0)}",
        f"- Rejected now: {report.get('summary', {}).get('rejected_now', 0)}",
        f"- Clarification needed: {report.get('summary', {}).get('clarification_needed', 0)}",
        f"- Delivery channel: `{report.get('delivery', {}).get('channel', 'telegram_owner')}`",
        f"- Delivery sent: `{report.get('delivery', {}).get('sent', False)}`",
        f"- Delivery reason: `{report.get('delivery', {}).get('reason', '')}`",
        f"- Queue path: `{APPROVALS_QUEUE.as_posix()}`",
        f"- JSON report: `{APPROVALS_REPORT_JSON.as_posix()}`",
    ]
    (root / APPROVALS_REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (root / APPROVALS_REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pending_requests(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pending = [row for row in rows if str(row.get("status", "")) == "pending"]
    pending.sort(key=lambda row: str(row.get("created_at", "")))
    return pending


def _notify_owner(root: Path, message: str, *, dry_run: bool = False) -> Dict[str, Any]:
    out = send_message(root, message, dry_run=dry_run)
    return {
        "channel": "telegram_owner",
        "dry_run": bool(dry_run),
        "sent": bool(out.get("sent", False) or out.get("queued", False)),
        "queued": bool(out.get("queued", False)),
        "reason": str(out.get("reason", "")),
        "fallback_outbox": str(out.get("fallback_outbox", "")),
        "queue_item_id": str(out.get("queue_item_id", "")),
    }


def enqueue_request(
    root: str | Path,
    *,
    request_type: str,
    subject: str,
    payload: Dict[str, Any],
    source_ref: str,
    dedupe_key: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    queue_path = canonical_root / APPROVALS_QUEUE
    rows = _read_ndjson(queue_path)

    payload_safe = dict(payload)
    dedupe_value = dedupe_key.strip() or str(payload_safe.get("promotion_id", "")).strip() or subject.strip()
    dedupe_value = dedupe_value or f"{request_type}:{subject}"

    for row in rows:
        if str(row.get("status")) != "pending":
            continue
        if str(row.get("dedupe_key", "")) == dedupe_value and str(row.get("request_type", "")) == request_type:
            return {
                "status": "duplicate_pending",
                "approval_id": str(row.get("approval_id", "")),
                "queue_path": APPROVALS_QUEUE.as_posix(),
                "canonical_root": str(canonical_root.resolve()),
                "notification": {
                    "channel": "telegram_owner",
                    "sent": False,
                    "reason": "duplicate_pending_no_notify",
                    "fallback_outbox": "",
                },
            }

    now = _utc_now()
    approval_id = _make_approval_id(request_type, dedupe_value, source_ref)
    row = {
        "approval_id": approval_id,
        "request_type": request_type,
        "subject": subject[:220],
        "source_ref": source_ref[:320],
        "payload": payload_safe,
        "dedupe_key": dedupe_value,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "resolved_by": "",
        "resolved_at": "",
        "resolution_note": "",
        "version": 1,
    }
    rows.append(row)
    rows.sort(key=lambda item: str(item.get("created_at", "")))
    _write_ndjson(queue_path, rows)
    message = (
        "Nueva aprobacion pendiente para owner\n"
        f"tipo={request_type}\n"
        f"subject={subject[:120]}\n"
        f"approval_id={approval_id}\n"
        "Responde en Telegram con 'si/ok/dale' para aprobar, 'no' para rechazar."
    )
    notification = _notify_owner(canonical_root, message)
    return {
        "status": "enqueued",
        "approval_id": approval_id,
        "queue_path": APPROVALS_QUEUE.as_posix(),
        "canonical_root": str(canonical_root.resolve()),
        "notification": notification,
    }


def _sync_from_sg_queue(root: Path) -> Dict[str, Any]:
    if not (root / SG_QUEUE).is_file():
        return {"enqueued": 0, "skipped": 0}
    enqueued = 0
    skipped = 0
    for row in _read_ndjson(root / SG_QUEUE):
        if str(row.get("status", "")) != "pending":
            continue
        if not bool(row.get("needs_approval", False)):
            continue
        promotion_id = str(row.get("promotion_id", "")).strip()
        if not promotion_id:
            continue
        out = enqueue_request(
            root,
            request_type="sg_promotion",
            subject=f"SG promotion {promotion_id}",
            payload={
                "promotion_id": promotion_id,
                "sensitivity": str(row.get("sensitivity", "medium")),
                "text": str(row.get("text", ""))[:320],
            },
            source_ref=str(row.get("source_ref", "docs/_inbox/sg_promotion_queue.ndjson")),
            dedupe_key=f"sg_promotion:{promotion_id}",
        )
        if out["status"] == "enqueued":
            enqueued += 1
        else:
            skipped += 1
    return {"enqueued": enqueued, "skipped": skipped}


def _mark_row(row: Dict[str, Any], *, status: str, note: str, resolved_by: str) -> None:
    row["status"] = status
    row["resolution_note"] = note[:400]
    row["resolved_by"] = resolved_by[:120]
    row["resolved_at"] = _utc_now()
    row["updated_at"] = row["resolved_at"]


def _resolve_rows_for_reply(rows: List[Dict[str, Any]], reply_text: str) -> Dict[str, Any]:
    pending = _pending_requests(rows)
    if not pending:
        return {"status": "no_pending", "targets": []}

    lower = reply_text.strip().lower()
    if NONE_RE.search(lower):
        return {"status": "resolved", "action": "reject_all", "targets": [row["approval_id"] for row in pending]}

    if ALL_RE.search(lower):
        return {"status": "resolved", "action": "approve_all", "targets": [row["approval_id"] for row in pending]}

    positive = bool(POSITIVE_RE.search(lower))
    negative = bool(NEGATIVE_RE.search(lower))
    if not positive and not negative:
        return {"status": "ignored", "targets": []}

    candidates = list(pending)
    if WORKER_RE.search(lower):
        candidates = [row for row in pending if str(row.get("request_type", "")) == "worker_pairing"]
    elif PROMOTION_RE.search(lower):
        candidates = [row for row in pending if str(row.get("request_type", "")) == "sg_promotion"]

    if not candidates:
        return {"status": "ignored", "targets": []}

    if len(candidates) == 1:
        action = "approve" if positive and not negative else "reject"
        return {"status": "resolved", "action": action, "targets": [candidates[0]["approval_id"]]}

    only_one_type = len({str(row.get("request_type", "")) for row in candidates}) == 1
    if LAST_RE.search(lower) or only_one_type:
        target = sorted(candidates, key=lambda row: str(row.get("created_at", "")))[-1]
        action = "approve" if positive and not negative else "reject"
        return {"status": "resolved", "action": action, "targets": [target["approval_id"]]}

    return {
        "status": "needs_clarification",
        "targets": [],
        "options": [
            {
                "approval_id": str(row.get("approval_id", "")),
                "request_type": str(row.get("request_type", "")),
                "subject": str(row.get("subject", "")),
                "created_at": str(row.get("created_at", "")),
            }
            for row in candidates[-3:]
        ],
    }


def _apply_request(root: Path, row: Dict[str, Any]) -> Dict[str, Any]:
    req_type = str(row.get("request_type", ""))
    payload = row.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    if req_type == "sg_promotion":
        promotion_id = str(payload.get("promotion_id", "")).strip()
        if not promotion_id:
            return {"status": "error", "reason": "missing_promotion_id"}
        out = approve_promotion(root, promotion_id)
        return {"status": "ok", "action": "sg_promotion_approved", "promotion_id": promotion_id, "result": out}

    if req_type == "worker_pairing":
        pairings = _load_pairings(root)
        worker_key = str(payload.get("worker_key", "")).strip()
        if not worker_key:
            worker_key = _worker_key(
                str(payload.get("channel", "whatsapp")),
                str(payload.get("account_id", "_")),
                str(payload.get("peer_id", "_")),
            )
        pairings["workers"][worker_key] = {
            "status": "paired",
            "paired_at": _utc_now(),
            "channel": str(payload.get("channel", "")),
            "account_id": str(payload.get("account_id", "")),
            "peer_id": str(payload.get("peer_id", "")),
            "display_name": str(payload.get("display_name", "")),
            "source_ref": str(row.get("source_ref", "")),
            "approved_from": str(row.get("approval_id", "")),
        }
        _save_pairings(root, pairings)
        peer_target = str(payload.get("peer_id", "")).strip()
        if peer_target:
            enqueue_message(
                root,
                channel="whatsapp",
                target=peer_target,
                text="Aprobado, ya tienes acceso a backoffice.",
                purpose="worker_pairing_result",
                session_id="",
                source_ref=f"approval:{row.get('approval_id', '')}",
                metadata={"result": "approved", "request_type": "worker_pairing"},
            )
        return {"status": "ok", "action": "worker_paired", "worker_key": worker_key}

    return {"status": "error", "reason": f"unsupported_request_type:{req_type}"}


def process_owner_reply(root: str | Path, *, reply_text: str) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = _load_state(canonical_root)
    rows = _read_ndjson(canonical_root / APPROVALS_QUEUE)

    resolution = _resolve_rows_for_reply(rows, reply_text)
    approved_now = 0
    rejected_now = 0
    errors: List[str] = []
    actions: List[Dict[str, Any]] = []

    by_id = {str(row.get("approval_id", "")): row for row in rows}
    targets = [item for item in resolution.get("targets", []) if item in by_id]

    if resolution.get("status") == "resolved":
        action = str(resolution.get("action", "approve"))
        for approval_id in targets:
            row = by_id[approval_id]
            if action.startswith("approve"):
                op = _apply_request(canonical_root, row)
                if op.get("status") == "ok":
                    _mark_row(row, status="approved", note=op.get("action", "approved"), resolved_by="owner_nl")
                    approved_now += 1
                else:
                    errors.append(str(op.get("reason", "unknown_error")))
                    _mark_row(row, status="error", note=str(op), resolved_by="owner_nl")
                actions.append({"approval_id": approval_id, "op": op})
            else:
                _mark_row(row, status="rejected", note="owner_rejected_nl", resolved_by="owner_nl")
                rejected_now += 1
                payload = row.get("payload", {})
                if isinstance(payload, dict) and str(row.get("request_type", "")) == "worker_pairing":
                    peer_target = str(payload.get("peer_id", "")).strip()
                    if peer_target:
                        enqueue_message(
                            canonical_root,
                            channel="whatsapp",
                            target=peer_target,
                            text="Solicitud rechazada por owner. Mantengo acceso restringido.",
                            purpose="worker_pairing_result",
                            session_id="",
                            source_ref=f"approval:{approval_id}",
                            metadata={"result": "rejected", "request_type": "worker_pairing"},
                        )
                actions.append({"approval_id": approval_id, "op": {"status": "ok", "action": "rejected"}})

    _write_ndjson(canonical_root / APPROVALS_QUEUE, rows)

    state["last_owner_reply_at"] = _utc_now()
    state["last_owner_reply_text"] = reply_text[:500]
    state["last_resolution"] = str(resolution.get("status", ""))
    _write_state(canonical_root, state)

    pending = _pending_requests(rows)
    notification: Dict[str, Any] = {
        "channel": "telegram_owner",
        "sent": False,
        "reason": "not_sent",
        "fallback_outbox": "",
    }
    if resolution.get("status") == "needs_clarification":
        options = resolution.get("options", [])
        lines = ["Tengo multiples aprobaciones pendientes y la respuesta fue ambigua."]
        for item in options[:3]:
            lines.append(f"- {item.get('request_type','')}: {item.get('subject','')}")
        lines.append("Responde: 'solo la ultima', 'ambas' o 'ninguna'.")
        notification = _notify_owner(canonical_root, "\n".join(lines))
    elif resolution.get("status") == "resolved":
        notification = _notify_owner(
            canonical_root,
            "Aprobaciones procesadas.\n"
            f"approved={approved_now}\n"
            f"rejected={rejected_now}\n"
            f"pending={len(pending)}",
        )

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": str(resolution.get("status", "unknown")),
        "resolution": resolution,
        "actions": actions,
        "errors": errors,
        "delivery": notification,
        "summary": {
            "total_count": len(rows),
            "pending_count": len(pending),
            "approved_now": approved_now,
            "rejected_now": rejected_now,
            "clarification_needed": 1 if resolution.get("status") == "needs_clarification" else 0,
        },
        "paths": {
            "queue": APPROVALS_QUEUE.as_posix(),
            "state": APPROVALS_STATE.as_posix(),
            "worker_pairings": WORKER_PAIRINGS.as_posix(),
        },
        "version": 1,
    }
    _log_report(canonical_root, report)
    return report


def process_pending_approvals(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = _load_state(canonical_root)
    sync = _sync_from_sg_queue(canonical_root)
    state["last_queue_sync_at"] = _utc_now()
    _write_state(canonical_root, state)

    rows = _read_ndjson(canonical_root / APPROVALS_QUEUE)
    pending = _pending_requests(rows)
    notification: Dict[str, Any] = {
        "channel": "telegram_owner",
        "sent": False,
        "reason": "no_new_items",
        "fallback_outbox": "",
    }
    if int(sync.get("enqueued", 0)) > 0:
        notification = _notify_owner(
            canonical_root,
            "Nuevas aprobaciones en cola.\n"
            f"new={sync.get('enqueued', 0)}\n"
            f"pending_total={len(pending)}",
        )
    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": "ok",
        "sync": sync,
        "delivery": notification,
        "summary": {
            "total_count": len(rows),
            "pending_count": len(pending),
            "pending_sg_promotion": sum(1 for row in pending if str(row.get("request_type", "")) == "sg_promotion"),
            "pending_worker_pairing": sum(1 for row in pending if str(row.get("request_type", "")) == "worker_pairing"),
        },
        "paths": {
            "queue": APPROVALS_QUEUE.as_posix(),
            "state": APPROVALS_STATE.as_posix(),
            "worker_pairings": WORKER_PAIRINGS.as_posix(),
        },
        "version": 1,
    }
    _log_report(canonical_root, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Approval queue manager")
    parser.add_argument("--root", default=".")
    parser.add_argument("--sync", action="store_true", help="sync SG queue into approvals queue")
    parser.add_argument("--reply", default="", help="owner natural-language reply")
    parser.add_argument("--enqueue-type", default="")
    parser.add_argument("--subject", default="")
    parser.add_argument("--payload-json", default="")
    parser.add_argument("--source-ref", default="runtime")
    parser.add_argument("--dedupe-key", default="")
    args = parser.parse_args()

    if args.enqueue_type:
        if not args.subject:
            parser.error("--subject is required with --enqueue-type")
        payload: Dict[str, Any] = {}
        if args.payload_json:
            candidate = Path(args.payload_json)
            if candidate.is_file():
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            else:
                payload = json.loads(args.payload_json)
            if not isinstance(payload, dict):
                parser.error("--payload-json must be an object")
        out = enqueue_request(
            args.root,
            request_type=args.enqueue_type,
            subject=args.subject,
            payload=payload,
            source_ref=args.source_ref,
            dedupe_key=args.dedupe_key,
        )
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.reply:
        out = process_owner_reply(args.root, reply_text=args.reply)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        if out["status"] == "needs_clarification":
            return 4
        return 0

    if args.sync:
        out = process_pending_approvals(args.root)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    parser.error("Use --sync or --reply or --enqueue-type.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

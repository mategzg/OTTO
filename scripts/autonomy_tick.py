#!/usr/bin/env python3
"""Autonomy tick: repo reality doctor + autonomous ingest execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.brain_ingest_router import run_apply, run_plan
from scripts.corpus_triage import run_triage
from scripts.instruction_surface_doctor import run_surface_fix, run_surface_scan
from scripts.approval_manager import process_pending_approvals
from scripts.memory_compact import run_memory_compact
from scripts.memory_index_build import run_memory_index_build
from scripts.outbox_queue import materialized_items, summarize_items
from scripts.repo_reality_doctor import run_doctor, write_reports
from scripts.repo_root import get_canonical_root, get_pinned_root
from scripts.safety_switch import autopause_switch, get_safety_status, load_policy as load_safety_policy
from scripts.session_memory_manager import run_session_maintenance
from scripts.sg_promotion import process_promotions

AUTONOMY_STATE_PATH = Path("state/autonomy_state.json")
AUTONOMY_LOCK_PATH = Path("state/autonomy_tick.lock")
AUTONOMY_JSON = Path("docs/_inbox/autonomy_latest.json")
AUTONOMY_MD = Path("docs/_inbox/autonomy_latest.md")
AUTONOMY_LOG = Path("logs/autonomy_latest.json")
PENDING_DROP = Path("vault/inbox_raw/_pending_drop")


def send_telegram_message(text: str, *, token: Optional[str] = None, chat_id: Optional[str] = None) -> Dict[str, Any]:
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        return {"ok": False, "sent": False, "reason": "missing_config"}

    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "sent": False, "reason": str(exc)}

    return {"ok": True, "sent": True, "response": body[:200]}


def _emit_message(root: Path, text: str, send_func: Callable[[str], Dict[str, Any]]) -> Dict[str, Any]:
    sent = send_func(text)
    if sent.get("sent"):
        return sent

    outbox = root / "docs" / "_inbox" / "outbox_latest.md"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text(text + "\n", encoding="utf-8")
    return {
        "ok": False,
        "sent": False,
        "reason": sent.get("reason", "missing_config"),
        "outbox": outbox.resolve().relative_to(root.resolve()).as_posix(),
    }


def _parse_iso(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_state(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_autonomy_reports(root: Path, report: Dict[str, Any]) -> Dict[str, str]:
    _save_json(root / AUTONOMY_JSON, report)
    _save_json(root / AUTONOMY_LOG, report)

    lines: List[str] = [
        "# Autonomy Latest",
        "",
        f"- Root: `{report['canonical_root']}`",
        f"- Status: `{report['status']}`",
        f"- Pending sources(total): {report['pending_total_sources']}",
        f"- Pending selected this tick: {report['pending_selected_sources']}",
        f"- Last plan id: `{report.get('plan_id', '')}`",
        f"- Last apply status: `{report.get('apply_status', '')}`",
        f"- Processed ids: `{', '.join(report.get('processed_ids', []))}`",
        f"- Heartbeat pending_drop: {report.get('heartbeat_context', {}).get('pending_drop_count', 0)}",
        f"- Heartbeat sources_pending: {report.get('heartbeat_context', {}).get('sources_pending_count', 0)}",
        f"- Heartbeat slices_processed: {report.get('heartbeat_context', {}).get('slices_processed_count', 0)}",
        f"- Runtime compactions: {report.get('runtime_context', {}).get('compactions_done', 0)}",
        f"- Runtime distills: {report.get('runtime_context', {}).get('distills_done', 0)}",
        f"- Runtime approvals pending: {report.get('runtime_context', {}).get('approvals_pending', 0)}",
        f"- Runtime approvals delivery sent: `{report.get('runtime_context', {}).get('approvals_delivery_sent', False)}`",
        f"- Runtime approvals delivery reason: `{report.get('runtime_context', {}).get('approvals_delivery_reason', '')}`",
        f"- SG pending approval: {report.get('runtime_context', {}).get('sg_pending_approval', 0)}",
        f"- Outbox queued: {report.get('runtime_context', {}).get('outbox_queued', 0)}",
        f"- Outbox delivered(last run): {report.get('runtime_context', {}).get('outbox_delivered', 0)}",
        f"- Outbox failed(last run): {report.get('runtime_context', {}).get('outbox_failed', 0)}",
        f"- Memory pending: {report.get('memory', {}).get('pending_inbox', 0)}",
        f"- Memory compact status: `{report.get('memory', {}).get('compact_status', '')}`",
        f"- Memory index status: `{report.get('memory', {}).get('index_status', '')}`",
        f"- Surface drift count: {report.get('surface_scan', {}).get('summary', {}).get('drift_count', 0)}",
        f"- Surface drift grave count: {report.get('surface_scan', {}).get('summary', {}).get('drift_grave_count', 0)}",
        f"- Consecutive failures: {report['state']['consecutive_failures']}",
        f"- Paused until: `{report['state'].get('paused_until_utc', '')}`",
        f"- JSON report: `{AUTONOMY_JSON.as_posix()}`",
        f"- Log report: `{AUTONOMY_LOG.as_posix()}`",
    ]
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for item in report["errors"]:
            lines.append(f"- {item}")

    md_path = root / AUTONOMY_MD
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "json": AUTONOMY_JSON.as_posix(),
        "markdown": AUTONOMY_MD.as_posix(),
        "log": AUTONOMY_LOG.as_posix(),
    }


def _acquire_lock(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        return False
    lock_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    return True


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except OSError:
        pass


def _fingerprint(report: Dict[str, Any], *, root_drift: bool, pinned_root: str) -> str:
    pending = [
        {
            "candidate_id": item["candidate_id"],
            "candidate_type": item["candidate_type"],
            "path": item["path"],
        }
        for item in sorted(report["candidates"], key=lambda c: c["candidate_id"])
        if item.get("disposition") == "pending"
    ]
    payload = {"pending": pending, "pinned_root": pinned_root, "root_drift": root_drift}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_repo_reality_doctor_job(
    *,
    root: Optional[str | Path] = None,
    now: Optional[datetime] = None,
    interval_hours: int = 24,
    dedupe_hours: int = 24,
    send_func: Callable[[str], Dict[str, Any]] = send_telegram_message,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state_path = canonical_root / "state" / "autonomy_repo_doctor_state.json"
    log_path = canonical_root / "logs" / "repo_reality_autonomy_latest.json"

    now_dt = now or _utc_now()
    state = _load_state(state_path)

    last_run = _parse_iso(state.get("last_run_utc", ""))
    if last_run and (now_dt - last_run) < timedelta(hours=interval_hours):
        result = {
            "canonical_root": str(canonical_root),
            "status": "skipped_interval",
            "last_run_utc": state.get("last_run_utc", ""),
        }
        _save_json(log_path, result)
        return result

    report = run_doctor(canonical_root, apply=False)
    paths = write_reports(report, canonical_root)

    pinned = get_pinned_root(canonical_root, require_clean=True)
    pinned_str = str(pinned) if pinned else ""
    root_drift = not pinned_str or Path(report["canonical_root"]).resolve() != Path(pinned_str).resolve()

    fingerprint = _fingerprint(report, root_drift=root_drift, pinned_root=pinned_str)
    last_fingerprint = state.get("last_fingerprint", "")
    last_alert = _parse_iso(state.get("last_alert_utc", ""))

    has_pending = report["summary"].get("pending_count", 0) > 0
    should_alert = False
    if has_pending or root_drift:
        if fingerprint != last_fingerprint:
            should_alert = True
        elif last_alert is None or (now_dt - last_alert) >= timedelta(hours=dedupe_hours):
            should_alert = True

    telegram = {"ok": False, "sent": False, "reason": "not_needed"}
    if should_alert:
        msg = (
            "Repo reality drift detected\n"
            f"root={canonical_root}\n"
            f"pinned_root={pinned_str or '(not set)'}\n"
            f"root_drift={root_drift}\n"
            f"pending_candidates={report['summary']['pending_count']}\n"
            f"pathlike={report['summary'].get('pathlike_count', 0)}\n"
            f"backups={report['summary'].get('backup_count', 0)}\n"
            f"report={paths['markdown']}\n"
            "suggested=/repo roots"
        )
        telegram = send_func(msg)

    state.update(
        {
            "last_alert_utc": now_dt.isoformat() if should_alert else state.get("last_alert_utc", ""),
            "last_fingerprint": fingerprint,
            "last_run_utc": now_dt.isoformat(),
            "last_root_drift": root_drift,
            "last_pinned_root": pinned_str,
            "last_pending_count": report["summary"].get("pending_count", 0),
        }
    )
    _save_state(state_path, state)

    result = {
        "canonical_root": str(canonical_root),
        "paths": paths,
        "root_drift": root_drift,
        "status": "ok",
        "summary": report["summary"],
        "telegram": telegram,
    }
    _save_json(log_path, result)
    return result


def _default_autonomy_state() -> Dict[str, Any]:
    return {
        "auto_paused_reason": "",
        "backoff_until_utc": "",
        "consecutive_failures": 0,
        "last_error": "",
        "last_plan_id": "",
        "last_processed_ids": [],
        "last_run_utc": "",
        "last_status": "never",
        "paused_until_utc": "",
    }


def _merged_autonomy_state(root: Path) -> Dict[str, Any]:
    state = _default_autonomy_state()
    state.update(_load_state(root / AUTONOMY_STATE_PATH))
    return state


def _memory_pending_count(root: Path) -> int:
    inbox = root / "docs" / "_inbox" / "memory_inbox.ndjson"
    if not inbox.is_file():
        return 0
    count = 0
    for line in inbox.read_text(encoding="utf-8").splitlines():
        if line.strip():
            count += 1
    return count


def _pending_drop_count(root: Path) -> int:
    pending = root / PENDING_DROP
    if not pending.is_dir():
        return 0
    count = 0
    for item in pending.iterdir():
        if item.name == "_ingested" or item.name.startswith("."):
            continue
        if item.is_file() or item.is_dir():
            count += 1
    return count


def _outbox_metrics(root: Path) -> Dict[str, int]:
    items = materialized_items(root)
    summary = summarize_items(items)
    delivered_last = 0
    failed_last = 0
    outbox_log = root / "logs" / "outbox_delivery_latest.json"
    if outbox_log.is_file():
        try:
            payload = json.loads(outbox_log.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            run_summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
            delivered_last = int(run_summary.get("delivered_in_run", 0))
            failed_last = int(run_summary.get("failed_in_run", 0))
    return {
        "outbox_queued": int(summary.get("pending_count", 0)),
        "outbox_delivered": delivered_last,
        "outbox_failed": failed_last,
    }


def autonomy_status(root: Optional[str | Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = _merged_autonomy_state(canonical_root)
    triage = run_triage(canonical_root)["report"]
    surface_summary: Dict[str, Any] = {}
    surface_json = canonical_root / "docs" / "_inbox" / "instruction_surface_report_latest.json"
    if surface_json.is_file():
        try:
            payload = json.loads(surface_json.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                surface_summary = dict(payload.get("summary", {}))
        except json.JSONDecodeError:
            surface_summary = {}
    return {
        "canonical_root": str(canonical_root.resolve()),
        "pending_sources": triage["summary"]["pending_sources"],
        "pending_files": triage["summary"]["pending_files"],
        "pending_drop_count": _pending_drop_count(canonical_root),
        "last_plan_id": state.get("last_plan_id", ""),
        "last_processed_ids": list(state.get("last_processed_ids", [])),
        "last_status": state.get("last_status", "never"),
        "last_run_utc": state.get("last_run_utc", ""),
        "paused_until_utc": state.get("paused_until_utc", ""),
        "backoff_until_utc": state.get("backoff_until_utc", ""),
        "consecutive_failures": int(state.get("consecutive_failures", 0)),
        "surface_summary": surface_summary,
        "latest_report_json": AUTONOMY_JSON.as_posix() if (canonical_root / AUTONOMY_JSON).is_file() else "",
        "latest_report_md": AUTONOMY_MD.as_posix() if (canonical_root / AUTONOMY_MD).is_file() else "",
        "memory_inbox_pending": _memory_pending_count(canonical_root),
    }


def autonomy_last(root: Optional[str | Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    return {
        "canonical_root": str(canonical_root.resolve()),
        "autonomy_json": AUTONOMY_JSON.as_posix() if (canonical_root / AUTONOMY_JSON).is_file() else "",
        "autonomy_md": AUTONOMY_MD.as_posix() if (canonical_root / AUTONOMY_MD).is_file() else "",
        "triage_json": "docs/_inbox/corpus_triage_latest.json" if (canonical_root / "docs/_inbox/corpus_triage_latest.json").is_file() else "",
        "plan_json": "docs/_inbox/corpus_assimilation_plan_latest.json" if (canonical_root / "docs/_inbox/corpus_assimilation_plan_latest.json").is_file() else "",
        "apply_json": "docs/_inbox/corpus_assimilation_report_latest.json" if (canonical_root / "docs/_inbox/corpus_assimilation_report_latest.json").is_file() else "",
    }


def autonomy_pause(root: Optional[str | Path] = None, *, hours: int = 12) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state_path = canonical_root / AUTONOMY_STATE_PATH
    state = _merged_autonomy_state(canonical_root)
    until = _utc_now() + timedelta(hours=max(1, hours))
    state["paused_until_utc"] = until.isoformat()
    state["last_status"] = "paused"
    _save_state(state_path, state)
    return {"ok": True, "paused_until_utc": state["paused_until_utc"], "canonical_root": str(canonical_root.resolve())}


def autonomy_resume(root: Optional[str | Path] = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state_path = canonical_root / AUTONOMY_STATE_PATH
    state = _merged_autonomy_state(canonical_root)
    state["paused_until_utc"] = ""
    state["backoff_until_utc"] = ""
    state["auto_paused_reason"] = ""
    state["last_status"] = "resumed"
    _save_state(state_path, state)
    return {"ok": True, "canonical_root": str(canonical_root.resolve())}


def run_autonomy_tick(
    *,
    root: Optional[str | Path] = None,
    force: bool = False,
    max_sources_per_tick: int = 2,
    max_apply_ops_per_tick: int = 250,
    max_runtime_seconds: int = 180,
    send_func: Callable[[str], Dict[str, Any]] = send_telegram_message,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state_path = canonical_root / AUTONOMY_STATE_PATH
    lock_path = canonical_root / AUTONOMY_LOCK_PATH
    now = _utc_now()

    if not _acquire_lock(lock_path):
        result = {
            "canonical_root": str(canonical_root.resolve()),
            "status": "locked",
            "pending_total_sources": 0,
            "pending_selected_sources": 0,
            "errors": ["autonomy_tick lock exists"],
            "state": _merged_autonomy_state(canonical_root),
            "version": 1,
        }
        result["paths"] = _write_autonomy_reports(canonical_root, result)
        return result

    try:
        state = _merged_autonomy_state(canonical_root)
        safety_status = get_safety_status(canonical_root, auto_expire=True)
        safety_policy = load_safety_policy(canonical_root)
        if safety_status.get("paused", False):
            report = {
                "apply_status": "",
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "errors": [],
                "heartbeat_context": {
                    "pending_drop_count": _pending_drop_count(canonical_root),
                    "sources_pending_count": 0,
                    "ingested_count": 0,
                    "normalized_count": 0,
                    "slices_processed_count": 0,
                },
                "runtime_context": {
                    "sessions_scanned": 0,
                    "compactions_done": 0,
                    "distills_done": 0,
                    "approvals_pending": 0,
                    "approvals_delivery_sent": False,
                    "approvals_delivery_reason": "",
                    "sg_promoted_auto": 0,
                    "sg_pending_approval": 0,
                    "outbox_queued": _outbox_metrics(canonical_root)["outbox_queued"],
                    "outbox_delivered": _outbox_metrics(canonical_root)["outbox_delivered"],
                    "outbox_failed": _outbox_metrics(canonical_root)["outbox_failed"],
                    "safety_paused": True,
                    "safety_reason": str(safety_status.get("reason", "")),
                },
                "pending_selected_sources": 0,
                "pending_total_sources": 0,
                "plan_id": "",
                "processed_ids": [],
                "surface_scan": {},
                "status": "paused_safety",
                "state": state,
                "version": 1,
            }
            report["paths"] = _write_autonomy_reports(canonical_root, report)
            return report

        paused_until = _parse_iso(state.get("paused_until_utc", ""))
        backoff_until = _parse_iso(state.get("backoff_until_utc", ""))

        if not force and paused_until and now < paused_until:
            report = {
                "apply_status": "",
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "errors": [],
                "heartbeat_context": {
                    "pending_drop_count": _pending_drop_count(canonical_root),
                    "sources_pending_count": 0,
                    "ingested_count": 0,
                    "normalized_count": 0,
                    "slices_processed_count": 0,
                },
                "runtime_context": {
                    "sessions_scanned": 0,
                    "compactions_done": 0,
                    "distills_done": 0,
                    "approvals_pending": 0,
                    "approvals_delivery_sent": False,
                    "approvals_delivery_reason": "",
                    "sg_promoted_auto": 0,
                    "sg_pending_approval": 0,
                    "outbox_queued": _outbox_metrics(canonical_root)["outbox_queued"],
                    "outbox_delivered": _outbox_metrics(canonical_root)["outbox_delivered"],
                    "outbox_failed": _outbox_metrics(canonical_root)["outbox_failed"],
                },
                "pending_selected_sources": 0,
                "pending_total_sources": 0,
                "plan_id": "",
                "processed_ids": [],
                "surface_scan": {},
                "status": "paused",
                "state": state,
                "version": 1,
            }
            report["paths"] = _write_autonomy_reports(canonical_root, report)
            return report

        if not force and backoff_until and now < backoff_until:
            report = {
                "apply_status": "",
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "errors": [],
                "heartbeat_context": {
                    "pending_drop_count": _pending_drop_count(canonical_root),
                    "sources_pending_count": 0,
                    "ingested_count": 0,
                    "normalized_count": 0,
                    "slices_processed_count": 0,
                },
                "runtime_context": {
                    "sessions_scanned": 0,
                    "compactions_done": 0,
                    "distills_done": 0,
                    "approvals_pending": 0,
                    "approvals_delivery_sent": False,
                    "approvals_delivery_reason": "",
                    "sg_promoted_auto": 0,
                    "sg_pending_approval": 0,
                    "outbox_queued": _outbox_metrics(canonical_root)["outbox_queued"],
                    "outbox_delivered": _outbox_metrics(canonical_root)["outbox_delivered"],
                    "outbox_failed": _outbox_metrics(canonical_root)["outbox_failed"],
                },
                "pending_selected_sources": 0,
                "pending_total_sources": 0,
                "plan_id": "",
                "processed_ids": [],
                "surface_scan": {},
                "status": "backoff",
                "state": state,
                "version": 1,
            }
            report["paths"] = _write_autonomy_reports(canonical_root, report)
            return report

        surface_scan_out = run_surface_scan(canonical_root)
        surface_report = surface_scan_out["report"]
        surface_payload: Dict[str, Any] = {
            "fix_actions": [],
            "paths": surface_scan_out["paths"],
            "summary": surface_report["summary"],
        }

        if surface_report["summary"]["drift_count"] > 0:
            fix_out = run_surface_fix(canonical_root)
            surface_report = fix_out["report"]
            surface_payload = {
                "fix_actions": fix_out["report"].get("fix_actions", []),
                "fix_summary": fix_out["report"].get("fix_summary", {}),
                "paths": fix_out["paths"],
                "summary": surface_report["summary"],
            }

        if surface_report["summary"]["drift_grave_count"] > 0:
            errors = [
                f"surface_drift_grave_remaining:{surface_report['summary']['drift_grave_count']}",
                "autonomy_tick stopped before triage/apply to protect instruction surface",
            ]
            state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
            state["last_error"] = "; ".join(errors)[:500]
            state["last_run_utc"] = now.isoformat()
            state["last_status"] = "blocked_surface"
            if int(state.get("consecutive_failures", 0)) >= 3 and not force:
                pause_until = now + timedelta(hours=12)
                state["paused_until_utc"] = pause_until.isoformat()
                state["backoff_until_utc"] = pause_until.isoformat()
                state["auto_paused_reason"] = "three_consecutive_failures_surface_drift"
            _save_state(state_path, state)

            report = {
                "apply_status": "",
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "errors": errors,
                "heartbeat_context": {
                    "pending_drop_count": _pending_drop_count(canonical_root),
                    "sources_pending_count": 0,
                    "ingested_count": 0,
                    "normalized_count": 0,
                    "slices_processed_count": 0,
                },
                "runtime_context": {
                    "sessions_scanned": 0,
                    "compactions_done": 0,
                    "distills_done": 0,
                    "approvals_pending": 0,
                    "approvals_delivery_sent": False,
                    "approvals_delivery_reason": "",
                    "sg_promoted_auto": 0,
                    "sg_pending_approval": 0,
                    "outbox_queued": _outbox_metrics(canonical_root)["outbox_queued"],
                    "outbox_delivered": _outbox_metrics(canonical_root)["outbox_delivered"],
                    "outbox_failed": _outbox_metrics(canonical_root)["outbox_failed"],
                },
                "pending_selected_sources": 0,
                "pending_total_sources": 0,
                "plan_id": "",
                "processed_ids": [],
                "status": "blocked_surface",
                "state": state,
                "surface_scan": surface_payload,
                "version": 1,
            }
            report["paths"] = _write_autonomy_reports(canonical_root, report)
            report["transport"] = _emit_message(
                canonical_root,
                "Autonomy preflight bloqueado: instruction surface drift grave persiste tras auto-fix.",
                send_func,
            )
            return report

        triage_out = run_triage(canonical_root)
        triage = triage_out["report"]
        pending_sources = sorted(triage.get("sources", []), key=lambda item: item["inbox_rel_path"])
        pending_total = len(pending_sources)

        errors: List[str] = []
        plan_id = ""
        apply_status = ""
        processed_ids: List[str] = []
        selected_count = 0
        pending_drop = _pending_drop_count(canonical_root)
        heartbeat_context: Dict[str, Any] = {
            "pending_drop_count": pending_drop,
            "sources_pending_count": pending_total,
            "ingested_count": 0,
            "normalized_count": 0,
            "slices_processed_count": 0,
            "note": "run heartbeat_worker --once to prioritize pending_drop intake" if pending_drop > 0 else "",
        }
        runtime_context: Dict[str, Any] = {
            "sessions_scanned": 0,
            "compactions_done": 0,
            "distills_done": 0,
            "approvals_pending": 0,
            "approvals_delivery_sent": False,
            "approvals_delivery_reason": "",
            "sg_promoted_auto": 0,
            "sg_pending_approval": 0,
            "outbox_queued": 0,
            "outbox_delivered": 0,
            "outbox_failed": 0,
            "safety_paused": bool(safety_status.get("paused", False)),
            "safety_reason": str(safety_status.get("reason", "")),
            "runtime_report": "docs/_inbox/runtime_report_latest.json",
            "approvals_report": "docs/_inbox/approvals_report_latest.json",
            "sg_promotion_report": "docs/_inbox/sg_promotion_report_latest.json",
        }

        if pending_drop > 0:
            errors.append(f"pending_drop_detected:{pending_drop}")

        try:
            runtime_out = run_session_maintenance(
                canonical_root,
                max_sessions=max(1, max_sources_per_tick * 6),
                max_compactions=max(1, max_sources_per_tick * 4),
                max_distills=max(1, max_sources_per_tick * 2),
                max_runtime_seconds=max(30, max_runtime_seconds),
            )
            runtime_summary = runtime_out.get("summary", {})
            runtime_context["sessions_scanned"] = int(runtime_summary.get("sessions_scanned", 0))
            runtime_context["compactions_done"] = int(runtime_summary.get("compactions_done", 0))
            runtime_context["distills_done"] = int(runtime_summary.get("distills_done", 0))
        except Exception as exc:
            errors.append(f"runtime_maintenance_error:{exc}")

        try:
            approvals_out = process_pending_approvals(canonical_root)
            runtime_context["approvals_pending"] = int(approvals_out.get("summary", {}).get("pending_count", 0))
            runtime_context["approvals_delivery_sent"] = bool(approvals_out.get("delivery", {}).get("sent", False))
            runtime_context["approvals_delivery_reason"] = str(approvals_out.get("delivery", {}).get("reason", ""))
        except Exception as exc:
            errors.append(f"approval_manager_error:{exc}")

        try:
            sg_out = process_promotions(canonical_root)
            sg_summary = sg_out.get("summary", {})
            runtime_context["sg_promoted_auto"] = int(sg_summary.get("promoted_auto", 0))
            runtime_context["sg_pending_approval"] = int(sg_summary.get("pending_approval", 0))
        except Exception as exc:
            errors.append(f"sg_promotion_error:{exc}")

        outbox_context = _outbox_metrics(canonical_root)
        runtime_context["outbox_queued"] = outbox_context["outbox_queued"]
        runtime_context["outbox_delivered"] = outbox_context["outbox_delivered"]
        runtime_context["outbox_failed"] = outbox_context["outbox_failed"]

        memory_payload: Dict[str, Any] = {
            "pending_inbox": _memory_pending_count(canonical_root),
            "compact_status": "",
            "index_status": "",
            "paths": {},
        }

        if pending_total == 0:
            status = "idle"
            state["consecutive_failures"] = 0
            state["last_error"] = ""
        else:
            selected = pending_sources[: max(1, max_sources_per_tick)]
            selected_ids = [item["source_id"] for item in selected]
            selected_count = len(selected_ids)

            plan_out = run_plan(
                canonical_root,
                include_source_ids=selected_ids,
                max_sources=max(1, max_sources_per_tick),
            )
            plan = plan_out["plan"]
            plan_id = plan["plan_id"]

            if plan["status"] == "blocked":
                status = "blocked"
                errors.append(f"plan_blocked:{','.join(plan.get('stop_reasons', []))}")
            elif len(plan.get("operations", [])) > max_apply_ops_per_tick:
                status = "blocked"
                errors.append(
                    f"ops_exceeds_limit:{len(plan.get('operations', []))}>{max_apply_ops_per_tick}"
                )
            else:
                apply_out = run_apply(canonical_root, plan_id=plan_id)
                apply_status = apply_out["report"]["status"]
                status = apply_status
                processed_ids = [item["source_id"] for item in apply_out["report"].get("processed_moves", [])]
                heartbeat_context["slices_processed_count"] = sum(
                    1 for src in selected if str(src.get("source_kind", "")) == "chatgpt_slice"
                )
                errors.extend(apply_out["report"].get("errors", []))

            if status in {"success", "idle"}:
                state["consecutive_failures"] = 0
                state["last_error"] = ""
            else:
                state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
                state["last_error"] = "; ".join(errors)[:500]

        if int(state.get("consecutive_failures", 0)) >= 3 and not force:
            pause_until = now + timedelta(hours=12)
            state["paused_until_utc"] = pause_until.isoformat()
            state["backoff_until_utc"] = pause_until.isoformat()
            state["auto_paused_reason"] = "three_consecutive_failures"
            autopause_switch(
                canonical_root,
                reason=f"autonomy_tick_consecutive_failures={state.get('consecutive_failures', 0)}",
                hours=int(safety_policy.get("autopause_hours", 2)),
            )

        state["last_plan_id"] = plan_id or state.get("last_plan_id", "")
        state["last_processed_ids"] = processed_ids
        state["last_run_utc"] = now.isoformat()
        state["last_status"] = status

        memory_payload["pending_inbox"] = _memory_pending_count(canonical_root)
        if memory_payload["pending_inbox"] > 0:
            compact_out = run_memory_compact(canonical_root, apply=True)
            compact_report = compact_out["report"]
            memory_payload["compact_status"] = compact_report["status"]
            memory_payload["paths"].update(
                {
                    "compact_json": compact_out["paths"]["json"],
                    "compact_md": compact_out["paths"]["markdown"],
                    "compact_log": compact_out["paths"]["log"],
                }
            )

            if compact_report["status"] == "success":
                if status == "idle":
                    status = "success"
                index_out = run_memory_index_build(canonical_root)
                memory_payload["index_status"] = "success"
                memory_payload["paths"].update(
                    {
                        "index_json": index_out["paths"]["json"],
                        "index_md": index_out["paths"]["markdown"],
                        "index_log": index_out["paths"]["log"],
                        "index_state": index_out["paths"]["index"],
                    }
                )
            else:
                memory_payload["index_status"] = "skipped_due_compact"
                errors.append(f"memory_compact_status:{compact_report['status']}")
                status = "partial" if status == "success" else status
        else:
            memory_payload["compact_status"] = "idle"
            memory_payload["index_status"] = "idle"

        _save_state(state_path, state)

        report = {
            "apply_status": apply_status,
            "canonical_root": str(canonical_root.resolve()),
            "created_at": now.isoformat(),
            "errors": errors,
            "pending_selected_sources": selected_count,
            "pending_total_sources": pending_total,
            "plan_id": plan_id,
            "processed_ids": processed_ids,
            "status": status,
            "state": state,
            "heartbeat_context": heartbeat_context,
            "runtime_context": runtime_context,
            "memory": memory_payload,
            "surface_scan": surface_payload,
            "triage_paths": triage_out["paths"],
            "version": 1,
        }
        report["paths"] = _write_autonomy_reports(canonical_root, report)

        if status not in {"idle", "paused", "backoff"} or force:
            message = (
                "Autonomy tick\n"
                f"status={status}\n"
                f"pending_total={pending_total}\n"
                f"pending_selected={selected_count}\n"
                f"plan_id={plan_id or '(none)'}\n"
                f"processed_ids={','.join(processed_ids) or '(none)'}\n"
                f"report={report['paths']['markdown']}"
            )
            report["transport"] = _emit_message(canonical_root, message, send_func)

        return report
    finally:
        _release_lock(lock_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run autonomy tick")
    parser.add_argument("--root", default=".")
    parser.add_argument("--repo-doctor", action="store_true", help="Run legacy repo reality autonomy job")
    parser.add_argument("--once", action="store_true", help="Run one autonomous ingest tick")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--pause-hours", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-sources-per-tick", type=int, default=2)
    parser.add_argument("--max-apply-ops-per-tick", type=int, default=250)
    parser.add_argument("--max-runtime-seconds", type=int, default=180)
    parser.add_argument("--interval-hours", type=int, default=24)
    parser.add_argument("--dedupe-hours", type=int, default=24)
    args = parser.parse_args()

    if args.repo_doctor:
        result = run_repo_reality_doctor_job(
            root=args.root,
            interval_hours=max(1, args.interval_hours),
            dedupe_hours=max(1, args.dedupe_hours),
        )
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.pause_hours > 0:
        result = autonomy_pause(args.root, hours=args.pause_hours)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.resume:
        result = autonomy_resume(args.root)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.status:
        result = autonomy_status(args.root)
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    result = run_autonomy_tick(
        root=args.root,
        force=args.force,
        max_sources_per_tick=max(1, args.max_sources_per_tick),
        max_apply_ops_per_tick=max(1, args.max_apply_ops_per_tick),
        max_runtime_seconds=max(30, args.max_runtime_seconds),
    )
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("status") in {"success", "idle", "paused", "backoff", "paused_safety"} else 3


if __name__ == "__main__":
    raise SystemExit(main())

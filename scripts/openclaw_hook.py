#!/usr/bin/env python3
"""Telegram-first hook commands for repository reality doctor."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_reality_doctor import (
    apply_approved_quarantine,
    apply_salvage_plan,
    approve_candidate_ids,
    build_salvage_plan,
    keep_candidate_ids,
    run_doctor,
    run_full_fix,
    write_fix_log,
    write_reports,
)
from scripts.repo_root import (
    CANONICAL_ROOT_MARKER,
    get_canonical_root,
    get_pinned_root,
    list_root_candidates,
    set_canonical_root,
)
from scripts.home_hygiene_doctor import run_home_clean_obvious, run_home_scan
from scripts.workspace_hygiene_doctor import run_workspace_clean, run_workspace_scan
from scripts.corpus_triage import run_triage
from scripts.brain_ingest_router import brain_status, run_apply, run_plan
from scripts.autonomy_tick import (
    autonomy_last,
    autonomy_pause,
    autonomy_resume,
    autonomy_status,
    run_autonomy_tick,
)
from scripts.instruction_surface_doctor import run_surface_fix, run_surface_scan
from scripts.memory_capture import run_capture
from scripts.memory_compact import memory_status, run_memory_compact
from scripts.memory_index_build import run_memory_index_build
from scripts.memory_query import run_memory_query
from scripts.dropbox_intake import run_apply as run_dropbox_intake_apply
from scripts.dropbox_intake import run_scan as run_dropbox_intake_scan
from scripts.chatgpt_export_normalize import run_normalize as run_chatgpt_normalize
from scripts.heartbeat_worker import run_heartbeat_once
from scripts.session_memory_manager import run_session_maintenance
from scripts.sg_promotion import approve_promotion, process_promotions
from scripts.approval_manager import process_pending_approvals
from scripts.channel_ingress_adapter import handle_runtime_event
from scripts.outbox_delivery import run_deliver as run_outbox_deliver
from scripts.outbox_delivery import run_scan as run_outbox_scan


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


def _emit_message(message: str, canonical_root: Path) -> Dict[str, Any]:
    telegram = send_telegram_message(message)
    if telegram.get("sent"):
        return telegram

    outbox = canonical_root / "docs" / "_inbox" / "outbox_latest.md"
    outbox.parent.mkdir(parents=True, exist_ok=True)
    outbox.write_text(message + "\n", encoding="utf-8")
    return {
        "ok": False,
        "sent": False,
        "reason": telegram.get("reason", "missing_config"),
        "outbox": outbox.resolve().relative_to(canonical_root.resolve()).as_posix(),
    }


def _result_error(command: str, message: str) -> Dict[str, Any]:
    return {"ok": False, "command": command, "message": message}


def _build_doctor_summary(command: str, report: Dict[str, Any], paths: Dict[str, str], extra: Optional[List[str]] = None) -> str:
    summary = report["summary"]
    lines = [
        f"Comando: {command}",
        f"Root canonico: {report['canonical_root']}",
        f"Root pinneado: {report.get('pinned_root') or '(no configurado)'}",
        f"Scan base: {report.get('scan_base', '')}",
        f"Candidates: {summary['candidate_count']}",
        f"Pending: {summary['pending_count']}",
        f"Pathlike: {summary.get('pathlike_count', 0)}",
        f"Backups: {summary.get('backup_count', 0)}",
        f"Nested git: {summary['nested_git_count']}",
        f"Report md: {paths['markdown']}",
        f"Report json: {paths['json']}",
    ]
    if extra:
        lines.extend(extra)
    return "\n".join(lines)


def _require_clean_pin(anchor: Path) -> Optional[Dict[str, Any]]:
    pinned = get_pinned_root(anchor, require_clean=True)
    if pinned is None:
        return _result_error(
            "/repo",
            "No hay root limpio pinneado. Ejecuta /repo roots y /repo setroot <id>.",
        )
    return None


def _command_roots(anchor: Path) -> Dict[str, Any]:
    candidates = list_root_candidates(anchor)
    pinned = get_pinned_root(anchor, require_clean=False)

    lines = [
        "Comando: /repo roots",
        f"Pinned marker: {str(pinned) if pinned else '(not set)'}",
        f"Marker file: {CANONICAL_ROOT_MARKER}",
        f"Candidate count: {len(candidates)}",
    ]

    for item in candidates[:12]:
        lines.append(
            f"- id={item.candidate_id} clean={item.clean} safe_for_pin={item.safe_for_pin} score={item.score} has_git={item.has_git} path={item.path}"
        )

    message = "\n".join(lines)

    base = anchor if anchor.is_dir() else anchor.parent
    canonical = base.resolve()
    transport = _emit_message(message, canonical)

    return {
        "ok": True,
        "command": "/repo roots",
        "message": message,
        "pinned_root": str(pinned) if pinned else "",
        "candidates": [
            {
                "candidate_id": item.candidate_id,
                "clean": item.clean,
                "has_git": item.has_git,
                "markers_found": item.markers_found,
                "path": item.path,
                "reason": item.reason,
                "safe_for_pin": item.safe_for_pin,
                "score": item.score,
            }
            for item in candidates
        ],
        "transport": transport,
    }


def _command_setroot(anchor: Path, candidate_id: str) -> Dict[str, Any]:
    candidates = {item.candidate_id: item for item in list_root_candidates(anchor)}
    selected = candidates.get(candidate_id)
    if selected is None:
        return _result_error("/repo setroot", f"Unknown candidate id: {candidate_id}")
    if not selected.safe_for_pin:
        return _result_error(
            "/repo setroot",
            "Candidate no apto para pin limpio (requiere path limpio y .git o markers fuertes).",
        )

    pin = set_canonical_root(selected.path, created_by="telegram", reason="seq005_clean_root")
    canonical_root = Path(pin["payload"]["root_realpath"])

    report = run_doctor(canonical_root, apply=False)
    paths = write_reports(report, canonical_root)

    message = _build_doctor_summary(
        "/repo setroot",
        report,
        paths,
        extra=[
            f"Pinned candidate id: {candidate_id}",
            f"Pinned marker: {pin['marker_path']}",
            "Root limpio pinneado correctamente.",
        ],
    )
    transport = _emit_message(message, canonical_root)

    return {
        "ok": True,
        "command": "/repo setroot",
        "candidate_id": candidate_id,
        "canonical_root": str(canonical_root),
        "pinned_marker": pin["marker_path"],
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "transport": transport,
    }


def _command_scan(command: str, canonical_root: Path) -> Dict[str, Any]:
    report = run_doctor(canonical_root, apply=False)
    paths = write_reports(report, canonical_root)
    message = _build_doctor_summary(command, report, paths)
    transport = _emit_message(message, canonical_root)

    return {
        "ok": True,
        "command": command,
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "transport": transport,
    }


def _command_keep(canonical_root: Path, candidate_id: str) -> Dict[str, Any]:
    keep_result = keep_candidate_ids(canonical_root, [candidate_id])
    report = run_doctor(canonical_root, apply=False)
    paths = write_reports(report, canonical_root)

    message = _build_doctor_summary(
        "/repo keep",
        report,
        paths,
        extra=[f"keep_result={json.dumps(keep_result, sort_keys=True)}"],
    )
    transport = _emit_message(message, canonical_root)

    return {
        "ok": True,
        "command": "/repo keep",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "keep_result": keep_result,
        "transport": transport,
    }


def _command_quarantine(canonical_root: Path, candidate_id: str) -> Dict[str, Any]:
    approved = approve_candidate_ids(canonical_root, [candidate_id])
    applied = apply_approved_quarantine(canonical_root)
    report = applied["report"]
    paths = write_reports(report, canonical_root)
    fix_log = write_fix_log(applied, canonical_root)

    message = _build_doctor_summary(
        "/repo quarantine",
        report,
        paths,
        extra=[
            f"approve_result={json.dumps(approved, sort_keys=True)}",
            f"fix_log={fix_log}",
        ],
    )
    transport = _emit_message(message, canonical_root)

    return {
        "ok": True,
        "command": "/repo quarantine",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "approve_result": approved,
        "apply_result": applied["apply"],
        "fix_log": fix_log,
        "transport": transport,
    }


def _command_salvage(canonical_root: Path) -> Dict[str, Any]:
    plan = build_salvage_plan(canonical_root)

    message = (
        "Encontré copias fantasma y preparé salvage determinista.\n"
        f"root={plan['canonical_root']}\n"
        f"candidates={plan['summary']['candidate_count']}\n"
        f"salvage_candidates={plan['summary']['salvage_candidate_count']}\n"
        f"entries={plan['summary']['entry_count']}\n"
        f"conflicts={plan['summary']['conflict_count']}\n"
        f"blocked={plan['summary']['blocked']}\n"
        f"report_md={plan['paths']['markdown']}\n"
        f"report_json={plan['paths']['json']}"
    )
    transport = _emit_message(message, canonical_root)

    return {
        "ok": True,
        "command": "/repo salvage",
        "canonical_root": str(canonical_root),
        "message": message,
        "plan": plan,
        "transport": transport,
    }


def _command_apply_salvage(canonical_root: Path) -> Dict[str, Any]:
    result = apply_salvage_plan(canonical_root)
    report = run_doctor(canonical_root, apply=False)
    paths = write_reports(report, canonical_root)

    message = _build_doctor_summary(
        "/repo apply-salvage",
        report,
        paths,
        extra=[f"salvage_apply={json.dumps(result, sort_keys=True)}"],
    )
    transport = _emit_message(message, canonical_root)

    return {
        "ok": bool(result.get("ok", False)),
        "command": "/repo apply-salvage",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "salvage_apply": result,
        "transport": transport,
    }


def _command_fix(canonical_root: Path) -> Dict[str, Any]:
    result = run_full_fix(canonical_root)
    report = result.get("report", run_doctor(canonical_root, apply=False))
    paths = write_reports(report, canonical_root)
    fix_log = write_fix_log(result, canonical_root)

    message = _build_doctor_summary(
        "/repo fix",
        report,
        paths,
        extra=[
            "Encontré copias fantasma; rescaté lo único y moví a cuarentena según defaults.",
            f"fix_status={result.get('status')}",
            f"fix_log={fix_log}",
        ],
    )
    transport = _emit_message(message, canonical_root)

    return {
        "ok": result.get("status") != "blocked",
        "command": "/repo fix",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "fix_result": result,
        "fix_log": fix_log,
        "transport": transport,
    }


def _command_repo_hygiene(canonical_root: Path) -> Dict[str, Any]:
    result = run_workspace_scan(canonical_root)
    report = result["report"]
    paths = result["paths"]
    summary = report["summary"]
    message = (
        "Comando: /repo hygiene\n"
        f"Root canonico: {report['canonical_root']}\n"
        f"Candidates: {summary['candidate_count']}\n"
        f"Sensitive: {summary['sensitive_count']}\n"
        f"Junk: {summary['junk_count']}\n"
        f"Report md: {paths['markdown']}\n"
        f"Report json: {paths['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/repo hygiene",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": summary,
        "transport": transport,
    }


def _command_repo_clean(canonical_root: Path) -> Dict[str, Any]:
    result = run_workspace_clean(canonical_root)
    report = result["report"]
    paths = result["paths"]
    clean_result = result["result"]
    message = (
        "Comando: /repo clean\n"
        "Workspace hygiene (junk+sensitive) ejecutado.\n"
        f"Root canonico: {report['canonical_root']}\n"
        f"Status: {clean_result['status']}\n"
        f"Moved: {clean_result.get('moved_count', 0)}\n"
        f"Blocked: {clean_result.get('blocked_reason', '')}\n"
        f"Report md: {paths['markdown']}\n"
        f"Report json: {paths['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": clean_result.get("status") == "ok",
        "command": "/repo clean",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "clean_result": clean_result,
        "transport": transport,
    }


def _command_home_hygiene(canonical_root: Path) -> Dict[str, Any]:
    home_root = Path.home().resolve()
    result = run_home_scan(canonical_root, home_root)
    report = result["report"]
    paths = result["paths"]
    summary = report["summary"]
    message = (
        "Comando: /home hygiene\n"
        f"Home root: {report['home_root']}\n"
        f"Candidates: {summary['candidate_count']}\n"
        f"Sensitive: {summary['sensitive_count']}\n"
        f"Junk: {summary['junk_count']}\n"
        f"Skipped dot-dirs: {summary['skipped_dotdirs']}\n"
        f"Report md: {paths['markdown']}\n"
        f"Report json: {paths['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/home hygiene",
        "canonical_root": str(canonical_root),
        "home_root": str(home_root),
        "message": message,
        "paths": paths,
        "summary": summary,
        "transport": transport,
    }


def _command_home_clean(canonical_root: Path) -> Dict[str, Any]:
    home_root = Path.home().resolve()
    result = run_home_clean_obvious(canonical_root, home_root)
    report = result["report"]
    paths = result["paths"]
    clean_result = result["result"]
    message = (
        "Comando: /home clean\n"
        "Home hygiene clean-obvious ejecutado.\n"
        f"Home root: {report['home_root']}\n"
        f"Status: {clean_result['status']}\n"
        f"Moved: {clean_result.get('moved_count', 0)}\n"
        f"Blocked: {clean_result.get('blocked_reason', '')}\n"
        f"Report md: {paths['markdown']}\n"
        f"Report json: {paths['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": clean_result.get("status") == "ok",
        "command": "/home clean",
        "canonical_root": str(canonical_root),
        "home_root": str(home_root),
        "message": message,
        "paths": paths,
        "summary": report["summary"],
        "clean_result": clean_result,
        "transport": transport,
    }


def _command_brain_triage(canonical_root: Path) -> Dict[str, Any]:
    result = run_triage(canonical_root)
    report = result["report"]
    paths = result["paths"]
    summary = report["summary"]
    message = (
        "Comando: /brain triage\n"
        f"Pending sources: {summary['pending_sources']}\n"
        f"Pending files: {summary['pending_files']}\n"
        f"Pending bytes: {summary['pending_total_bytes']}\n"
        f"High signal: {summary['high_signal_sources']}\n"
        f"Suspicious entries: {summary['suspicious_entries']}\n"
        f"Report md: {paths['markdown']}\n"
        f"Report json: {paths['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/brain triage",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": summary,
        "transport": transport,
    }


def _command_brain_plan(canonical_root: Path) -> Dict[str, Any]:
    out = run_plan(canonical_root)
    plan = out["plan"]
    paths = out["paths"]
    triage = plan["triage_summary"]
    message = (
        "Comando: /brain plan\n"
        f"Plan ID: {plan['plan_id']}\n"
        f"Status: {plan['status']}\n"
        f"Stop reasons: {', '.join(plan['stop_reasons'])}\n"
        f"Pending sources: {triage['pending_sources']}\n"
        f"Operations: {len(plan['operations'])}\n"
        f"Report md: {paths['markdown']}\n"
        f"Plan json: {paths['plan_file']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": plan["status"] != "blocked",
        "command": "/brain plan",
        "canonical_root": str(canonical_root),
        "message": message,
        "plan_id": plan["plan_id"],
        "paths": paths,
        "summary": triage,
        "stop_reasons": plan["stop_reasons"],
        "transport": transport,
    }


def _command_brain_apply(canonical_root: Path, plan_id: str) -> Dict[str, Any]:
    out = run_apply(canonical_root, plan_id=plan_id)
    report = out["report"]
    paths = out["paths"]
    summary = report["summary"]
    message = (
        "Comando: /brain apply\n"
        f"Plan ID: {plan_id}\n"
        f"Status: {report['status']}\n"
        f"Created: {summary['created']}\n"
        f"Unchanged: {summary['unchanged']}\n"
        f"Conflicts(side-by-side): {summary['conflict_side_by_side']}\n"
        f"Processed moves: {summary['processed_moves']}\n"
        f"Report md: {paths['markdown']}\n"
        f"Report json: {paths['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": report["status"] == "success",
        "command": "/brain apply",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": paths,
        "summary": summary,
        "errors": report["errors"],
        "transport": transport,
    }


def _command_brain_status(canonical_root: Path) -> Dict[str, Any]:
    status = brain_status(canonical_root)
    message = (
        "Comando: /brain status\n"
        f"Pending sources: {status['pending_sources']}\n"
        f"Pending files: {status['pending_files']}\n"
        f"Latest plan: {status['latest_plan'] or '(none)'}\n"
        f"Latest triage report: {status['latest_triage_report'] or '(none)'}\n"
        f"Latest plan report: {status['latest_plan_report'] or '(none)'}\n"
        f"Latest apply report: {status['latest_apply_report'] or '(none)'}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/brain status",
        "canonical_root": str(canonical_root),
        "message": message,
        "status": status,
        "transport": transport,
    }


def _command_autonomy_status(canonical_root: Path) -> Dict[str, Any]:
    status = autonomy_status(canonical_root)
    surface = status.get("surface_summary", {})
    message = (
        "Comando: /autonomy status\n"
        f"Pending sources: {status['pending_sources']}\n"
        f"Pending files: {status['pending_files']}\n"
        f"Last status: {status['last_status']}\n"
        f"Last plan id: {status['last_plan_id'] or '(none)'}\n"
        f"Surface drift: {surface.get('drift_count', 0)}\n"
        f"Surface drift grave: {surface.get('drift_grave_count', 0)}\n"
        f"Paused until: {status['paused_until_utc'] or '(none)'}\n"
        f"Failures: {status['consecutive_failures']}\n"
        f"Latest report: {status['latest_report_md'] or '(none)'}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/autonomy status",
        "canonical_root": str(canonical_root),
        "message": message,
        "status": status,
        "transport": transport,
    }


def _command_autonomy_run(canonical_root: Path) -> Dict[str, Any]:
    out = run_autonomy_tick(root=canonical_root, force=True)
    message = (
        "Comando: /autonomy run\n"
        f"Status: {out['status']}\n"
        f"Pending total: {out['pending_total_sources']}\n"
        f"Selected: {out['pending_selected_sources']}\n"
        f"Plan id: {out.get('plan_id', '') or '(none)'}\n"
        f"Processed ids: {','.join(out.get('processed_ids', [])) or '(none)'}\n"
        f"Report md: {out['paths']['markdown']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": out["status"] in {"success", "idle", "paused", "backoff"},
        "command": "/autonomy run",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_autonomy_pause(canonical_root: Path, hours: int) -> Dict[str, Any]:
    out = autonomy_pause(canonical_root, hours=hours)
    message = (
        "Comando: /autonomy pause\n"
        f"Paused until: {out['paused_until_utc']}\n"
        f"Root: {out['canonical_root']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": out.get("ok", False),
        "command": "/autonomy pause",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_autonomy_resume(canonical_root: Path) -> Dict[str, Any]:
    out = autonomy_resume(canonical_root)
    message = (
        "Comando: /autonomy resume\n"
        f"Resumed: {out.get('ok', False)}\n"
        f"Root: {out['canonical_root']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": out.get("ok", False),
        "command": "/autonomy resume",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_autonomy_last(canonical_root: Path) -> Dict[str, Any]:
    out = autonomy_last(canonical_root)
    message = (
        "Comando: /autonomy last\n"
        f"Autonomy md: {out['autonomy_md'] or '(none)'}\n"
        f"Triage json: {out['triage_json'] or '(none)'}\n"
        f"Plan json: {out['plan_json'] or '(none)'}\n"
        f"Apply json: {out['apply_json'] or '(none)'}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/autonomy last",
        "canonical_root": str(canonical_root),
        "message": message,
        "last": out,
        "transport": transport,
    }


def _command_context_surface(canonical_root: Path) -> Dict[str, Any]:
    out = run_surface_scan(canonical_root)
    summary = out["report"]["summary"]
    message = (
        "Comando: /context surface\n"
        f"Reserved found: {summary['reserved_found']}\n"
        f"Drift: {summary['drift_count']}\n"
        f"Drift grave: {summary['drift_grave_count']}\n"
        f"Allowed: {summary['allowed_count']}\n"
        f"Report md: {out['paths']['markdown']}\n"
        f"Report json: {out['paths']['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/context surface",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": out["paths"],
        "summary": summary,
        "transport": transport,
    }


def _command_context_fix(canonical_root: Path) -> Dict[str, Any]:
    out = run_surface_fix(canonical_root)
    summary = out["report"]["summary"]
    fix_summary = out["report"].get("fix_summary", {})
    message = (
        "Comando: /context fix\n"
        f"Moved: {fix_summary.get('moved_count', 0)}\n"
        f"Pre drift: {fix_summary.get('pre_drift_count', 0)}\n"
        f"Post drift: {fix_summary.get('post_drift_count', 0)}\n"
        f"Post drift grave: {fix_summary.get('post_drift_grave_count', 0)}\n"
        f"Report md: {out['paths']['markdown']}\n"
        f"Report json: {out['paths']['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": summary["drift_grave_count"] == 0,
        "command": "/context fix",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": out["paths"],
        "summary": summary,
        "fix_summary": fix_summary,
        "transport": transport,
    }


def _command_context_status(canonical_root: Path) -> Dict[str, Any]:
    out = run_surface_scan(canonical_root)
    summary = out["report"]["summary"]
    message = (
        "Comando: /context status\n"
        f"Drift actual: {summary['drift_count']}\n"
        f"Drift grave actual: {summary['drift_grave_count']}\n"
        f"Needs user: {summary['needs_user_count']}\n"
        f"Ultimo reporte: {out['paths']['markdown']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/context status",
        "canonical_root": str(canonical_root),
        "message": message,
        "paths": out["paths"],
        "summary": summary,
        "transport": transport,
    }


def _command_memory_status(canonical_root: Path) -> Dict[str, Any]:
    status = memory_status(canonical_root)
    message = (
        "Comando: /memory status\n"
        f"Inbox pending: {status['inbox_pending']}\n"
        f"Last compact: {status['last_compact'] or '(none)'}\n"
        f"Last index: {status['last_index'] or '(none)'}\n"
        f"Best known totals: {json.dumps(status['best_known_totals'], sort_keys=True)}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/memory status",
        "canonical_root": str(canonical_root),
        "message": message,
        "status": status,
        "transport": transport,
    }


def _command_memory_capture(canonical_root: Path, text: str) -> Dict[str, Any]:
    clean_text = text.strip()
    if not clean_text:
        return _result_error("/memory capture", "Usage: /memory capture <texto>")

    lowered = clean_text.lower()
    record_type = "note_raw"
    if lowered.startswith(("yo ", "mi ", "i ", "my ")):
        record_type = "profile_fact"

    out = run_capture(
        canonical_root,
        record_type=record_type,
        key="",
        source_ref="hook:/memory capture",
        confidence="medium",
        tags_csv="hook,memory",
        text=clean_text,
        fields={},
    )
    message = (
        "Comando: /memory capture\n"
        f"Type: {record_type}\n"
        f"Record id: {out['record']['id']}\n"
        f"Inbox: {out['inbox_path']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/memory capture",
        "canonical_root": str(canonical_root),
        "message": message,
        "record": out["record"],
        "transport": transport,
    }


def _command_memory_compact(canonical_root: Path) -> Dict[str, Any]:
    compact_out = run_memory_compact(canonical_root, apply=True)
    compact_report = compact_out["report"]
    index_paths: Dict[str, str] = {}
    index_status = "skipped"
    if compact_report["status"] == "success":
        index_out = run_memory_index_build(canonical_root)
        index_status = "success"
        index_paths = dict(index_out["paths"])

    message = (
        "Comando: /memory compact\n"
        f"Compact status: {compact_report['status']}\n"
        f"Incoming valid: {compact_report['summary']['incoming_valid']}\n"
        f"Final records: {compact_report['summary']['final_records']}\n"
        f"Index status: {index_status}\n"
        f"Compact report: {compact_out['paths']['markdown']}\n"
        f"Index report: {index_paths.get('markdown', '(none)')}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": compact_report["status"] == "success",
        "command": "/memory compact",
        "canonical_root": str(canonical_root),
        "message": message,
        "compact": compact_out,
        "index_status": index_status,
        "index_paths": index_paths,
        "transport": transport,
    }


def _command_memory_ask(canonical_root: Path, question: str) -> Dict[str, Any]:
    clean_question = question.strip()
    if not clean_question:
        return _result_error("/memory ask", "Usage: /memory ask <pregunta>")

    out = run_memory_query(
        canonical_root,
        question=clean_question,
        k=8,
        types=[],
        include_superseded=False,
        evidence=True,
        output_format="md",
    )
    message = f"Comando: /memory ask\nPregunta: {clean_question}\n\n{out['markdown'].strip()}"
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/memory ask",
        "canonical_root": str(canonical_root),
        "message": message,
        "result_count": out["result_count"],
        "results": out["results"],
        "transport": transport,
    }


def _command_inbox_status(canonical_root: Path) -> Dict[str, Any]:
    intake = run_dropbox_intake_scan(canonical_root)
    summary = intake["report"]["summary"]
    sources_root = canonical_root / "vault" / "inbox_raw" / "sources"
    chatgpt_normalized = 0
    slices_pending = 0
    sources_pending = 0
    if sources_root.is_dir():
        for source_dir in sorted(sources_root.iterdir(), key=lambda p: p.name):
            if not source_dir.is_dir():
                continue
            hints_path = source_dir / "HINTS.json"
            if not hints_path.is_file():
                sources_pending += 1
                continue
            try:
                hints = json.loads(hints_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                hints = {}
            status = str(hints.get("normalize_status", ""))
            suspected = str(hints.get("suspected_kind", ""))
            if suspected == "chatgpt_export":
                if status == "ok":
                    chatgpt_normalized += 1
                slices_index = source_dir / "normalized" / "slices_index.json"
                if slices_index.is_file():
                    try:
                        payload = json.loads(slices_index.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        payload = {}
                    slices = payload.get("slices", []) if isinstance(payload.get("slices", []), list) else []
                    for item in slices:
                        if not isinstance(item, dict):
                            continue
                        rel = str(item.get("path", "")).strip()
                        if rel and (source_dir / rel).is_file():
                            slices_pending += 1
            if status != "ok":
                sources_pending += 1

    message = (
        "Comando: /inbox status\n"
        f"Pending drop count: {summary['pending_count']}\n"
        f"New pending: {summary['new_count']}\n"
        f"Duplicate pending: {summary['duplicate_count']}\n"
        f"Sources pending count: {sources_pending}\n"
        f"ChatGPT normalized count: {chatgpt_normalized}\n"
        f"Slices pending count: {slices_pending}\n"
        f"Intake report: {intake['paths']['markdown']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/inbox status",
        "canonical_root": str(canonical_root),
        "message": message,
        "intake": intake,
        "sources_pending_count": sources_pending,
        "chatgpt_normalized_count": chatgpt_normalized,
        "slices_pending_count": slices_pending,
        "transport": transport,
    }


def _command_inbox_intake(canonical_root: Path) -> Dict[str, Any]:
    out = run_dropbox_intake_apply(canonical_root)
    apply = out["report"].get("apply", {})
    message = (
        "Comando: /inbox intake\n"
        f"Ingested count: {apply.get('ingested_count', 0)}\n"
        f"Pending after intake: {out['report']['summary']['pending_count']}\n"
        f"Report md: {out['paths']['markdown']}\n"
        f"Report json: {out['paths']['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/inbox intake",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_inbox_normalize(canonical_root: Path, source_id: str) -> Dict[str, Any]:
    out = run_chatgpt_normalize(canonical_root, source_id=source_id, scan_latest=(not source_id))
    summary = out["report"]["summary"]
    message = (
        "Comando: /inbox normalize\n"
        f"Target count: {summary['target_count']}\n"
        f"ChatGPT detected: {summary['chatgpt_detected_count']}\n"
        f"Normalized count: {summary['normalized_count']}\n"
        f"Slice count: {summary['slice_count']}\n"
        f"Report md: {out['paths']['markdown']}\n"
        f"Report json: {out['paths']['json']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/inbox normalize",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_heartbeat_run(canonical_root: Path) -> Dict[str, Any]:
    out = run_heartbeat_once(canonical_root, force=True)
    message = (
        "Comando: /heartbeat run\n"
        f"Status: {out['report']['status']}\n"
        f"Pending drop: {out['report']['summary'].get('pending_drop_count', 0)}\n"
        f"Ingested: {out['report']['summary'].get('ingested_count', 0)}\n"
        f"Normalized: {out['report']['summary'].get('normalized_count', 0)}\n"
        f"Slices processed: {out['report']['summary'].get('slices_processed_count', 0)}\n"
        f"Report md: {out['paths']['markdown']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": out["report"]["status"] in {"success", "skipped_interval"},
        "command": "/heartbeat run",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_heartbeat_status(canonical_root: Path) -> Dict[str, Any]:
    report_path = canonical_root / "docs" / "_inbox" / "heartbeat_latest.json"
    payload: Dict[str, Any] = {}
    if report_path.is_file():
        try:
            parsed = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed
    status = str(payload.get("status", "never"))
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    message = (
        "Comando: /heartbeat status\n"
        f"Last status: {status}\n"
        f"Last run: {payload.get('created_at', '(none)')}\n"
        f"Pending drop: {summary.get('pending_drop_count', 0)}\n"
        f"Ingested: {summary.get('ingested_count', 0)}\n"
        f"Normalized: {summary.get('normalized_count', 0)}\n"
        f"Last report: docs/_inbox/heartbeat_latest.md"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/heartbeat status",
        "canonical_root": str(canonical_root),
        "message": message,
        "status": payload,
        "transport": transport,
    }


def _command_runtime_status(canonical_root: Path) -> Dict[str, Any]:
    approvals_sync = process_pending_approvals(canonical_root)
    runtime_path = canonical_root / "docs" / "_inbox" / "runtime_report_latest.json"
    runtime: Dict[str, Any] = {}
    if runtime_path.is_file():
        try:
            parsed = json.loads(runtime_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            runtime = parsed

    sg_path = canonical_root / "docs" / "_inbox" / "sg_promotion_report_latest.json"
    sg_payload: Dict[str, Any] = {}
    if sg_path.is_file():
        try:
            parsed = json.loads(sg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            sg_payload = parsed

    approvals_path = canonical_root / "docs" / "_inbox" / "approvals_report_latest.json"
    approvals_payload: Dict[str, Any] = {}
    if approvals_path.is_file():
        try:
            parsed = json.loads(approvals_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            approvals_payload = parsed

    ingress_path = canonical_root / "docs" / "_inbox" / "ingress_report_latest.json"
    ingress_payload: Dict[str, Any] = {}
    if ingress_path.is_file():
        try:
            parsed = json.loads(ingress_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            ingress_payload = parsed

    sessions_root = canonical_root / "state" / "sessions"
    sessions_total = 0
    if sessions_root.is_dir():
        sessions_total = len([item for item in sessions_root.iterdir() if item.is_dir()])

    summary = runtime.get("summary", {}) if isinstance(runtime.get("summary", {}), dict) else {}
    sg_summary = sg_payload.get("summary", {}) if isinstance(sg_payload.get("summary", {}), dict) else {}
    approvals_summary = approvals_payload.get("summary", {}) if isinstance(approvals_payload.get("summary", {}), dict) else {}
    ingress_event = ingress_payload.get("event", {}) if isinstance(ingress_payload.get("event", {}), dict) else {}
    message = (
        "Comando: /runtime status\n"
        f"Sessions total: {sessions_total}\n"
        f"Sessions scanned: {summary.get('sessions_scanned', 0)}\n"
        f"Compactions done: {summary.get('compactions_done', 0)}\n"
        f"Distills done: {summary.get('distills_done', 0)}\n"
        f"Approvals pending: {approvals_summary.get('pending_count', 0)}\n"
        f"SG pending approval: {sg_summary.get('pending_approval', 0)}\n"
        f"Last ingress channel: {ingress_event.get('channel', '(none)')}\n"
        "Report md: docs/_inbox/runtime_report_latest.md"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/runtime status",
        "canonical_root": str(canonical_root),
        "message": message,
        "runtime": runtime,
        "approvals_sync": approvals_sync,
        "approvals_summary": approvals_summary,
        "sg_summary": sg_summary,
        "ingress": ingress_payload,
        "transport": transport,
    }


def _command_runtime_ingress(canonical_root: Path, payload_text: str) -> Dict[str, Any]:
    payload_raw = payload_text.strip()
    if not payload_raw:
        return _result_error("/runtime ingest", "Usage: /runtime ingest <event-json|path>")
    path = Path(payload_raw)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(payload_raw)
    if not isinstance(payload, dict):
        return _result_error("/runtime ingest", "event payload must be a JSON object")

    out = handle_runtime_event(canonical_root, payload)
    message = (
        "Comando: /runtime ingest\n"
        f"Status: {out.get('status', 'unknown')}\n"
        f"Session: {out.get('session_id', '')}\n"
        f"Intent: {out.get('primary_intent', '')}\n"
        f"Labels: {', '.join(out.get('labels', []))}\n"
        "Report md: docs/_inbox/ingress_report_latest.md"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/runtime ingest",
        "canonical_root": str(canonical_root),
        "message": message,
        "ingress": out,
        "transport": transport,
    }


def _command_approvals_status(canonical_root: Path) -> Dict[str, Any]:
    report_path = canonical_root / "docs" / "_inbox" / "approvals_report_latest.json"
    payload: Dict[str, Any] = {}
    if report_path.is_file():
        try:
            parsed = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed
    summary = payload.get("summary", {}) if isinstance(payload.get("summary", {}), dict) else {}
    delivery = payload.get("delivery", {}) if isinstance(payload.get("delivery", {}), dict) else {}
    message = (
        "Comando: /approvals status\n"
        f"Pending: {summary.get('pending_count', 0)}\n"
        f"Pending SG: {summary.get('pending_sg_promotion', 0)}\n"
        f"Pending worker pairing: {summary.get('pending_worker_pairing', 0)}\n"
        f"Delivery channel: {delivery.get('channel', 'telegram_owner')}\n"
        f"Delivery sent: {delivery.get('sent', False)}\n"
        "Report md: docs/_inbox/approvals_report_latest.md"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/approvals status",
        "canonical_root": str(canonical_root),
        "message": message,
        "approvals": payload,
        "transport": transport,
    }


def _command_discord_domains_status(canonical_root: Path) -> Dict[str, Any]:
    state_path = canonical_root / "state" / "discord_domains.json"
    payload: Dict[str, Any] = {}
    if state_path.is_file():
        try:
            parsed = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed
    domains = payload.get("domains", {}) if isinstance(payload.get("domains", {}), dict) else {}
    sample = sorted(domains.items(), key=lambda item: item[0])[:5]
    sample_text = ", ".join(f"{cid}:{str(data.get('domain_slug',''))}" for cid, data in sample)
    message = (
        "Comando: /discord domains status\n"
        f"Total mapped channels: {len(domains)}\n"
        f"Updated at: {payload.get('updated_at', '')}\n"
        f"Sample: {sample_text or '(none)'}\n"
        "State file: state/discord_domains.json"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/discord domains status",
        "canonical_root": str(canonical_root),
        "message": message,
        "domains": payload,
        "transport": transport,
    }


def _command_outbox_status(canonical_root: Path) -> Dict[str, Any]:
    out = run_outbox_scan(canonical_root)
    summary = out["report"]["summary"]
    message = (
        "Comando: /outbox status\n"
        f"Queue total: {summary.get('queue_total', 0)}\n"
        f"Queue pending: {summary.get('queue_pending', 0)}\n"
        f"Delivered total: {summary.get('queue_delivered', 0)}\n"
        f"Failed retryable: {summary.get('queue_failed_retryable', 0)}\n"
        f"Report md: {out['paths']['markdown']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/outbox status",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_outbox_deliver(canonical_root: Path) -> Dict[str, Any]:
    out = run_outbox_deliver(canonical_root)
    summary = out["report"]["summary"]
    message = (
        "Comando: /outbox deliver\n"
        f"Status: {out['report']['status']}\n"
        f"Processed in run: {summary.get('processed_in_run', 0)}\n"
        f"Delivered in run: {summary.get('delivered_in_run', 0)}\n"
        f"Failed in run: {summary.get('failed_in_run', 0)}\n"
        f"Queue pending: {summary.get('queue_pending', 0)}\n"
        f"Report md: {out['paths']['markdown']}"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": out["report"]["status"] in {"success", "partial", "deferred"},
        "command": "/outbox deliver",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def _command_runtime_compact(canonical_root: Path) -> Dict[str, Any]:
    out = run_session_maintenance(
        canonical_root,
        max_sessions=200,
        max_compactions=200,
        max_distills=0,
        max_runtime_seconds=300,
    )
    summary = out.get("summary", {})
    message = (
        "Comando: /runtime compact\n"
        f"Sessions scanned: {summary.get('sessions_scanned', 0)}\n"
        f"Compactions done: {summary.get('compactions_done', 0)}\n"
        f"Distills done: {summary.get('distills_done', 0)}\n"
        "Report md: docs/_inbox/runtime_report_latest.md"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/runtime compact",
        "canonical_root": str(canonical_root),
        "message": message,
        "runtime": out,
        "transport": transport,
    }


def _command_runtime_distill(canonical_root: Path) -> Dict[str, Any]:
    out = run_session_maintenance(
        canonical_root,
        max_sessions=200,
        max_compactions=0,
        max_distills=200,
        max_runtime_seconds=300,
    )
    summary = out.get("summary", {})
    message = (
        "Comando: /runtime distill\n"
        f"Sessions scanned: {summary.get('sessions_scanned', 0)}\n"
        f"Compactions done: {summary.get('compactions_done', 0)}\n"
        f"Distills done: {summary.get('distills_done', 0)}\n"
        "Report md: docs/_inbox/runtime_report_latest.md"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/runtime distill",
        "canonical_root": str(canonical_root),
        "message": message,
        "runtime": out,
        "transport": transport,
    }


def _command_sg_approve(canonical_root: Path, promotion_id: str) -> Dict[str, Any]:
    out = approve_promotion(canonical_root, promotion_id)
    summary = out.get("summary", {})
    message = (
        "Comando: /sg approve\n"
        f"Approved id: {promotion_id}\n"
        f"Pending: {summary.get('pending', 0)}\n"
        f"Promoted: {summary.get('promoted', 0)}\n"
        f"Pending approval: {summary.get('pending_approval', 0)}\n"
        "Report md: docs/_inbox/sg_promotion_report_latest.md"
    )
    transport = _emit_message(message, canonical_root)
    return {
        "ok": True,
        "command": "/sg approve",
        "canonical_root": str(canonical_root),
        "message": message,
        "result": out,
        "transport": transport,
    }


def handle_repo_command(command_text: str, *, root: Optional[str | Path] = None) -> Dict[str, Any]:
    command = command_text.strip()
    anchor = Path(root or ".").resolve()
    parts = command.split()

    if len(parts) < 2 or parts[0] not in {"/repo", "/home", "/brain", "/autonomy", "/context", "/memory", "/inbox", "/heartbeat", "/runtime", "/outbox", "/sg", "/approvals", "/discord"}:
        return _result_error(
            command,
            "Unknown command. Use /repo roots|setroot|status|doctor|hygiene|clean|salvage|apply-salvage|fix|quarantine|keep, /home hygiene|clean, /brain triage|plan|apply|status, /autonomy status|run|pause|resume|last, /context surface|fix|status, /memory status|capture|compact|ask, /inbox status|intake|normalize, /heartbeat run|status, /runtime status|compact|distill|ingest, /outbox status|deliver|replay <batch_id>, /approvals status, /discord domains status, or /sg approve <id>.",
        )

    scope = parts[0]
    sub = parts[1]

    if scope == "/repo" and sub == "roots":
        return _command_roots(anchor)

    if scope == "/repo" and sub == "setroot":
        if len(parts) < 3:
            return _result_error(command, "Usage: /repo setroot <id>")
        return _command_setroot(anchor, parts[2])

    # For operational commands, always resolve against the clean canonical root.
    try:
        canonical_root = get_canonical_root(anchor)
    except Exception as exc:
        return _result_error(command, f"No pude resolver root limpio: {exc}")

    if scope == "/repo" and sub in {"status", "doctor"}:
        return _command_scan(f"/repo {sub}", canonical_root)

    if scope == "/repo" and sub == "hygiene":
        return _command_repo_hygiene(canonical_root)

    if scope == "/repo" and sub == "clean":
        pin_error = _require_clean_pin(canonical_root)
        if pin_error:
            return pin_error
        return _command_repo_clean(canonical_root)

    if scope == "/repo" and sub == "salvage":
        pin_error = _require_clean_pin(canonical_root)
        if pin_error:
            return pin_error
        return _command_salvage(canonical_root)

    if scope == "/repo" and sub == "apply-salvage":
        pin_error = _require_clean_pin(canonical_root)
        if pin_error:
            return pin_error
        return _command_apply_salvage(canonical_root)

    if scope == "/repo" and sub == "fix":
        pin_error = _require_clean_pin(canonical_root)
        if pin_error:
            return pin_error
        return _command_fix(canonical_root)

    if scope == "/repo" and sub == "keep":
        if len(parts) < 3:
            return _result_error(command, "Usage: /repo keep <candidate_id>")
        return _command_keep(canonical_root, parts[2])

    if scope == "/repo" and sub == "quarantine":
        if len(parts) < 3:
            return _result_error(command, "Usage: /repo quarantine <candidate_id>")
        pin_error = _require_clean_pin(canonical_root)
        if pin_error:
            return pin_error
        return _command_quarantine(canonical_root, parts[2])

    if scope == "/home" and sub == "hygiene":
        return _command_home_hygiene(canonical_root)

    if scope == "/home" and sub == "clean":
        return _command_home_clean(canonical_root)

    if scope == "/brain" and sub == "triage":
        return _command_brain_triage(canonical_root)

    if scope == "/brain" and sub == "plan":
        pin_error = _require_clean_pin(canonical_root)
        if pin_error:
            return pin_error
        return _command_brain_plan(canonical_root)

    if scope == "/brain" and sub == "apply":
        if len(parts) < 3:
            return _result_error(command, "Usage: /brain apply <plan_id>")
        pin_error = _require_clean_pin(canonical_root)
        if pin_error:
            return pin_error
        return _command_brain_apply(canonical_root, parts[2])

    if scope == "/brain" and sub == "status":
        return _command_brain_status(canonical_root)

    if scope == "/autonomy" and sub == "status":
        return _command_autonomy_status(canonical_root)

    if scope == "/autonomy" and sub == "run":
        return _command_autonomy_run(canonical_root)

    if scope == "/autonomy" and sub == "pause":
        hours = 12
        if len(parts) >= 3:
            try:
                hours = max(1, int(parts[2]))
            except ValueError:
                return _result_error(command, "Usage: /autonomy pause <hours>")
        return _command_autonomy_pause(canonical_root, hours)

    if scope == "/autonomy" and sub == "resume":
        return _command_autonomy_resume(canonical_root)

    if scope == "/autonomy" and sub == "last":
        return _command_autonomy_last(canonical_root)

    if scope == "/context" and sub == "surface":
        return _command_context_surface(canonical_root)

    if scope == "/context" and sub == "fix":
        return _command_context_fix(canonical_root)

    if scope == "/context" and sub == "status":
        return _command_context_status(canonical_root)

    if scope == "/memory" and sub == "status":
        return _command_memory_status(canonical_root)

    if scope == "/memory" and sub == "capture":
        text = command.partition("capture")[2].strip()
        return _command_memory_capture(canonical_root, text)

    if scope == "/memory" and sub == "compact":
        return _command_memory_compact(canonical_root)

    if scope == "/memory" and sub == "ask":
        text = command.partition("ask")[2].strip()
        return _command_memory_ask(canonical_root, text)

    if scope == "/inbox" and sub == "status":
        return _command_inbox_status(canonical_root)

    if scope == "/inbox" and sub == "intake":
        return _command_inbox_intake(canonical_root)

    if scope == "/inbox" and sub == "normalize":
        source_id = parts[2].strip() if len(parts) >= 3 else ""
        return _command_inbox_normalize(canonical_root, source_id)

    if scope == "/heartbeat" and sub == "run":
        return _command_heartbeat_run(canonical_root)

    if scope == "/heartbeat" and sub == "status":
        return _command_heartbeat_status(canonical_root)

    if scope == "/runtime" and sub == "status":
        return _command_runtime_status(canonical_root)

    if scope == "/runtime" and sub == "compact":
        return _command_runtime_compact(canonical_root)

    if scope == "/runtime" and sub == "distill":
        return _command_runtime_distill(canonical_root)

    if scope == "/runtime" and sub == "ingest":
        payload = command.partition("ingest")[2].strip()
        return _command_runtime_ingress(canonical_root, payload)

    if scope == "/outbox" and sub == "status":
        return _command_outbox_status(canonical_root)

    if scope == "/outbox" and sub == "deliver":
        return _command_outbox_deliver(canonical_root)

    if scope == "/outbox" and sub == "replay":
        if len(parts) < 3:
            return _result_error(command, "Usage: /outbox replay <batch_id>")
        return _result_error(command, "Replay no implementado aun; usar /outbox deliver para reintentos de pendientes.")

    if scope == "/approvals" and sub == "status":
        return _command_approvals_status(canonical_root)

    if scope == "/discord" and sub == "domains":
        if len(parts) >= 3 and parts[2] == "status":
            return _command_discord_domains_status(canonical_root)
        return _result_error(command, "Usage: /discord domains status")

    if scope == "/sg" and sub == "approve":
        if len(parts) < 3:
            return _result_error(command, "Usage: /sg approve <id>")
        return _command_sg_approve(canonical_root, parts[2])

    return _result_error(
        command,
        "Unknown command. Use /repo roots|setroot|status|doctor|hygiene|clean|salvage|apply-salvage|fix|quarantine|keep, /home hygiene|clean, /brain triage|plan|apply|status, /autonomy status|run|pause|resume|last, /context surface|fix|status, /memory status|capture|compact|ask, /inbox status|intake|normalize, /heartbeat run|status, /runtime status|compact|distill|ingest, /outbox status|deliver|replay <batch_id>, /approvals status, /discord domains status, or /sg approve <id>.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenClaw hook repo commands")
    parser.add_argument(
        "command",
        help="/repo ... | /home hygiene|clean | /brain triage|plan|apply <plan_id>|status | /autonomy status|run|pause <hours>|resume|last | /context surface|fix|status | /memory status|capture <text>|compact|ask <question> | /inbox status|intake|normalize [source_id] | /heartbeat run|status | /runtime status|compact|distill|ingest <event-json|path> | /outbox status|deliver|replay <batch_id> | /approvals status | /discord domains status | /sg approve <id>",
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    result = handle_repo_command(args.command, root=args.root)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())

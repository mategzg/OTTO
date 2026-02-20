#!/usr/bin/env python3
"""Heartbeat delegation engine: scan pending work, build prompt, and delegate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mission_orchestrator import run_emit_prompts as orchestrator_emit_prompts
from scripts.mission_orchestrator import run_init as orchestrator_run_init
from scripts.outbox_queue import enqueue_message, materialized_items
from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/heartbeat_delegation_policy.json")
STATE_PATH = Path("state/heartbeat_delegation_state.json")
PROD_DOCTOR_PATH = Path("docs/_inbox/prod_doctor_latest.json")

RESEARCH_QUEUE = Path("state/research_queue.json")
ODOO_QUEUE = Path("state/odoo_queue.json")
SUMMARIZER_QUEUE = Path("state/summarizer_queue.json")
REMINDERS_QUEUE = Path("state/reminders_queue.json")
MEMORY_INBOX = Path("docs/_inbox/memory_inbox.ndjson")
OUTBOX_QUEUE = Path("docs/_inbox/outbox_queue.ndjson")
HOOK_BACKLOG = Path("state/hook_backlog/events.ndjson")

DEFAULT_POLICY: Dict[str, Any] = {
    "enabled": True,
    "coder_priority": ["codex", "claude_code"],
    "fallback_telegram": True,
    "max_active_delegations": 1,
    "priority_order": ["outbox", "reminders", "hook_backlog", "research", "odoo", "summarizer", "memory", "health"],
    "workload_thresholds": {"light": 5, "medium": 15},
}

DEFAULT_STATE: Dict[str, Any] = {
    "last_delegation_at": None,
    "coder_used": None,
    "items_delegated": 0,
    "status": "no_work",
    "active_mission_id": None,
    "active_workload": None,
    "active_prompt_sha1": None,
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


def _load_json_array(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def _count_ndjson(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            count += 1
    return count


def _ensure_policy(root: Path) -> Dict[str, Any]:
    path = root / POLICY_PATH
    payload = _load_json(path)
    policy = dict(DEFAULT_POLICY)
    policy.update(payload)
    if not path.is_file():
        _save_json(path, policy)
    return policy


def _ensure_state(root: Path) -> Dict[str, Any]:
    path = root / STATE_PATH
    payload = _load_json(path)
    state = dict(DEFAULT_STATE)
    state.update(payload)
    if not path.is_file():
        _save_json(path, state)
    return state


def _pending_by_status(rows: Iterable[Dict[str, Any]], statuses: Iterable[str]) -> List[Dict[str, Any]]:
    wanted = {str(item).strip().lower() for item in statuses}
    out: List[Dict[str, Any]] = []
    for row in rows:
        status = str(row.get("status", "pending")).strip().lower()
        if status in wanted:
            out.append(row)
    return out


def _reminder_due_pending(rows: Iterable[Dict[str, Any]], *, now: datetime) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("status", "")).strip().lower() != "pending":
            continue
        due_raw = str(row.get("deliver_at", "")).strip()
        if not due_raw:
            continue
        try:
            due = datetime.fromisoformat(due_raw)
        except ValueError:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due <= now.astimezone(due.tzinfo):
            out.append(row)
    return out


def scan_pending_work(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    now = datetime.now(timezone.utc)

    research_rows = _load_json_array(canonical_root / RESEARCH_QUEUE)
    odoo_rows = _load_json_array(canonical_root / ODOO_QUEUE)
    summarizer_rows = _load_json_array(canonical_root / SUMMARIZER_QUEUE)
    reminders_rows = _load_json_array(canonical_root / REMINDERS_QUEUE)

    research_pending = _pending_by_status(research_rows, {"pending"})
    odoo_pending = _pending_by_status(odoo_rows, {"pending"})
    summarizer_pending = _pending_by_status(summarizer_rows, {"pending"})
    reminders_due = _reminder_due_pending(reminders_rows, now=now)

    outbox_pending = [
        row
        for row in materialized_items(canonical_root)
        if str(row.get("status", "pending")).strip().lower() in {"pending", "failed_retryable"}
    ]

    prod = _load_json(canonical_root / PROD_DOCTOR_PATH)
    health_degraded = str(prod.get("go_no_go", "go")).strip().lower() != "go"
    health_count = 1 if health_degraded else 0

    pending = {
        "research": {
            "count": len(research_pending),
            "queue_path": RESEARCH_QUEUE.as_posix(),
            "items": [str(row.get("task_id", "")) for row in research_pending[:10]],
        },
        "odoo": {
            "count": len(odoo_pending),
            "queue_path": ODOO_QUEUE.as_posix(),
            "items": [str(row.get("task_id", "")) for row in odoo_pending[:10]],
        },
        "summarizer": {
            "count": len(summarizer_pending),
            "queue_path": SUMMARIZER_QUEUE.as_posix(),
            "items": [str(row.get("id", "")) for row in summarizer_pending[:10]],
        },
        "reminders": {
            "count": len(reminders_due),
            "queue_path": REMINDERS_QUEUE.as_posix(),
            "items": [str(row.get("id", "")) for row in reminders_due[:10]],
        },
        "memory": {
            "count": _count_ndjson(canonical_root / MEMORY_INBOX),
            "queue_path": MEMORY_INBOX.as_posix(),
            "items": [],
        },
        "outbox": {
            "count": len(outbox_pending),
            "queue_path": OUTBOX_QUEUE.as_posix(),
            "items": [str(row.get("id", "")) for row in outbox_pending[:10]],
        },
        "hook_backlog": {
            "count": _count_ndjson(canonical_root / HOOK_BACKLOG),
            "queue_path": HOOK_BACKLOG.as_posix(),
            "items": [],
        },
        "health": {
            "count": health_count,
            "queue_path": PROD_DOCTOR_PATH.as_posix(),
            "items": [str(prod.get("go_no_go", ""))] if health_degraded else [],
        },
    }
    total_pending = sum(int(section.get("count", 0)) for section in pending.values())
    return {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "pending": pending,
        "total_pending": total_pending,
    }


def estimate_workload(pending: Dict[str, Any], *, policy: Dict[str, Any] | None = None) -> str:
    cfg = dict((policy or {}).get("workload_thresholds", {}))
    light_cutoff = int(cfg.get("light", 5))
    medium_cutoff = int(cfg.get("medium", 15))
    total = int(pending.get("total_pending", 0))
    if total <= 0:
        return "none"
    if total <= light_cutoff:
        return "light"
    if total <= medium_cutoff:
        return "medium"
    return "heavy"


def _command_map() -> Dict[str, str]:
    return {
        "reminders": "python3 scripts/reminder_engine.py --process --root .",
        "research": "python3 scripts/research_agent.py --process --root .",
        "odoo": "python3 scripts/odoo_agent.py --process --root .",
        "summarizer": "python3 scripts/session_summarizer.py --process --root .",
        "memory": "python3 scripts/memory_compact.py --root . && python3 scripts/memory_index_build.py --root .",
        "outbox": "python3 scripts/outbox_delivery.py --deliver --root .",
        "hook_backlog": "python3 scripts/hook_backlog.py --replay --root .",
        "health": "python3 scripts/prod_doctor.py --scan --json",
    }


def build_delegation_prompt(root: str | Path, pending: Dict[str, Any], workload: str, *, policy: Dict[str, Any] | None = None) -> str:
    canonical_root = get_canonical_root(root)
    pending_map = pending.get("pending", {})
    priorities = list((policy or {}).get("priority_order", DEFAULT_POLICY["priority_order"]))
    commands = _command_map()
    run_style = "ATOMIC" if workload == "light" else "POTENT"

    lines: List[str] = [
        "ROLE: Coder executor. Evidence required. No fabrication.",
        "ROUTE: CODEX_DEFAULT (CLAUDE_CODE solo si `.claude/*` o runtime/plugins/rules/imports Claude)",
        f"RUN_STYLE: {run_style}",
        "MODE: APPLY",
        f"STOP_AFTER: {'MILESTONE_DONE' if run_style == 'ATOMIC' else 'FINAL_REPORT'}",
        f"ROOT: {canonical_root}",
        "",
        "SCOPE_PATHS:",
        "- scripts/",
        "- state/",
        "- docs/_inbox/",
        "- logs/",
        "- ops/RUN_LEDGER.ndjson",
        "",
        "ALLOWED_EXCEPTIONS:",
        "- docs/_inbox/*latest.json",
        "- docs/_inbox/*latest.md",
        "- logs/*latest.json",
        "- ops/RUN_LEDGER.ndjson",
        "",
        "OBJECTIVE:",
        "Procesar trabajo pendiente de heartbeat con scripts existentes (sin reescribir lógica).",
        "",
        "CONSTRAINTS (HARD):",
        "- NO-FABRICATION: usa solo estado real del repo.",
        "- NO modificar scripts/contratos; solo ejecutar y reportar evidencia.",
        "- SCOPE-BOUND: solo dentro de SCOPE_PATHS (+ ALLOWED_EXCEPTIONS).",
        "- GATE-BEFORE-CLOSE y STOP-ON-FAIL para comandos críticos.",
        "- Prompt authority: no auto-encadenar prompts; next_prompt_ready es draft.",
        "",
        "PENDING WORK SNAPSHOT:",
    ]
    for key in priorities:
        section = pending_map.get(key, {})
        lines.append(
            f"- {key}: count={int(section.get('count', 0))}, queue={section.get('queue_path', '')}, sample={section.get('items', [])[:5]}"
        )

    lines.extend(["", "EXECUTION COMMANDS BY CATEGORY:"])
    for key in priorities:
        lines.append(f"- {key}: `{commands.get(key, 'GAP/NO_VERIFICADO')}`")

    if workload == "light":
        lines.extend(
            [
                "",
                "EXECUTION MODE (ATOMIC):",
                "Ejecuta todo en un solo bloque siguiendo prioridad y reporta qué quedó pendiente.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "EXECUTION MODE (POTENT):",
                "Usa checkpoints por categoría y respeta prioridad: outbox -> reminders -> hook_backlog -> research -> odoo -> summarizer -> memory -> health.",
            ]
        )

    lines.extend(
        [
            "",
            "DONE_CRITERIA:",
            "- [ ] Pendiente total reducido o explicado con GAP verificable.",
            "- [ ] Comandos ejecutados con evidencia exacta.",
            "- [ ] Sin cambios fuera de SCOPE_PATHS/ALLOWED_EXCEPTIONS.",
            "",
            "FAILURE_POLICY:",
            "- Si un comando crítico falla: STOP, reporta output exacto, diagnóstico y fix propuesto.",
            "",
            "OUTPUT_SCHEMA (MUST):",
            "- Devolver UN YAML con `run` + `copilot_packet`.",
            "- `run.allowed_exceptions` MUST existir.",
            "- Si RUN_STYLE=POTENT, incluir `run.checkpoints[]`.",
            "- `copilot_packet` mínimo: current_state, open_issues, approvals_needed, questions_to_user, suggested_next_steps.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _prompt_sha(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()


def _mission_id_for_delegation(coder: str, prompt: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short = hashlib.sha1((coder + "|" + prompt).encode("utf-8")).hexdigest()[:8]
    return f"hbdel_{coder}_{stamp}_{short}"


def _write_delegation_prompt(root: Path, mission_id: str, prompt: str) -> str:
    mission_dir = root / "state" / "missions" / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = mission_dir / "DELEGATION_PROMPT.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path.resolve().relative_to(root.resolve()).as_posix()


def _telegram_fallback(root: Path, pending: Dict[str, Any]) -> Dict[str, Any]:
    summary = []
    for key, section in pending.get("pending", {}).items():
        count = int(section.get("count", 0))
        if count > 0:
            summary.append(f"{key}={count}")
    detail = ", ".join(summary) if summary else "sin detalle"
    text = (
        "⚠️ Heartbeat: no pude delegar trabajo pendiente a ningún coder.\n"
        f"Pendientes: {detail}\n"
        "Acción sugerida: revisar misión de heartbeat y ejecutar colas manualmente."
    )
    queued = enqueue_message(
        root,
        channel="telegram_owner",
        target=os.getenv("TELEGRAM_CHAT_ID", "").strip() or "owner",
        text=text,
        purpose="heartbeat_delegation_fallback",
        source_ref="scripts/heartbeat_delegator.py",
        metadata={"kind": "heartbeat_delegation_fallback", "pending_total": int(pending.get("total_pending", 0))},
    )
    return {"status": "fallback_telegram", "queued": queued}


def delegate_to_coder(
    root: str | Path,
    prompt: str,
    *,
    pending: Dict[str, Any],
    workload: str,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    cfg = dict(_ensure_policy(canonical_root))
    if isinstance(policy, dict):
        cfg.update(policy)
    state = _ensure_state(canonical_root)

    max_active = max(1, int(cfg.get("max_active_delegations", 1)))
    active_mission_id = str(state.get("active_mission_id") or "").strip()
    if active_mission_id and max_active <= 1:
        return {
            "status": "delegation_in_progress",
            "coder_used": state.get("coder_used"),
            "active_mission_id": active_mission_id,
            "items_delegated": int(state.get("items_delegated", 0)),
        }

    total = int(pending.get("total_pending", 0))
    if total <= 0:
        state.update(
            {
                "last_delegation_at": _utc_now(),
                "coder_used": None,
                "items_delegated": 0,
                "status": "no_work",
                "active_mission_id": None,
                "active_workload": workload,
                "active_prompt_sha1": _prompt_sha(prompt),
            }
        )
        _save_json(canonical_root / STATE_PATH, state)
        return {"status": "no_work", "items_delegated": 0}

    for coder in [str(item).strip() for item in cfg.get("coder_priority", []) if str(item).strip()]:
        mission_id = _mission_id_for_delegation(coder, prompt)
        try:
            init = orchestrator_run_init(
                canonical_root,
                title=f"[heartbeat_delegation][coder={coder}] procesar colas pendientes",
                channel="telegram",
                peer_id=f"coder_{coder}",
                thread_id="heartbeat_delegation",
                size="S" if workload == "light" else "M",
                mission_id=mission_id,
            )
            orchestrator_emit_prompts(canonical_root, mission_id=mission_id)
            prompt_rel = _write_delegation_prompt(canonical_root, mission_id, prompt)
            state.update(
                {
                    "last_delegation_at": _utc_now(),
                    "coder_used": coder,
                    "items_delegated": total,
                    "status": "delegated",
                    "active_mission_id": mission_id,
                    "active_workload": workload,
                    "active_prompt_sha1": _prompt_sha(prompt),
                    "active_prompt_path": prompt_rel,
                }
            )
            _save_json(canonical_root / STATE_PATH, state)
            return {
                "status": "delegated",
                "coder_used": coder,
                "active_mission_id": mission_id,
                "items_delegated": total,
                "mission_paths": init.get("report", {}).get("mission_paths", {}),
                "prompt_path": prompt_rel,
            }
        except Exception as exc:
            continue

    if bool(cfg.get("fallback_telegram", True)):
        fallback = _telegram_fallback(canonical_root, pending)
        state.update(
            {
                "last_delegation_at": _utc_now(),
                "coder_used": "telegram_owner",
                "items_delegated": total,
                "status": "fallback_telegram",
                "active_mission_id": None,
                "active_workload": workload,
                "active_prompt_sha1": _prompt_sha(prompt),
            }
        )
        _save_json(canonical_root / STATE_PATH, state)
        return {"status": "fallback_telegram", "coder_used": "telegram_owner", "items_delegated": total, **fallback}

    state.update(
        {
            "last_delegation_at": _utc_now(),
            "coder_used": None,
            "items_delegated": total,
            "status": "failed_no_fallback",
            "active_mission_id": None,
            "active_workload": workload,
            "active_prompt_sha1": _prompt_sha(prompt),
        }
    )
    _save_json(canonical_root / STATE_PATH, state)
    return {"status": "failed_no_fallback", "items_delegated": total}


def check_completed_delegations(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = _ensure_state(canonical_root)
    mission_id = str(state.get("active_mission_id") or "").strip()
    if not mission_id:
        return {"status": "no_active_delegation", "active": False}

    mission_json = canonical_root / "state" / "missions" / mission_id / "mission.json"
    mission = _load_json(mission_json)
    mission_status = str(mission.get("status", "")).strip().lower()
    completed = mission_status == "completed"

    if not completed:
        pending_drop = canonical_root / "vault" / "inbox_raw" / "_pending_drop"
        if pending_drop.is_dir():
            for child in pending_drop.iterdir():
                if mission_id in child.name:
                    completed = True
                    break

    if completed:
        state.update(
            {
                "status": "completed",
                "active_mission_id": None,
            }
        )
        _save_json(canonical_root / STATE_PATH, state)
        return {"status": "completed", "active": False, "mission_id": mission_id}
    return {"status": "delegation_in_progress", "active": True, "mission_id": mission_id}


def load_policy(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    return _ensure_policy(canonical_root)


def load_state(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    return _ensure_state(canonical_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Heartbeat delegation helper")
    parser.add_argument("--root", default=".")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--delegate", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    canonical_root = get_canonical_root(args.root)
    policy = _ensure_policy(canonical_root)
    out: Dict[str, Any]
    if args.check:
        out = check_completed_delegations(canonical_root)
    elif args.scan:
        pending = scan_pending_work(canonical_root)
        out = {"status": "ok", "pending": pending, "workload": estimate_workload(pending, policy=policy)}
    elif args.delegate:
        pending = scan_pending_work(canonical_root)
        workload = estimate_workload(pending, policy=policy)
        prompt = build_delegation_prompt(canonical_root, pending, workload, policy=policy)
        out = delegate_to_coder(canonical_root, prompt, pending=pending, workload=workload, policy=policy)
    else:
        parser.error("Use --scan or --delegate or --check")
        return 2

    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

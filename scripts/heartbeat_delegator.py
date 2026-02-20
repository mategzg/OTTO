#!/usr/bin/env python3
"""Heartbeat delegation engine: scan pending work, build prompt, and delegate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
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
PENDING_DROP = Path("vault/inbox_raw/_pending_drop")
SOURCES_ROOT = Path("vault/inbox_raw/sources")
INGEST_PLAN_ROOT = Path("state/ingest_plans")
TRIAGE_REPORT_PATH = Path("docs/_inbox/corpus_triage_latest.json")

_INGEST_PENDING_EXCLUDED_PREFIXES = (
    "mission_learning",
    "research",
    "legacy_recovery",
    "_legacy_recovery",
)
_INGEST_PENDING_EXCLUDED_EXACT = {"_ingested", "processed"}

DEFAULT_POLICY: Dict[str, Any] = {
    "enabled": True,
    "coder_priority": ["codex", "claude_code"],
    "fallback_telegram": True,
    "max_active_delegations": 1,
    "stale_delegation_minutes": 45,
    "priority_order": ["outbox", "reminders", "ingest", "hook_backlog", "research", "odoo", "summarizer", "memory", "health"],
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
    "ingest_progress": {
        "total_packages_detected": 0,
        "packages_processed": 0,
        "packages_remaining": 0,
        "last_batch_at": None,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc(ts: Any) -> datetime | None:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc)


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


def _is_pending_drop_candidate(name: str) -> bool:
    low = name.strip().lower()
    if not low:
        return False
    if low.startswith("."):
        return False
    if low in _INGEST_PENDING_EXCLUDED_EXACT:
        return False
    return not any(low.startswith(prefix) for prefix in _INGEST_PENDING_EXCLUDED_PREFIXES)


def _ingest_pending_packages(root: Path) -> Dict[str, Any]:
    pending_root = root / PENDING_DROP
    if not pending_root.is_dir():
        return {"count": 0, "items": []}
    items: List[str] = []
    for item in sorted(pending_root.iterdir(), key=lambda p: p.name):
        if not (item.is_file() or item.is_dir()):
            continue
        if not _is_pending_drop_candidate(item.name):
            continue
        items.append(item.name)
    return {"count": len(items), "items": items[:20]}


def _iter_source_dirs(root: Path) -> List[Path]:
    sources_root = root / SOURCES_ROOT
    if not sources_root.is_dir():
        return []
    out: List[Path] = []
    for item in sorted(sources_root.iterdir(), key=lambda p: p.name):
        if item.is_dir() and (item / "source").exists():
            out.append(item)
    return out


def _normalized_sources_pending(root: Path) -> Dict[str, Any]:
    pending: List[str] = []
    for source_dir in _iter_source_dirs(root):
        hints = _load_json(source_dir / "HINTS.json")
        normalize_status = str(hints.get("normalize_status", "")).strip().lower()
        if normalize_status == "ok" and (source_dir / "normalized" / "messages.ndjson").is_file():
            continue
        pending.append(source_dir.resolve().relative_to(root.resolve()).as_posix())
    return {"count": len(pending), "items": pending[:20]}


def _source_root_rel_from_ref(root: Path, raw_ref: str) -> str:
    text = str(raw_ref or "").strip()
    if not text:
        return ""
    ref_path = Path(text)
    if not ref_path.is_absolute():
        candidate = (root / ref_path).resolve()
    else:
        candidate = ref_path.resolve()
    try:
        rel = candidate.relative_to(root.resolve()).as_posix()
    except Exception:
        return ""
    needle = "vault/inbox_raw/sources/"
    if needle not in rel:
        return ""
    tail = rel.split(needle, 1)[1]
    if not tail:
        return ""
    source_name = tail.split("/", 1)[0]
    if not source_name:
        return ""
    return f"{needle}{source_name}"


def _triage_pending_sources(root: Path) -> Dict[str, Any]:
    normalized_sources = []
    for source_dir in _iter_source_dirs(root):
        hints = _load_json(source_dir / "HINTS.json")
        status = str(hints.get("normalize_status", "")).strip().lower()
        if status != "ok":
            continue
        normalized_sources.append(source_dir.resolve().relative_to(root.resolve()).as_posix())

    triage = _load_json(root / TRIAGE_REPORT_PATH)
    triaged_roots: set[str] = set()
    for row in triage.get("sources", []):
        if not isinstance(row, dict):
            continue
        parent_rel = _source_root_rel_from_ref(root, str(row.get("parent_source_rel", "")))
        if parent_rel:
            triaged_roots.add(parent_rel)
        for key in ("source_path", "inbox_rel_path"):
            rel = _source_root_rel_from_ref(root, str(row.get(key, "")))
            if rel:
                triaged_roots.add(rel)

    pending = [rel for rel in normalized_sources if rel not in triaged_roots]
    return {"count": len(pending), "items": pending[:20]}


def _apply_pending_plans(root: Path) -> Dict[str, Any]:
    plan_root = root / INGEST_PLAN_ROOT
    if not plan_root.is_dir():
        return {"count": 0, "items": []}
    pending_plans: List[str] = []
    inbox_root = root / "vault" / "inbox_raw"
    for plan_file in sorted(plan_root.glob("*.json"), key=lambda p: p.name):
        plan = _load_json(plan_file)
        if str(plan.get("status", "")).strip().lower() != "ok":
            continue
        sources = plan.get("sources", [])
        if not isinstance(sources, list):
            continue
        unresolved = False
        for source in sources:
            if not isinstance(source, dict):
                continue
            inbox_rel = str(source.get("inbox_rel_path", "")).strip()
            if inbox_rel and (inbox_root / inbox_rel).exists():
                unresolved = True
                break
        if unresolved:
            pending_plans.append(str(plan.get("plan_id", plan_file.stem)))
    return {"count": len(pending_plans), "items": pending_plans[:20]}


def _compute_ingest_progress(existing: Dict[str, Any], pending: Dict[str, Any], *, stamp: str | None = None) -> Dict[str, Any]:
    base = dict(DEFAULT_STATE["ingest_progress"])
    if isinstance(existing, dict):
        base.update({k: existing.get(k) for k in base.keys()})
    # Track full ingest backlog (drop + normalize + triage + apply), not only pending_drop.
    remaining = int(pending.get("pending", {}).get("ingest", {}).get("count", 0))
    processed_prev = max(0, int(base.get("packages_processed", 0)))
    total_prev = max(0, int(base.get("total_packages_detected", 0)))
    total = max(total_prev, processed_prev + remaining)
    processed = max(processed_prev, total - remaining)
    return {
        "total_packages_detected": total,
        "packages_processed": processed,
        "packages_remaining": remaining,
        "last_batch_at": stamp or base.get("last_batch_at"),
    }


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
    ingest_progress = state.get("ingest_progress")
    if not isinstance(ingest_progress, dict):
        ingest_progress = {}
    merged_progress = dict(DEFAULT_STATE["ingest_progress"])
    merged_progress.update({k: ingest_progress.get(k) for k in merged_progress.keys()})
    state["ingest_progress"] = merged_progress
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
    ingest_pending = _ingest_pending_packages(canonical_root)
    ingest_normalize = _normalized_sources_pending(canonical_root)
    ingest_triage = _triage_pending_sources(canonical_root)
    ingest_apply = _apply_pending_plans(canonical_root)
    ingest_count = max(
        int(ingest_pending.get("count", 0)),
        int(ingest_normalize.get("count", 0)),
        int(ingest_triage.get("count", 0)),
        int(ingest_apply.get("count", 0)),
    )

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
        "ingest": {
            "count": ingest_count,
            "queue_path": PENDING_DROP.as_posix(),
            "items": list(ingest_pending.get("items", []))[:10],
            "details": {
                "pending_drop": ingest_pending,
                "normalize_pending": ingest_normalize,
                "triage_pending": ingest_triage,
                "apply_pending": ingest_apply,
            },
        },
        "ingest_pending": {
            "count": int(ingest_pending.get("count", 0)),
            "queue_path": PENDING_DROP.as_posix(),
            "items": list(ingest_pending.get("items", []))[:10],
        },
        "ingest_normalize": {
            "count": int(ingest_normalize.get("count", 0)),
            "queue_path": SOURCES_ROOT.as_posix(),
            "items": list(ingest_normalize.get("items", []))[:10],
        },
        "ingest_triage": {
            "count": int(ingest_triage.get("count", 0)),
            "queue_path": TRIAGE_REPORT_PATH.as_posix(),
            "items": list(ingest_triage.get("items", []))[:10],
        },
        "ingest_apply": {
            "count": int(ingest_apply.get("count", 0)),
            "queue_path": INGEST_PLAN_ROOT.as_posix(),
            "items": list(ingest_apply.get("items", []))[:10],
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
    primary_total_keys = ["outbox", "reminders", "ingest", "hook_backlog", "research", "odoo", "summarizer", "memory", "health"]
    total_pending = sum(int(pending.get(key, {}).get("count", 0)) for key in primary_total_keys)
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
        "ingest": "python3 scripts/dropbox_intake.py --apply --root .",
        "research": "python3 scripts/research_agent.py --root .",
        "odoo": "python3 scripts/odoo_agent.py --root .",
        "summarizer": "python3 scripts/session_summarizer.py --root .",
        "memory": "python3 scripts/memory_compact.py --apply --root . && python3 scripts/memory_index_build.py --root .",
        "outbox": "python3 scripts/outbox_delivery.py --deliver --root .",
        "hook_backlog": "python3 scripts/hook_backlog.py --replay --root .",
        "health": "python3 scripts/prod_doctor.py --scan --json",
    }


def _ingest_command_block() -> List[str]:
    return [
        "python3 scripts/dropbox_intake.py --apply --root .",
        "python3 scripts/chatgpt_export_normalize.py --root .",
        "python3 scripts/corpus_triage.py --root .",
        "python3 scripts/brain_ingest_router.py --plan --root .",
        "PLAN_ID=$(python3 - <<'PY'\nimport json, pathlib\np=pathlib.Path('docs/_inbox/corpus_assimilation_plan_latest.json')\nplan=json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}\nprint(plan.get('plan_id',''))\nPY\n)",
        "if [ -n \"$PLAN_ID\" ]; then python3 scripts/brain_ingest_router.py --apply \"$PLAN_ID\" --root .; fi",
        "python3 scripts/write_router.py --root .",
        "python3 scripts/brain_index_build.py --root .",
        "python3 scripts/memory_compact.py --apply --root .",
        "python3 scripts/memory_index_build.py --root .",
    ]


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
        if key == "ingest":
            ingest_count = int(pending_map.get("ingest", {}).get("count", 0))
            if ingest_count <= 0:
                lines.append("- ingest: `NO_PENDING_INGEST`")
            else:
                lines.append("- ingest:")
                for cmd in _ingest_command_block():
                    lines.append(f"  - `{cmd}`")
            continue
        lines.append(f"- {key}: `{commands.get(key, 'GAP/NO_VERIFICADO')}`")

    ingest_count = int(pending_map.get("ingest", {}).get("count", 0))
    if ingest_count > 0:
        lines.extend(
            [
                "",
                "INGEST BATCH RULES:",
                "- Ejecutar pipeline de ingest en orden.",
                "- Si el volumen excede limites por corrida, procesar solo el batch permitido y reportar remanente.",
                "- El siguiente heartbeat delegara automaticamente el siguiente batch mientras queden paquetes en `vault/inbox_raw/_pending_drop/`.",
                "- Evidencia obligatoria: paquetes procesados, errores, categorias aplicadas, pendientes restantes.",
            ]
        )

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
    state["ingest_progress"] = _compute_ingest_progress(state.get("ingest_progress", {}), pending)

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
        state["ingest_progress"] = _compute_ingest_progress(state.get("ingest_progress", {}), pending, stamp=_utc_now())
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
            state["ingest_progress"] = _compute_ingest_progress(state.get("ingest_progress", {}), pending, stamp=_utc_now())
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
        state["ingest_progress"] = _compute_ingest_progress(state.get("ingest_progress", {}), pending, stamp=_utc_now())
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
    state["ingest_progress"] = _compute_ingest_progress(state.get("ingest_progress", {}), pending, stamp=_utc_now())
    _save_json(canonical_root / STATE_PATH, state)
    return {"status": "failed_no_fallback", "items_delegated": total}


def check_completed_delegations(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = _ensure_state(canonical_root)
    policy = _ensure_policy(canonical_root)
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
        rescanned = scan_pending_work(canonical_root)
        state.update(
            {
                "status": "completed",
                "active_mission_id": None,
            }
        )
        state["ingest_progress"] = _compute_ingest_progress(state.get("ingest_progress", {}), rescanned, stamp=_utc_now())
        _save_json(canonical_root / STATE_PATH, state)
        return {
            "status": "completed",
            "active": False,
            "mission_id": mission_id,
            "ingest_progress": state.get("ingest_progress", {}),
            "remaining_pending": int(rescanned.get("total_pending", 0)),
        }

    # stale-lock guard: if a delegation stays active too long without explicit completion,
    # release the lock so heartbeat can redelegate in the next cycle.
    stale_minutes = max(5, int(policy.get("stale_delegation_minutes", 45)))
    now_utc = datetime.now(timezone.utc)
    stamp_candidates = [
        _parse_utc(state.get("last_delegation_at")),
        _parse_utc(mission.get("updated_at")),
        _parse_utc(mission.get("created_at")),
    ]
    latest_ref = max((dt for dt in stamp_candidates if dt is not None), default=None)
    if latest_ref and now_utc - latest_ref >= timedelta(minutes=stale_minutes):
        state.update(
            {
                "status": "stale_reset",
                "active_mission_id": None,
            }
        )
        _save_json(canonical_root / STATE_PATH, state)
        return {
            "status": "stale_reset",
            "active": False,
            "mission_id": mission_id,
            "stale_minutes": stale_minutes,
            "last_activity_utc": latest_ref.isoformat(),
        }

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

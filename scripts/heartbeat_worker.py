#!/usr/bin/env python3
"""Passive heartbeat worker: intake -> normalize -> runtime -> outbox -> autonomy tick."""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.autonomy_tick import run_autonomy_tick
from scripts.approval_manager import process_pending_approvals
from scripts.chatgpt_export_normalize import run_normalize
from scripts.circuit_breaker import should_allow
from scripts.day2_doc_inventory import run_day2_inventory_sync
from scripts.dropbox_intake import run_apply as run_intake_apply
from scripts.dropbox_intake import run_scan as run_intake_scan
try:
    from scripts.episodic_memory_builder import run_build as run_episodic_memory_builder
except Exception:  # pragma: no cover - optional integration
    def run_episodic_memory_builder(*_args, **_kwargs):
        return {"status": "unavailable", "episodes_built": 0, "index_size_bytes": 0}
from scripts.hook_backlog import run_replay as run_hook_backlog_replay
from scripts.hook_backlog import run_scan as run_hook_backlog_scan
from scripts.heartbeat_delegator import (
    build_delegation_prompt,
    check_completed_delegations,
    delegate_to_coder,
    estimate_workload,
    load_policy as load_delegation_policy,
    load_state as load_delegation_state,
    scan_pending_work,
)
from scripts.legacy_recovery_worker import run_once as run_legacy_recovery_once
try:
    from scripts.learning_promoter import run_promoter as run_learning_promoter
except Exception:  # pragma: no cover - optional integration
    def run_learning_promoter(*_args, **_kwargs):
        return {"report": {"status": "unavailable", "summary": {"promoted_count": 0, "candidate_files_processed": 0}}}
try:
    from scripts.odoo_agent import run_odoo as run_odoo_agent
except Exception:  # pragma: no cover - optional integration
    def run_odoo_agent(*_args, **_kwargs):
        return {"status": "unavailable", "tasks_processed": 0, "tasks_done": 0, "tasks_failed": 0}
from scripts.outbox_delivery import run_deliver as run_outbox_deliver
from scripts.outbox_queue import enqueue_message, materialized_items
try:
    from scripts.proactivity_engine import queue_topic_alert, run_proactivity
except Exception:  # pragma: no cover - optional integration
    def queue_topic_alert(*_args, **_kwargs):
        return {"queued": False, "reason": "proactivity_engine_unavailable"}

    def run_proactivity(*_args, **_kwargs):
        return {"report": {"status": "unavailable", "summary": {"queued_count": 0}}}
try:
    from scripts.reminder_engine import process_reminders as run_reminder_engine
except Exception:  # pragma: no cover - optional integration
    def run_reminder_engine(*_args, **_kwargs):
        return {"delivered": 0, "expired": 0, "pending": 0}
try:
    from scripts.research_agent import run_research_stage
except Exception:  # pragma: no cover - optional integration
    def run_research_stage(*_args, **_kwargs):
        return {"status": "unavailable", "tasks_processed": 0, "tasks_done": 0, "tasks_failed": 0}
from scripts.prod_doctor import run_prod_doctor
from scripts.project_docs_maintainer import run_apply as run_project_docs_apply
from scripts.repo_root import get_canonical_root
from scripts.safety_switch import autopause_switch, get_safety_status, load_policy as load_safety_policy
try:
    from scripts.session_summarizer import run_stage as run_session_summarizer_stage
except Exception:  # pragma: no cover - optional integration
    def run_session_summarizer_stage(*_args, **_kwargs):
        return {"status": "unavailable", "check": {"added": 0, "pending": 0}, "create": {"created": 0, "fallback": 0}, "ingest": {"done": 0}}
from scripts.session_memory_manager import run_session_maintenance
from scripts.sg_promotion import process_promotions
from scripts.whatsapp_budget_guard import refresh_usage_state as refresh_whatsapp_usage_state
from scripts.whatsapp_budget_guard import release_hold_queue as release_whatsapp_hold_queue

# Backward-compatible alias used by existing tests/patches.
run_research_agent = run_research_stage

POLICY_PATH = Path("state/heartbeat_policy.json")
LOCK_PATH = Path("state/heartbeat_worker.lock")
AUTONOMY_STATE_PATH = Path("state/autonomy_state.json")

REPORT_JSON = Path("docs/_inbox/heartbeat_latest.json")
REPORT_MD = Path("docs/_inbox/heartbeat_latest.md")
REPORT_LOG = Path("logs/heartbeat_latest.json")
OUTBOX_ARCHIVE_DIR = Path("docs/_inbox/outbox_queue")

DEFAULT_POLICY = {
    "version": 1,
    "interval_minutes": 30,
    "max_sources_per_heartbeat": 2,
    "max_apply_ops_per_heartbeat": 10,
    "max_outbox_items_per_heartbeat": 20,
    "max_outbox_chars_per_item": 4000,
    "max_hook_backlog_events_per_heartbeat": 25,
    "max_hook_backlog_runtime_seconds": 20,
    "run_legacy_recovery": True,
    "legacy_recovery_force": False,
    "run_project_docs_maintainer": True,
    "run_prod_doctor": True,
    "max_sessions_per_tick": 12,
    "max_compactions_per_tick": 8,
    "max_distill_per_tick": 4,
    "max_runtime_seconds": 300,
    "failure_backoff_minutes": 30,
    "max_consecutive_failures_before_pause": 3,
}
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _cleanup_old_token_records(root: Path, days: int = 7) -> None:
    path = root / "state" / "token_usage_estimate.json"
    if not path.is_file():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_text = str(row.get("ts", "")).strip()
        try:
            ts = datetime.fromisoformat(ts_text)
        except ValueError:
            continue
        if ts >= cutoff:
            kept.append(json.dumps(row, sort_keys=True, ensure_ascii=False))
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def _cleanup_outbox_archives(root: Path, days: int = 7) -> Dict[str, int]:
    archive_root = root / OUTBOX_ARCHIVE_DIR
    if not archive_root.is_dir():
        return {"removed_files": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    removed = 0
    for item in archive_root.rglob("*"):
        if not item.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                item.unlink()
                removed += 1
            except OSError:
                continue
    for directory in sorted(archive_root.rglob("*"), reverse=True):
        if directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                continue
    return {"removed_files": removed}


def _count_ndjson_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _count_json_queue_pending(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(payload, list):
        pending = 0
        for row in payload:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status", "pending")).strip().lower()
            if status in {"pending", "running"}:
                pending += 1
        return pending
    return 0


def _build_pending_snapshot(root: Path) -> Dict[str, Any]:
    paths = {
        "research_queue": root / "state" / "research_queue.json",
        "odoo_queue": root / "state" / "odoo_queue.json",
        "memory_inbox": root / "docs" / "_inbox" / "memory_inbox.ndjson",
        "outbox_queue": root / "docs" / "_inbox" / "outbox_queue.ndjson",
        "reminders_queue": root / "state" / "reminders_queue.json",
        "hook_backlog_events": root / "state" / "hook_backlog" / "events.ndjson",
    }
    file_sizes = {name: (path.stat().st_size if path.is_file() else 0) for name, path in paths.items()}
    outbox_pending = 0
    for row in materialized_items(root):
        status = str(row.get("status", "pending")).strip().lower()
        if status in {"pending", "failed_retryable"}:
            outbox_pending += 1
    pending = {
        "research_pending": _count_json_queue_pending(paths["research_queue"]),
        "odoo_pending": _count_json_queue_pending(paths["odoo_queue"]),
        "memory_inbox_pending": _count_ndjson_lines(paths["memory_inbox"]),
        "outbox_pending": outbox_pending,
        "reminders_pending": _count_json_queue_pending(paths["reminders_queue"]),
        "hook_backlog_pending": _count_ndjson_lines(paths["hook_backlog_events"]),
    }
    total_pending = sum(int(value) for value in pending.values())
    return {"file_sizes": file_sizes, "pending": pending, "total_pending": total_pending}


def _load_policy(root: Path) -> Dict[str, Any]:
    path = root / POLICY_PATH
    policy = dict(DEFAULT_POLICY)
    policy.update(_load_json(path))
    if not path.is_file():
        _save_json(path, policy)
    return policy


def _acquire_lock(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    return True


def _release_lock(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _pending_drop_count(root: Path) -> int:
    pending = root / "vault" / "inbox_raw" / "_pending_drop"
    if not pending.is_dir():
        return 0
    count = 0
    for item in pending.iterdir():
        if item.name == "_ingested" or item.name.startswith("."):
            continue
        if item.is_file() or item.is_dir():
            count += 1
    return count


def _mission_learning_pending_count(root: Path) -> int:
    mission_root = root / "vault" / "inbox_raw" / "_pending_drop" / "mission_learning"
    if not mission_root.is_dir():
        return 0
    count = 0
    for item in mission_root.iterdir():
        if item.name.startswith("."):
            continue
        if item.is_file() or item.is_dir():
            count += 1
    return count


def _run_ingest_rescue(root: Path) -> Dict[str, Any]:
    """Inline rescue when delegation is active but ingest backlog remains stuck."""
    steps: list[dict[str, Any]] = []

    def _run(cmd: str) -> tuple[int, str]:
        proc = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True)
        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return proc.returncode, output.strip()

    for cmd in [
        "python3 scripts/corpus_triage.py --root .",
        "python3 scripts/brain_ingest_router.py --plan --root .",
    ]:
        rc, out = _run(cmd)
        steps.append({"command": cmd, "code": rc, "output": out[-800:]})
        if rc != 0:
            return {"status": "failed", "steps": steps}

    plan_id = ""
    plan_path = root / "docs" / "_inbox" / "corpus_assimilation_plan_latest.json"
    if plan_path.is_file():
        try:
            plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_id = str(plan_payload.get("plan_id", "")).strip()
        except Exception:
            plan_id = ""
    if not plan_id:
        return {"status": "no_plan", "steps": steps}

    cmd = f"python3 scripts/brain_ingest_router.py --apply {plan_id} --root ."
    rc, out = _run(cmd)
    steps.append({"command": cmd, "code": rc, "output": out[-800:]})
    if rc != 0:
        return {"status": "failed", "steps": steps, "plan_id": plan_id}

    cmd = "python3 scripts/write_router.py --root ."
    rc, out = _run(cmd)
    steps.append({"command": cmd, "code": rc, "output": out[-800:]})
    if rc != 0:
        return {"status": "failed", "steps": steps, "plan_id": plan_id}

    return {"status": "success", "steps": steps, "plan_id": plan_id}


def run_heartbeat_once(root: str | Path, *, force: bool = False) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    lock = canonical_root / LOCK_PATH

    if not _acquire_lock(lock):
        report = {
            "canonical_root": str(canonical_root.resolve()),
            "created_at": _utc_now().isoformat(),
            "status": "locked",
            "summary": {"reason": "heartbeat lock exists"},
            "version": 1,
        }
        _save_json(canonical_root / REPORT_JSON, report)
        _save_json(canonical_root / REPORT_LOG, report)
        (canonical_root / REPORT_MD).write_text("# Heartbeat Latest\n\n- Status: `locked`\n", encoding="utf-8")
        return {"report": report, "paths": {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()}}

    try:
        now = _utc_now()
        safety_status = get_safety_status(canonical_root, auto_expire=True)
        safety_policy = load_safety_policy(canonical_root)
        autonomy_state_path = canonical_root / AUTONOMY_STATE_PATH
        autonomy_state = _load_json(autonomy_state_path)
        last_run_iso = str(autonomy_state.get("heartbeat_last_run_utc", ""))
        if last_run_iso:
            try:
                last_run = datetime.fromisoformat(last_run_iso)
            except ValueError:
                last_run = None
        else:
            last_run = None

        interval_minutes = max(1, int(policy.get("interval_minutes", 30)))
        if safety_status.get("paused", False):
            outbox_delivery = run_outbox_deliver(
                canonical_root,
                max_items_per_run=max(1, int(policy.get("max_outbox_items_per_heartbeat", 20))),
                max_chars_per_item=max(200, int(policy.get("max_outbox_chars_per_item", 4000))),
                max_runtime_seconds=max(5, int(policy.get("max_runtime_seconds", 300) // 3)),
            )
            report = {
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "status": "paused_safety",
                "summary": {
                    "reason": str(safety_status.get("reason", "safety_switch_paused")),
                    "paused_until": str(safety_status.get("until_ts", "")),
                    "pending_drop_count": _pending_drop_count(canonical_root),
                    "outbox_queued": int(outbox_delivery["report"].get("summary", {}).get("queue_pending", 0)),
                    "outbox_delivered": int(outbox_delivery["report"].get("summary", {}).get("delivered_in_run", 0)),
                    "outbox_failed": int(outbox_delivery["report"].get("summary", {}).get("failed_in_run", 0)),
                },
                "safety_status": safety_status,
                "outbox_delivery_summary": outbox_delivery["report"].get("summary", {}),
                "version": 1,
            }
            _save_json(canonical_root / REPORT_JSON, report)
            _save_json(canonical_root / REPORT_LOG, report)
            (canonical_root / REPORT_MD).write_text(
                "# Heartbeat Latest\n\n"
                "- Status: `paused_safety`\n"
                f"- Reason: `{report['summary']['reason']}`\n"
                f"- Paused until: `{report['summary']['paused_until']}`\n",
                encoding="utf-8",
            )
            return {"report": report, "paths": {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()}}

        if not force and last_run and (now - last_run) < timedelta(minutes=interval_minutes):
            report = {
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "status": "skipped_interval",
                "summary": {
                    "interval_minutes": interval_minutes,
                    "last_run_utc": last_run_iso,
                    "pending_drop_count": _pending_drop_count(canonical_root),
                },
                "version": 1,
            }
            _save_json(canonical_root / REPORT_JSON, report)
            _save_json(canonical_root / REPORT_LOG, report)
            (canonical_root / REPORT_MD).write_text(
                "# Heartbeat Latest\n\n"
                f"- Status: `skipped_interval`\n"
                f"- Last run: `{last_run_iso}`\n"
                f"- Interval minutes: {interval_minutes}\n",
                encoding="utf-8",
            )
            return {"report": report, "paths": {"json": REPORT_JSON.as_posix(), "markdown": REPORT_MD.as_posix(), "log": REPORT_LOG.as_posix()}}

        pending_snapshot = _build_pending_snapshot(canonical_root)
        if not force and int(pending_snapshot.get("total_pending", 0)) == 0:
            report = {
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "status": "no_pending_work",
                "summary": {
                    "no_pending_work": True,
                    "pending_drop_count": _pending_drop_count(canonical_root),
                    "mission_learning_pending_count": _mission_learning_pending_count(canonical_root),
                    **pending_snapshot.get("pending", {}),
                },
                "pending_snapshot": pending_snapshot,
                "version": 1,
            }
            autonomy_state["heartbeat_last_run_utc"] = now.isoformat()
            autonomy_state["heartbeat_last_status"] = "no_pending_work"
            autonomy_state["heartbeat_last_report"] = REPORT_JSON.as_posix()
            _save_json(autonomy_state_path, autonomy_state)
            _save_json(canonical_root / REPORT_JSON, report)
            _save_json(canonical_root / REPORT_LOG, report)
            (canonical_root / REPORT_MD).write_text(
                "# Heartbeat Latest\n\n"
                "- Status: `no_pending_work`\n"
                f"- Pending snapshot total: {pending_snapshot.get('total_pending', 0)}\n",
                encoding="utf-8",
            )
            return {
                "report": report,
                "paths": {
                    "json": REPORT_JSON.as_posix(),
                    "markdown": REPORT_MD.as_posix(),
                    "log": REPORT_LOG.as_posix(),
                    "policy": POLICY_PATH.as_posix(),
                },
            }

        reminders = run_reminder_engine(canonical_root)
        outbox_delivery = run_outbox_deliver(
            canonical_root,
            max_items_per_run=max(1, int(policy.get("max_outbox_items_per_heartbeat", 20))),
            max_chars_per_item=max(200, int(policy.get("max_outbox_chars_per_item", 4000))),
            max_runtime_seconds=max(5, int(policy.get("max_runtime_seconds", 300) // 3)),
        )
        whatsapp_usage = refresh_whatsapp_usage_state(canonical_root)
        whatsapp_release = release_whatsapp_hold_queue(canonical_root, max_events=50)

        project_docs = {"report": {"status": "disabled", "updated_files": [], "paths": {}}}
        if bool(policy.get("run_project_docs_maintainer", True)):
            project_docs = run_project_docs_apply(canonical_root)

        day2_inventory = run_day2_inventory_sync(canonical_root)

        hook_backlog_scan = run_hook_backlog_scan(canonical_root)
        prod_doctor = {"report": {"status": "disabled", "summary": {}, "go_no_go": "go"}}
        if bool(policy.get("run_prod_doctor", True)):
            prod_doctor = run_prod_doctor(canonical_root, force=False)

        breaker_gates = {
            "cron_jobs": should_allow(canonical_root, resource="cron_jobs"),
            "tooling": should_allow(canonical_root, resource="tooling"),
            "retrieval": should_allow(canonical_root, resource="retrieval"),
        }

        delegation_policy = load_delegation_policy(canonical_root)
        delegation_completion = check_completed_delegations(canonical_root)
        delegation_pending = scan_pending_work(canonical_root)
        delegation_workload = estimate_workload(delegation_pending, policy=delegation_policy)
        delegation_prompt = build_delegation_prompt(
            canonical_root,
            delegation_pending,
            delegation_workload,
            policy=delegation_policy,
        )
        if not bool(breaker_gates["cron_jobs"].get("allowed", True)):
            delegation = {
                "status": "cooldown_skip",
                "coder_used": None,
                "items_delegated": 0,
                "active_mission_id": None,
                "reason": str(breaker_gates["cron_jobs"].get("reason", "cron_jobs_cooldown")),
            }
        elif not bool(delegation_policy.get("enabled", True)):
            delegation = {"status": "disabled", "coder_used": None, "items_delegated": 0, "active_mission_id": None}
        elif bool(delegation_completion.get("active", False)):
            delegation = {
                "status": "delegation_in_progress",
                "coder_used": str(load_delegation_state(canonical_root).get("coder_used") or ""),
                "items_delegated": int(delegation_pending.get("total_pending", 0)),
                "active_mission_id": str(delegation_completion.get("mission_id", "")),
            }
            ingest_backlog = int(delegation_pending.get("pending", {}).get("ingest", {}).get("count", 0))
            if ingest_backlog > 0 and bool(policy.get("ingest_inline_rescue_on_stall", True)):
                rescue = _run_ingest_rescue(canonical_root)
                delegation["ingest_rescue"] = rescue
                if rescue.get("status") == "success":
                    # Refresh snapshot after rescue to avoid stale pending counters.
                    delegation_pending = scan_pending_work(canonical_root)
        else:
            delegation = delegate_to_coder(
                canonical_root,
                delegation_prompt,
                pending=delegation_pending,
                workload=delegation_workload,
                policy=delegation_policy,
            )
        delegation_state = load_delegation_state(canonical_root)
        ingest_progress = delegation_state.get("ingest_progress", {}) if isinstance(delegation_state, dict) else {}

        # Inline lightweight stages (reminders/outbox already done) + delegated heavy stages.
        backlog_pending = int(delegation_pending.get("pending", {}).get("hook_backlog", {}).get("count", 0))
        hook_backlog_replay = {
            "report": {
                "summary": {
                    "pending_count": backlog_pending,
                    "selected_count": 0,
                    "failed_count": 0,
                },
                "state": {"consecutive_failures": 0, "stall_ticks": 0},
            },
            "paths": {},
        }
        legacy_recovery = {
            "report": {
                "status": "delegated",
                "summary": {
                    "packaged_count": 0,
                    "selected_count": 0,
                    "blocked_count": 0,
                    "legacy_scan_ran": False,
                    "legacy_disabled_reason": "delegated",
                },
            },
            "paths": {},
        }
        intake_scan = run_intake_scan(canonical_root)
        intake_apply = run_intake_apply(
            canonical_root,
            max_entries=max(1, int(policy.get("max_apply_ops_per_heartbeat", 10))),
        )
        normalized_total = 0
        normalized_slices = 0
        runtime = {"summary": {"sessions_touched": 0, "compactions_done": 0, "distills_done": 0, "status": "delegated"}}
        approvals = {"summary": {"pending_count": 0}, "delivery": {"sent": False, "reason": "delegated"}}
        sg_promotion = {"summary": {"promoted_auto": 0, "pending_approval": 0}}
        learning = {"report": {"status": "delegated", "summary": {"promoted_count": 0, "candidate_files_processed": 0}}}
        episodic_memory = {"status": "delegated", "episodes_built": 0, "index_size_bytes": 0}
        summarizer = {"status": "delegated", "check": {"added": 0, "pending": int(delegation_pending.get("pending", {}).get("summarizer", {}).get("count", 0))}, "create": {"created": 0, "fallback": 0}, "ingest": {"done": 0}}
        research_status = "delegated" if bool(breaker_gates.get("retrieval", {}).get("allowed", True)) else "skipped_cooldown"
        odoo_status = "delegated" if bool(breaker_gates.get("tooling", {}).get("allowed", True)) else "skipped_cooldown"
        research = {"status": research_status, "tasks_processed": 0, "tasks_done": 0, "tasks_failed": 0}
        odoo = {"status": odoo_status, "tasks_processed": 0, "tasks_done": 0, "tasks_failed": 0}
        autonomy = {"status": "delegated", "paths": {}}
        proactivity = {"report": {"status": "delegated", "summary": {"queued_count": 0}}}

        health_notify = {"queued": False, "reason": "healthy"}
        try:
            live_items = materialized_items(canonical_root)
            dead_letter_count = sum(1 for row in live_items if str(row.get("status", "")).strip().lower() == "dead_letter")
            go_no_go = str(prod_doctor["report"].get("go_no_go", "go"))
            issues: list[str] = []
            if go_no_go != "go":
                issues.append(f"prod_doctor={go_no_go}")
            if bool(safety_status.get("paused", False)):
                issues.append(f"safety_paused={str(safety_status.get('reason', '')).strip() or 'true'}")
            if dead_letter_count > 0:
                issues.append(f"outbox_dead_letter={dead_letter_count}")
            if issues:
                health_message = (
                    "⚠️ OTTO Health detectó degradación.\n"
                    f"- {'; '.join(issues)}\n"
                    "Acción recomendada: revisar prod_doctor y heartbeat_latest."
                )
                health_notify = queue_topic_alert(
                    canonical_root,
                    topic="safety_degraded",
                    text=health_message,
                    source_ref="scripts/heartbeat_worker.py",
                    purpose="ops_health_alert",
                )
        except Exception as exc:  # pragma: no cover - defensive guard
            health_notify = {"queued": False, "reason": f"error:{exc.__class__.__name__}"}

        status = "success" if str(delegation.get("status", "")) in {"delegated", "delegation_in_progress", "no_work", "fallback_telegram", "disabled", "cooldown_skip"} else "partial"

        report = {
            "canonical_root": str(canonical_root.resolve()),
            "created_at": now.isoformat(),
            "status": status,
            "policy": policy,
            "intake_scan_summary": intake_scan["report"]["summary"],
            "intake_apply_summary": intake_apply["report"].get("apply", {}),
            "autonomy_status": autonomy.get("status", ""),
            "autonomy_paths": autonomy.get("paths", {}),
            "runtime_paths": {
                "json": "docs/_inbox/runtime_report_latest.json",
                "markdown": "docs/_inbox/runtime_report_latest.md",
                "log": "logs/runtime_latest.json",
            },
            "runtime_summary": runtime.get("summary", {}),
            "hook_backlog_scan_summary": hook_backlog_scan["report"].get("summary", {}),
            "hook_backlog_replay_summary": hook_backlog_replay["report"].get("summary", {}),
            "hook_backlog_paths": hook_backlog_replay.get("paths", {}),
            "legacy_recovery_summary": legacy_recovery["report"].get("summary", {}),
            "legacy_recovery_status": str(legacy_recovery["report"].get("status", "")),
            "legacy_recovery_paths": legacy_recovery.get("paths", {}),
            "approvals_summary": approvals.get("summary", {}),
            "sg_promotion_summary": sg_promotion.get("summary", {}),
            "outbox_delivery_summary": outbox_delivery["report"].get("summary", {}),
            "prod_doctor_summary": prod_doctor["report"].get("summary", {}),
            "prod_doctor_status": str(prod_doctor["report"].get("status", "")),
            "delegation": {
                "status": str(delegation.get("status", "")),
                "coder_used": delegation.get("coder_used"),
                "items_delegated": int(delegation.get("items_delegated", 0)),
                "active_mission_id": str(delegation.get("active_mission_id", "")),
                "workload": delegation_workload,
                "ingest_progress": ingest_progress,
            },
            "reminders": reminders,
            "episodic_memory": episodic_memory,
            "summarizer": summarizer,
            "research": research,
            "odoo": odoo,
            "proactivity_summary": proactivity["report"].get("summary", {}),
            "proactivity_status": str(proactivity["report"].get("status", "")),
            "project_docs_summary": {
                "status": project_docs["report"].get("status", ""),
                "updated_files_count": len(project_docs["report"].get("updated_files", [])),
                "paths": project_docs["report"].get("paths", {}),
            },
            "learning_summary": learning.get("report", {}).get("summary", {}),
            "learning_status": str(learning.get("report", {}).get("status", "")),
            "safety_status": safety_status,
            "summary": {
                "pending_drop_count": _pending_drop_count(canonical_root),
                "mission_learning_pending_count": _mission_learning_pending_count(canonical_root),
                "ingested_count": int(intake_apply["report"].get("apply", {}).get("ingested_count", 0)),
                "normalized_count": normalized_total,
                "slices_processed_count": normalized_slices,
                "runtime_compactions": int(runtime.get("summary", {}).get("compactions_done", 0)),
                "runtime_distills": int(runtime.get("summary", {}).get("distills_done", 0)),
                "approvals_pending": int(approvals.get("summary", {}).get("pending_count", 0)),
                "approvals_delivery_sent": bool(approvals.get("delivery", {}).get("sent", False)),
                "approvals_delivery_reason": str(approvals.get("delivery", {}).get("reason", "")),
                "sg_promoted_auto": int(sg_promotion.get("summary", {}).get("promoted_auto", 0)),
                "sg_pending_approval": int(sg_promotion.get("summary", {}).get("pending_approval", 0)),
                "outbox_queued": int(outbox_delivery["report"].get("summary", {}).get("queue_pending", 0)),
                "outbox_delivered": int(outbox_delivery["report"].get("summary", {}).get("delivered_in_run", 0)),
                "outbox_failed": int(outbox_delivery["report"].get("summary", {}).get("failed_in_run", 0)),
                "hook_backlog_pending": int(hook_backlog_replay["report"].get("summary", {}).get("pending_count", 0)),
                "hook_backlog_replayed": int(hook_backlog_replay["report"].get("summary", {}).get("selected_count", 0)),
                "hook_backlog_failed": int(hook_backlog_replay["report"].get("summary", {}).get("failed_count", 0)),
                "legacy_recovery_status": str(legacy_recovery["report"].get("status", "")),
                "legacy_scan_ran": bool(legacy_recovery["report"].get("summary", {}).get("legacy_scan_ran", False)),
                "legacy_disabled_reason": str(legacy_recovery["report"].get("summary", {}).get("legacy_disabled_reason", "")),
                "legacy_recovery_packaged": int(legacy_recovery["report"].get("summary", {}).get("packaged_count", 0)),
                "legacy_recovery_selected": int(legacy_recovery["report"].get("summary", {}).get("selected_count", 0)),
                "legacy_recovery_blocked": int(legacy_recovery["report"].get("summary", {}).get("blocked_count", 0)),
                "prod_doctor_status": str(prod_doctor["report"].get("status", "")),
                "reminders_delivered": int(reminders.get("delivered", 0)),
                "reminders_expired": int(reminders.get("expired", 0)),
                "reminders_pending": int(reminders.get("pending", 0)),
                "episodic_memory_status": str(episodic_memory.get("status", "")),
                "episodic_episodes_built": int(episodic_memory.get("episodes_built", 0)),
                "summarizer_status": str(summarizer.get("status", "")),
                "summarizer_added": int(summarizer.get("check", {}).get("added", 0)),
                "summarizer_missions_created": int(summarizer.get("create", {}).get("created", 0)),
                "summarizer_done": int(summarizer.get("ingest", {}).get("done", 0)),
                "research_status": str(research.get("status", "")),
                "research_tasks_processed": int(research.get("tasks_processed", 0)),
                "research_tasks_done": int(research.get("tasks_done", 0)),
                "odoo_status": str(odoo.get("status", "")),
                "odoo_tasks_processed": int(odoo.get("tasks_processed", 0)),
                "odoo_tasks_done": int(odoo.get("tasks_done", 0)),
                "health_notify_queued": bool(health_notify.get("queued", False)),
                "health_notify_reason": str(health_notify.get("reason", "")),
                "whatsapp_5h_remaining_pct": whatsapp_usage.get("five_hour_remaining_pct"),
                "whatsapp_usage_status": str(whatsapp_usage.get("status", "")),
                "whatsapp_hold_release_status": str(whatsapp_release.get("status", "")),
                "whatsapp_hold_released": int(whatsapp_release.get("released", 0)),
                "proactivity_status": str(proactivity["report"].get("status", "")),
                "proactivity_queued_count": int(proactivity["report"].get("summary", {}).get("queued_count", 0)),
                "delegation_status": str(delegation.get("status", "")),
                "delegation_coder": str(delegation.get("coder_used", "")),
                "delegation_items": int(delegation.get("items_delegated", 0)),
                "delegation_workload": delegation_workload,
                "delegation_active_mission": str(delegation.get("active_mission_id", "")),
                "delegation_ingest_total_packages": int(ingest_progress.get("total_packages_detected", 0)),
                "delegation_ingest_packages_processed": int(ingest_progress.get("packages_processed", 0)),
                "delegation_ingest_packages_remaining": int(ingest_progress.get("packages_remaining", 0)),
                "delegation_ingest_rescue_status": str((delegation.get("ingest_rescue") or {}).get("status", "")),
                "breaker_cron_jobs_allowed": bool(breaker_gates.get("cron_jobs", {}).get("allowed", True)),
                "breaker_tooling_allowed": bool(breaker_gates.get("tooling", {}).get("allowed", True)),
                "breaker_retrieval_allowed": bool(breaker_gates.get("retrieval", {}).get("allowed", True)),
                "project_docs_status": str(project_docs["report"].get("status", "")),
                "project_docs_updated_files_count": len(project_docs["report"].get("updated_files", [])),
                "day2_doc_created": int(day2_inventory.get("summary", {}).get("created", 0)),
                "day2_doc_modified": int(day2_inventory.get("summary", {}).get("modified", 0)),
                "day2_doc_renamed": int(day2_inventory.get("summary", {}).get("renamed", 0)),
                "day2_doc_deleted": int(day2_inventory.get("summary", {}).get("deleted", 0)),
                "day2_doc_rot": int(day2_inventory.get("summary", {}).get("doc_rot", 0)),
                "learning_status": str(learning.get("report", {}).get("status", "")),
                "learning_promoted_count": int(learning.get("report", {}).get("summary", {}).get("promoted_count", 0)),
                "learning_candidate_files_processed": int(
                    learning.get("report", {}).get("summary", {}).get("candidate_files_processed", 0)
                ),
                **pending_snapshot.get("pending", {}),
            },
            "version": 1,
        }
        logger.info(
            "heartbeat: ingest progress %s/%s (remaining=%s)",
            int(report["summary"].get("delegation_ingest_packages_processed", 0)),
            int(report["summary"].get("delegation_ingest_total_packages", 0)),
            int(report["summary"].get("delegation_ingest_packages_remaining", 0)),
        )

        autonomy_state["heartbeat_last_run_utc"] = now.isoformat()
        autonomy_state["heartbeat_last_status"] = status
        autonomy_state["heartbeat_last_report"] = REPORT_JSON.as_posix()
        _save_json(autonomy_state_path, autonomy_state)

        _save_json(canonical_root / REPORT_JSON, report)
        _save_json(canonical_root / REPORT_LOG, report)

        lines = [
            "# Heartbeat Latest",
            "",
            f"- Status: `{status}`",
            f"- Pending drop: {report['summary']['pending_drop_count']}",
            f"- Mission learning pending: {report['summary']['mission_learning_pending_count']}",
            f"- Ingested count: {report['summary']['ingested_count']}",
            f"- Normalized count: {report['summary']['normalized_count']}",
            f"- Slices processed: {report['summary']['slices_processed_count']}",
            f"- Runtime compactions: {report['summary'].get('runtime_compactions', 0)}",
            f"- Runtime distills: {report['summary'].get('runtime_distills', 0)}",
            f"- Approvals pending: {report['summary'].get('approvals_pending', 0)}",
            f"- Approvals delivery sent: `{report['summary'].get('approvals_delivery_sent', False)}`",
            f"- Approvals delivery reason: `{report['summary'].get('approvals_delivery_reason', '')}`",
            f"- SG promoted auto: {report['summary'].get('sg_promoted_auto', 0)}",
            f"- SG pending approval: {report['summary'].get('sg_pending_approval', 0)}",
            f"- Outbox queued: {report['summary'].get('outbox_queued', 0)}",
            f"- Outbox delivered: {report['summary'].get('outbox_delivered', 0)}",
            f"- Outbox failed: {report['summary'].get('outbox_failed', 0)}",
            f"- Hook backlog pending: {report['summary'].get('hook_backlog_pending', 0)}",
            f"- Hook backlog replayed: {report['summary'].get('hook_backlog_replayed', 0)}",
            f"- Hook backlog failed: {report['summary'].get('hook_backlog_failed', 0)}",
            f"- Legacy recovery status: `{report['summary'].get('legacy_recovery_status', '')}`",
            f"- Legacy recovery scan ran: `{report['summary'].get('legacy_scan_ran', False)}`",
            f"- Legacy recovery disabled reason: `{report['summary'].get('legacy_disabled_reason', '')}`",
            f"- Legacy recovery packaged: {report['summary'].get('legacy_recovery_packaged', 0)}",
            f"- Legacy recovery selected: {report['summary'].get('legacy_recovery_selected', 0)}",
            f"- Legacy recovery blocked: {report['summary'].get('legacy_recovery_blocked', 0)}",
            f"- Prod doctor status: `{report['summary'].get('prod_doctor_status', '')}`",
            f"- Reminders delivered: {report['summary'].get('reminders_delivered', 0)}",
            f"- Reminders expired: {report['summary'].get('reminders_expired', 0)}",
            f"- Reminders pending: {report['summary'].get('reminders_pending', 0)}",
            f"- Episodic memory status: `{report['summary'].get('episodic_memory_status', '')}`",
            f"- Episodic episodes built: {report['summary'].get('episodic_episodes_built', 0)}",
            f"- Summarizer status: `{report['summary'].get('summarizer_status', '')}`",
            f"- Summarizer added: {report['summary'].get('summarizer_added', 0)}",
            f"- Summarizer missions created: {report['summary'].get('summarizer_missions_created', 0)}",
            f"- Summarizer done: {report['summary'].get('summarizer_done', 0)}",
            f"- Research status: `{report['summary'].get('research_status', '')}`",
            f"- Research tasks processed: {report['summary'].get('research_tasks_processed', 0)}",
            f"- Research tasks done: {report['summary'].get('research_tasks_done', 0)}",
            f"- Odoo status: `{report['summary'].get('odoo_status', '')}`",
            f"- Odoo tasks processed: {report['summary'].get('odoo_tasks_processed', 0)}",
            f"- Odoo tasks done: {report['summary'].get('odoo_tasks_done', 0)}",
            f"- Health notify queued: `{report['summary'].get('health_notify_queued', False)}`",
            f"- Health notify reason: `{report['summary'].get('health_notify_reason', '')}`",
            f"- WhatsApp 5h remaining pct: `{report['summary'].get('whatsapp_5h_remaining_pct', 'unknown')}`",
            f"- WhatsApp usage status: `{report['summary'].get('whatsapp_usage_status', '')}`",
            f"- WhatsApp hold release: `{report['summary'].get('whatsapp_hold_release_status', '')}` (released={report['summary'].get('whatsapp_hold_released', 0)})",
            f"- Proactivity status: `{report['summary'].get('proactivity_status', '')}`",
            f"- Proactivity queued: {report['summary'].get('proactivity_queued_count', 0)}",
            f"- Delegation status: `{report['summary'].get('delegation_status', '')}`",
            f"- Delegation coder: `{report['summary'].get('delegation_coder', '')}`",
            f"- Delegation workload: `{report['summary'].get('delegation_workload', '')}`",
            f"- Delegation active mission: `{report['summary'].get('delegation_active_mission', '')}`",
            f"- Ingest progress: {report['summary'].get('delegation_ingest_packages_processed', 0)}/{report['summary'].get('delegation_ingest_total_packages', 0)} (remaining={report['summary'].get('delegation_ingest_packages_remaining', 0)})",
            f"- Ingest rescue: `{report['summary'].get('delegation_ingest_rescue_status', '')}`",
            f"- Project docs status: `{report['summary'].get('project_docs_status', '')}`",
            f"- Project docs updated files: {report['summary'].get('project_docs_updated_files_count', 0)}",
            f"- Learning status: `{report['summary'].get('learning_status', '')}`",
            f"- Learning promoted: {report['summary'].get('learning_promoted_count', 0)}",
            f"- Learning candidate files processed: {report['summary'].get('learning_candidate_files_processed', 0)}",
            f"- Autonomy status: `{report['autonomy_status']}`",
            f"- JSON report: `{REPORT_JSON.as_posix()}`",
            f"- Log report: `{REPORT_LOG.as_posix()}`",
        ]
        (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Token budget: cleanup de registros >7 días.
        try:
            _policy_path = canonical_root / "state" / "token_budget_policy.json"
            if _policy_path.is_file():
                _bp = json.loads(_policy_path.read_text(encoding="utf-8"))
                if bool(_bp.get("enabled", False)):
                    _cleanup_old_token_records(canonical_root, days=7)
                    logger.info("heartbeat: token budget cleanup OK")
        except Exception as _e:  # pragma: no cover - defensive guard
            logger.warning(f"heartbeat: token budget cleanup falló: {_e}")
        try:
            cleaned = _cleanup_outbox_archives(canonical_root, days=7)
            logger.info("heartbeat: outbox archive cleanup removed=%s", cleaned.get("removed_files", 0))
        except Exception as _e:  # pragma: no cover - defensive guard
            logger.warning(f"heartbeat: outbox archive cleanup falló: {_e}")

        return {
            "report": report,
            "paths": {
                "json": REPORT_JSON.as_posix(),
                "markdown": REPORT_MD.as_posix(),
                "log": REPORT_LOG.as_posix(),
                "policy": POLICY_PATH.as_posix(),
            },
        }
    finally:
        _release_lock(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description="Heartbeat worker")
    parser.add_argument("--root", default=".")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.once:
        parser.error("Use --once")

    out = run_heartbeat_once(args.root, force=args.force)
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "status": out["report"]["status"],
                "summary": out["report"]["summary"],
                "paths": out["paths"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if out["report"]["status"] in {"success", "skipped_interval", "paused_safety", "paused_safety_auto", "no_pending_work"} else 3


if __name__ == "__main__":
    raise SystemExit(main())

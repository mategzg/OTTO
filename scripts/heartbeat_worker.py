#!/usr/bin/env python3
"""Passive heartbeat worker: intake -> normalize -> runtime -> outbox -> autonomy tick."""

from __future__ import annotations

import argparse
import json
import os
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
from scripts.dropbox_intake import run_apply as run_intake_apply
from scripts.dropbox_intake import run_scan as run_intake_scan
from scripts.hook_backlog import run_replay as run_hook_backlog_replay
from scripts.hook_backlog import run_scan as run_hook_backlog_scan
from scripts.legacy_recovery_worker import run_once as run_legacy_recovery_once
from scripts.outbox_delivery import run_deliver as run_outbox_deliver
from scripts.outbox_queue import enqueue_message
from scripts.prod_doctor import run_prod_doctor
from scripts.project_docs_maintainer import run_apply as run_project_docs_apply
from scripts.repo_root import get_canonical_root
from scripts.safety_switch import autopause_switch, get_safety_status, load_policy as load_safety_policy
from scripts.session_memory_manager import run_session_maintenance
from scripts.sg_promotion import process_promotions

POLICY_PATH = Path("state/heartbeat_policy.json")
LOCK_PATH = Path("state/heartbeat_worker.lock")
AUTONOMY_STATE_PATH = Path("state/autonomy_state.json")

REPORT_JSON = Path("docs/_inbox/heartbeat_latest.json")
REPORT_MD = Path("docs/_inbox/heartbeat_latest.md")
REPORT_LOG = Path("logs/heartbeat_latest.json")

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

        outbox_delivery = run_outbox_deliver(
            canonical_root,
            max_items_per_run=max(1, int(policy.get("max_outbox_items_per_heartbeat", 20))),
            max_chars_per_item=max(200, int(policy.get("max_outbox_chars_per_item", 4000))),
            max_runtime_seconds=max(5, int(policy.get("max_runtime_seconds", 300) // 3)),
        )
        project_docs = {"report": {"status": "disabled", "updated_files": [], "paths": {}}}
        if bool(policy.get("run_project_docs_maintainer", True)):
            project_docs = run_project_docs_apply(canonical_root)

        hook_backlog_scan = run_hook_backlog_scan(canonical_root)
        hook_backlog_replay = run_hook_backlog_replay(
            canonical_root,
            max_events=max(1, int(policy.get("max_hook_backlog_events_per_heartbeat", 25))),
            max_runtime_seconds=max(1, int(policy.get("max_hook_backlog_runtime_seconds", 20))),
        )
        legacy_recovery = {
            "report": {
                "status": "disabled",
                "summary": {
                    "packaged_count": 0,
                    "selected_count": 0,
                    "blocked_count": 0,
                    "legacy_scan_ran": False,
                    "legacy_disabled_reason": "disabled",
                },
            },
            "paths": {},
        }
        if bool(policy.get("run_legacy_recovery", True)):
            legacy_recovery = run_legacy_recovery_once(
                canonical_root,
                force=bool(policy.get("legacy_recovery_force", False)),
            )

        backlog_state = hook_backlog_replay["report"].get("state", {})
        backlog_summary = hook_backlog_replay["report"].get("summary", {})
        backlog_consecutive = int(backlog_state.get("consecutive_failures", 0))
        backlog_stall_ticks = int(backlog_state.get("stall_ticks", 0))
        backlog_pending = int(backlog_summary.get("pending_count", 0))
        safety_triggered = False
        if backlog_consecutive >= int(safety_policy.get("hook_backlog_consecutive_failures_autopause", 3)):
            safety_triggered = True
        if (
            backlog_pending >= int(safety_policy.get("hook_backlog_pending_threshold", 300))
            and backlog_stall_ticks >= int(safety_policy.get("hook_backlog_stall_ticks_autopause", 3))
        ):
            safety_triggered = True
        if safety_triggered:
            safety_status = autopause_switch(
                canonical_root,
                reason=(
                    "autopause_hook_backlog:"
                    f"consecutive_failures={backlog_consecutive},"
                    f"stall_ticks={backlog_stall_ticks},pending={backlog_pending}"
                ),
            )
            try:
                enqueue_message(
                    canonical_root,
                    channel="telegram_owner",
                    target=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
                    text=(
                        "Safety switch activado automaticamente.\n"
                        f"reason={safety_status.get('reason', '')}\n"
                        f"until={safety_status.get('until_ts', '')}\n"
                        f"hook_backlog_report={hook_backlog_replay['paths']['markdown']}"
                    ),
                    purpose="ops_alert",
                    source_ref="scripts/heartbeat_worker.py",
                    metadata={"kind": "autopause", "component": "hook_backlog"},
                )
            except Exception:
                pass
            report = {
                "canonical_root": str(canonical_root.resolve()),
                "created_at": now.isoformat(),
                "status": "paused_safety_auto",
                "policy": policy,
                "safety_status": safety_status,
                "hook_backlog_scan_summary": hook_backlog_scan["report"].get("summary", {}),
                "hook_backlog_replay_summary": hook_backlog_replay["report"].get("summary", {}),
                "legacy_recovery_summary": legacy_recovery["report"].get("summary", {}),
                "legacy_recovery_status": str(legacy_recovery["report"].get("status", "")),
                "outbox_delivery_summary": outbox_delivery["report"].get("summary", {}),
                "project_docs_summary": {
                    "status": project_docs["report"].get("status", ""),
                    "updated_files_count": len(project_docs["report"].get("updated_files", [])),
                    "paths": project_docs["report"].get("paths", {}),
                },
                "summary": {
                    "pending_drop_count": _pending_drop_count(canonical_root),
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
                    "project_docs_status": str(project_docs["report"].get("status", "")),
                },
                "version": 1,
            }
            _save_json(canonical_root / REPORT_JSON, report)
            _save_json(canonical_root / REPORT_LOG, report)
            (canonical_root / REPORT_MD).write_text(
                "# Heartbeat Latest\n\n"
                "- Status: `paused_safety_auto`\n"
                f"- Reason: `{safety_status.get('reason', '')}`\n"
                f"- Hook backlog pending: {report['summary']['hook_backlog_pending']}\n"
                f"- Hook backlog failed: {report['summary']['hook_backlog_failed']}\n",
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

        intake_scan = run_intake_scan(canonical_root)
        intake_apply = run_intake_apply(canonical_root, max_entries=max(1, int(policy.get("max_sources_per_heartbeat", 2))))

        normalized_total = 0
        normalized_slices = 0
        for item in intake_apply["report"].get("apply", {}).get("ingested", []):
            sid = str(item.get("source_id", ""))
            if not sid:
                continue
            norm = run_normalize(canonical_root, source_id=sid)
            normalized_total += norm["report"]["summary"]["normalized_count"]
            normalized_slices += norm["report"]["summary"]["slice_count"]

        if normalized_total == 0:
            # Opportunistic normalization for latest unnormalized sources.
            norm_latest = run_normalize(canonical_root, scan_latest=True)
            normalized_total += norm_latest["report"]["summary"]["normalized_count"]
            normalized_slices += norm_latest["report"]["summary"]["slice_count"]

        runtime = run_session_maintenance(
            canonical_root,
            max_sessions=max(0, int(policy.get("max_sessions_per_tick", 12))),
            max_compactions=max(0, int(policy.get("max_compactions_per_tick", 8))),
            max_distills=max(0, int(policy.get("max_distill_per_tick", 4))),
            max_runtime_seconds=max(30, int(policy.get("max_runtime_seconds", 300))),
        )

        approvals = process_pending_approvals(canonical_root)
        sg_promotion = process_promotions(canonical_root)

        prod_doctor = {"report": {"status": "disabled", "summary": {}}}
        if bool(policy.get("run_prod_doctor", True)):
            prod_doctor = run_prod_doctor(canonical_root, force=False)

        autonomy = run_autonomy_tick(
            root=canonical_root,
            force=force,
            max_sources_per_tick=max(1, int(policy.get("max_sources_per_heartbeat", 2))),
            max_apply_ops_per_tick=max(1, int(policy.get("max_apply_ops_per_heartbeat", 10))),
            max_runtime_seconds=max(60, int(policy.get("max_runtime_seconds", 300))),
        )

        status = "success" if autonomy.get("status") in {"success", "idle", "paused", "backoff", "paused_safety"} else "partial"

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
            "project_docs_summary": {
                "status": project_docs["report"].get("status", ""),
                "updated_files_count": len(project_docs["report"].get("updated_files", [])),
                "paths": project_docs["report"].get("paths", {}),
            },
            "safety_status": safety_status,
            "summary": {
                "pending_drop_count": _pending_drop_count(canonical_root),
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
                "project_docs_status": str(project_docs["report"].get("status", "")),
                "project_docs_updated_files_count": len(project_docs["report"].get("updated_files", [])),
            },
            "version": 1,
        }

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
            f"- Project docs status: `{report['summary'].get('project_docs_status', '')}`",
            f"- Project docs updated files: {report['summary'].get('project_docs_updated_files_count', 0)}",
            f"- Autonomy status: `{report['autonomy_status']}`",
            f"- JSON report: `{REPORT_JSON.as_posix()}`",
            f"- Log report: `{REPORT_LOG.as_posix()}`",
        ]
        (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

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
    return 0 if out["report"]["status"] in {"success", "skipped_interval", "paused_safety", "paused_safety_auto"} else 3


if __name__ == "__main__":
    raise SystemExit(main())

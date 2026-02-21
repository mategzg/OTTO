import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scripts.heartbeat_delegator as delegator
from scripts.outbox_queue import enqueue_message
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw" / "_pending_drop").mkdir(parents=True, exist_ok=True)
    (root / "state" / "missions").mkdir(parents=True, exist_ok=True)
    (root / "state" / "research_queue.json").write_text("[]\n", encoding="utf-8")
    (root / "state" / "odoo_queue.json").write_text("[]\n", encoding="utf-8")
    (root / "state" / "summarizer_queue.json").write_text("[]\n", encoding="utf-8")
    (root / "state" / "reminders_queue.json").write_text("[]\n", encoding="utf-8")
    (root / "docs" / "_inbox" / "memory_inbox.ndjson").write_text("", encoding="utf-8")
    (root / "state" / "hook_backlog").mkdir(parents=True, exist_ok=True)
    (root / "state" / "hook_backlog" / "events.ndjson").write_text("", encoding="utf-8")
    (root / "docs" / "_inbox" / "prod_doctor_latest.json").write_text(
        json.dumps({"status": "ok", "go_no_go": "go"}) + "\n",
        encoding="utf-8",
    )


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "owner-chat")
    set_canonical_root(workspace, created_by="test")
    return workspace


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def test_scan_pending_work_detects_items_across_queues(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    _write_json(workspace / "state" / "research_queue.json", [{"task_id": "r1", "status": "pending"}])
    _write_json(workspace / "state" / "odoo_queue.json", [{"task_id": "o1", "status": "pending"}])
    _write_json(workspace / "state" / "summarizer_queue.json", [{"id": "s1", "status": "pending"}])
    _write_json(
        workspace / "state" / "reminders_queue.json",
        [{"id": "rem1", "status": "pending", "deliver_at": (now - timedelta(minutes=1)).isoformat()}],
    )
    (workspace / "docs" / "_inbox" / "memory_inbox.ndjson").write_text('{"k":"v"}\n', encoding="utf-8")
    (workspace / "state" / "hook_backlog" / "events.ndjson").write_text('{"id":"e1"}\n', encoding="utf-8")
    enqueue_message(workspace, channel="telegram_owner", target="owner", text="pending", purpose="test")

    out = delegator.scan_pending_work(workspace)
    assert out["pending"]["research"]["count"] == 1
    assert out["pending"]["odoo"]["count"] == 1
    assert out["pending"]["summarizer"]["count"] == 1
    assert out["pending"]["reminders"]["count"] == 1
    assert out["pending"]["memory"]["count"] == 1
    assert out["pending"]["outbox"]["count"] == 1
    assert out["pending"]["hook_backlog"]["count"] == 1
    assert out["total_pending"] >= 7


def test_scan_pending_work_returns_empty_when_no_items(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = delegator.scan_pending_work(workspace)
    assert out["total_pending"] == 0
    assert all(int(section["count"]) == 0 for section in out["pending"].values())


def test_estimate_workload_classifies_ranges():
    assert delegator.estimate_workload({"total_pending": 0}) == "none"
    assert delegator.estimate_workload({"total_pending": 3}) == "light"
    assert delegator.estimate_workload({"total_pending": 10}) == "medium"
    assert delegator.estimate_workload({"total_pending": 20}) == "heavy"


def test_build_delegation_prompt_contains_scripts_and_priority(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending = {
        "total_pending": 3,
        "pending": {
            "outbox": {"count": 1, "queue_path": "docs/_inbox/outbox_queue.ndjson", "items": ["x"]},
            "reminders": {"count": 1, "queue_path": "state/reminders_queue.json", "items": ["r"]},
            "hook_backlog": {"count": 1, "queue_path": "state/hook_backlog/events.ndjson", "items": []},
            "research": {"count": 0, "queue_path": "state/research_queue.json", "items": []},
            "odoo": {"count": 0, "queue_path": "state/odoo_queue.json", "items": []},
            "summarizer": {"count": 0, "queue_path": "state/summarizer_queue.json", "items": []},
            "memory": {"count": 0, "queue_path": "docs/_inbox/memory_inbox.ndjson", "items": []},
            "health": {"count": 0, "queue_path": "docs/_inbox/prod_doctor_latest.json", "items": []},
        },
    }
    light = delegator.build_delegation_prompt(workspace, pending, "light")
    heavy = delegator.build_delegation_prompt(workspace, pending, "heavy")
    assert "RUN_STYLE: ATOMIC" in light
    assert "RUN_STYLE: POTENT" in heavy
    assert "python3 scripts/reminder_engine.py --process --root ." in light
    assert "python3 scripts/outbox_delivery.py --deliver --root ." in light
    assert "NO-FABRICATION" in heavy


def test_delegate_to_coder_fallback_order_codex_then_claude_then_telegram(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending = {"total_pending": 2, "pending": {}}
    prompt = "prompt"
    calls = []

    def _fake_init(_root, **kwargs):
        peer = kwargs.get("peer_id", "")
        calls.append(peer)
        if "codex" in peer:
            raise RuntimeError("codex unavailable")
        return {"report": {"mission_paths": {"mission_dir": "state/missions/x"}}}

    monkeypatch.setattr(delegator, "orchestrator_run_init", _fake_init)
    monkeypatch.setattr(delegator, "orchestrator_emit_prompts", lambda *_a, **_k: {"report": {"status": "success"}})
    out = delegator.delegate_to_coder(workspace, prompt, pending=pending, workload="light")
    assert out["status"] == "delegated"
    assert out["coder_used"] == "claude_code"
    assert calls[0].endswith("codex")
    assert calls[1].endswith("claude_code")

    # Force total failure to validate Telegram fallback.
    monkeypatch.setattr(delegator, "orchestrator_run_init", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down")))
    out2 = delegator.delegate_to_coder(workspace, "prompt2", pending=pending, workload="light", policy={"max_active_delegations": 5})
    assert out2["status"] == "fallback_telegram"


def test_check_completed_delegations_clears_active_when_mission_completed(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    state_path = workspace / "state" / "heartbeat_delegation_state.json"
    _write_json(
        state_path,
        {
            "last_delegation_at": datetime.now(timezone.utc).isoformat(),
            "coder_used": "codex",
            "items_delegated": 2,
            "status": "delegated",
            "active_mission_id": "hbdel_test_1",
        },
    )
    mission_json = workspace / "state" / "missions" / "hbdel_test_1" / "mission.json"
    mission_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(mission_json, {"status": "completed"})
    out = delegator.check_completed_delegations(workspace)
    assert out["status"] == "completed"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["active_mission_id"] is None


def test_no_redelegate_when_active_mission_exists(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    state_path = workspace / "state" / "heartbeat_delegation_state.json"
    _write_json(
        state_path,
        {
            "last_delegation_at": datetime.now(timezone.utc).isoformat(),
            "coder_used": "codex",
            "items_delegated": 1,
            "status": "delegated",
            "active_mission_id": "hbdel_active",
        },
    )
    out = delegator.delegate_to_coder(
        workspace,
        "prompt",
        pending={"total_pending": 5, "pending": {}},
        workload="medium",
        policy={"max_active_delegations": 1},
    )
    assert out["status"] == "delegation_in_progress"
    assert out["active_mission_id"] == "hbdel_active"


def test_scan_pending_work_detects_ingest_pending_and_excludes_system_dirs(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending = workspace / "vault" / "inbox_raw" / "_pending_drop"
    (pending / "chatgpt_export_001").mkdir(parents=True, exist_ok=True)
    (pending / "mission_learning").mkdir(parents=True, exist_ok=True)
    (pending / "research_batch_1").mkdir(parents=True, exist_ok=True)
    (pending / "_ingested").mkdir(parents=True, exist_ok=True)
    (pending / "legacy_recovery_keep").mkdir(parents=True, exist_ok=True)

    out = delegator.scan_pending_work(workspace)
    assert out["pending"]["ingest_pending"]["count"] == 1
    assert out["pending"]["ingest"]["count"] >= 1
    assert out["pending"]["ingest_pending"]["items"] == ["chatgpt_export_001"]


def test_build_delegation_prompt_includes_ingest_commands_when_pending(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending = delegator.scan_pending_work(workspace)
    pending["pending"]["ingest"]["count"] = 2
    pending["total_pending"] = pending.get("total_pending", 0) + 2
    prompt = delegator.build_delegation_prompt(workspace, pending, "medium")
    assert "python3 scripts/dropbox_intake.py --apply --root ." in prompt
    assert "python3 scripts/chatgpt_export_normalize.py --root ." in prompt
    assert "python3 scripts/brain_ingest_router.py --plan --root ." in prompt
    assert "subprocess.run(['python3','scripts/brain_ingest_router.py','--apply',plan_id,'--root','.'], check=False)" in prompt
    assert "batch permitido" in prompt


def test_build_delegation_prompt_skips_ingest_block_when_no_pending(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending = delegator.scan_pending_work(workspace)
    prompt = delegator.build_delegation_prompt(workspace, pending, "light")
    assert "- ingest: `NO_PENDING_INGEST`" in prompt
    assert "python3 scripts/chatgpt_export_normalize.py --root ." not in prompt


def test_policy_priority_places_ingest_before_research(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    policy = delegator.load_policy(workspace)
    order = list(policy.get("priority_order", []))
    assert "ingest" in order
    assert order.index("ingest") < order.index("research")


def test_check_completed_no_pending_releases_active_mission(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    state_path = workspace / "state" / "heartbeat_delegation_state.json"
    _write_json(
        state_path,
        {
            "last_delegation_at": datetime.now(timezone.utc).isoformat(),
            "coder_used": "codex",
            "items_delegated": 1,
            "status": "delegated",
            "active_mission_id": "hbdel_no_pending_1",
        },
    )
    mission_json = workspace / "state" / "missions" / "hbdel_no_pending_1" / "mission.json"
    mission_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(mission_json, {"status": "active"})

    out = delegator.check_completed_delegations(workspace)
    assert out["status"] == "completed_no_pending"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["active_mission_id"] is None


def test_check_completed_ignores_health_only_pending(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    state_path = workspace / "state" / "heartbeat_delegation_state.json"
    _write_json(
        state_path,
        {
            "last_delegation_at": datetime.now(timezone.utc).isoformat(),
            "coder_used": "codex",
            "items_delegated": 1,
            "status": "delegated",
            "active_mission_id": "hbdel_health_only_1",
        },
    )
    mission_json = workspace / "state" / "missions" / "hbdel_health_only_1" / "mission.json"
    mission_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(mission_json, {"status": "active"})

    prod = workspace / "docs" / "_inbox" / "prod_doctor_latest.json"
    prod.parent.mkdir(parents=True, exist_ok=True)
    _write_json(prod, {"go_no_go": "go_with_limits"})

    out = delegator.check_completed_delegations(workspace)
    assert out["status"] == "missing_handoff_retry"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["active_mission_id"] is None
    assert int(state.get("missing_handoff_attempts", 0)) >= 1


def test_check_completed_recognizes_handoff_file_completion(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    state_path = workspace / "state" / "heartbeat_delegation_state.json"
    _write_json(
        state_path,
        {
            "last_delegation_at": datetime.now(timezone.utc).isoformat(),
            "coder_used": "codex",
            "items_delegated": 1,
            "status": "delegated",
            "active_mission_id": "hbdel_handoff_1",
            "active_handoff_path": "docs/_inbox/subagent_handoffs/hbdel_handoff_1.json",
        },
    )
    mission_json = workspace / "state" / "missions" / "hbdel_handoff_1" / "mission.json"
    mission_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(mission_json, {"status": "active"})

    handoff = workspace / "docs" / "_inbox" / "subagent_handoffs" / "hbdel_handoff_1.json"
    handoff.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        handoff,
        {
            "run_id": "hbdel_handoff_1",
            "status": "success",
            "summary": ["done"],
            "files_changed": [],
            "gates": [],
            "gaps": [],
            "commit_hash": "N/A",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    out = delegator.check_completed_delegations(workspace)
    assert out["status"] == "completed"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["active_mission_id"] is None
    assert state.get("active_handoff_path") is None


def test_check_completed_updates_ingest_progress_tracking(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    state_path = workspace / "state" / "heartbeat_delegation_state.json"
    _write_json(
        state_path,
        {
            "last_delegation_at": datetime.now(timezone.utc).isoformat(),
            "coder_used": "codex",
            "items_delegated": 2,
            "status": "delegated",
            "active_mission_id": "hbdel_ingest_1",
            "ingest_progress": {
                "total_packages_detected": 3,
                "packages_processed": 1,
                "packages_remaining": 2,
                "last_batch_at": None,
            },
        },
    )
    mission_json = workspace / "state" / "missions" / "hbdel_ingest_1" / "mission.json"
    mission_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(mission_json, {"status": "completed"})
    (workspace / "vault" / "inbox_raw" / "_pending_drop" / "pkg_2").mkdir(parents=True, exist_ok=True)

    out = delegator.check_completed_delegations(workspace)
    assert out["status"] == "completed"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    progress = state.get("ingest_progress", {})
    assert int(progress.get("packages_remaining", -1)) == 1
    assert int(progress.get("total_packages_detected", 0)) >= 2


def test_ingest_progressive_cycle_delegates_next_batch(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending_root = workspace / "vault" / "inbox_raw" / "_pending_drop"
    (pending_root / "chatgpt_batch_1").mkdir(parents=True, exist_ok=True)
    (pending_root / "chatgpt_batch_2").mkdir(parents=True, exist_ok=True)

    created: list[str] = []

    def _fake_init(_root, **kwargs):
        mission_id = kwargs.get("mission_id", "")
        created.append(mission_id)
        return {"report": {"mission_paths": {"mission_dir": f"state/missions/{mission_id}"}}}

    monkeypatch.setattr(delegator, "orchestrator_run_init", _fake_init)
    monkeypatch.setattr(delegator, "orchestrator_emit_prompts", lambda *_a, **_k: {"report": {"status": "success"}})

    pending_first = delegator.scan_pending_work(workspace)
    prompt_first = delegator.build_delegation_prompt(workspace, pending_first, delegator.estimate_workload(pending_first))
    first = delegator.delegate_to_coder(workspace, prompt_first, pending=pending_first, workload="light")
    assert first["status"] == "delegated"

    mission_json = workspace / "state" / "missions" / first["active_mission_id"] / "mission.json"
    mission_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(mission_json, {"status": "completed"})
    (pending_root / "_ingested").mkdir(parents=True, exist_ok=True)
    (pending_root / "chatgpt_batch_1").rename(pending_root / "_ingested" / "chatgpt_batch_1")

    done = delegator.check_completed_delegations(workspace)
    assert done["status"] == "completed"

    pending_second = delegator.scan_pending_work(workspace)
    prompt_second = delegator.build_delegation_prompt(workspace, pending_second, delegator.estimate_workload(pending_second))
    second = delegator.delegate_to_coder(workspace, prompt_second, pending=pending_second, workload="light")
    assert second["status"] == "delegated"
    assert second["active_mission_id"] != first["active_mission_id"]
    assert len(created) >= 2

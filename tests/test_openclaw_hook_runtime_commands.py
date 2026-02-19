from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import openclaw_hook
from scripts.repo_root import set_canonical_root
from scripts.session_memory_manager import append_event
from scripts.sg_promotion import enqueue_promotion


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw" / "_pending_drop").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_openclaw_hook_runtime_and_sg_commands(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    append_event(
        workspace,
        {
            "agent_id": "otto",
            "channel": "discord",
            "chat_type": "thread",
            "peer_id": "u1",
            "channel_id": "ventas",
            "thread_id": "case_1",
            "message_id": "m1",
            "timestamp": old_ts,
            "text": "Decision del caso para cerrar",
            "labels": ["memory_worthy"],
        },
    )

    enqueue = enqueue_promotion(
        workspace,
        {"text": "token secreto del cliente", "source_ref": "runtime:test", "sensitivity": "high"},
    )
    assert enqueue["status"] == "enqueued"

    status = openclaw_hook.handle_repo_command("/runtime status", root=workspace)
    assert status["ok"] is True

    compact = openclaw_hook.handle_repo_command("/runtime compact", root=workspace)
    assert compact["ok"] is True

    distill = openclaw_hook.handle_repo_command("/runtime distill", root=workspace)
    assert distill["ok"] is True

    approve = openclaw_hook.handle_repo_command(f"/sg approve {enqueue['promotion_id']}", root=workspace)
    assert approve["ok"] is True

    outbox = workspace / "docs" / "_inbox" / "outbox_latest.md"
    assert outbox.is_file()


def test_openclaw_hook_runtime_ingest_command(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    payload = '{"channel":"telegram","peer_id":"mateo","message_id":"m1","text":"hola desde ingress"}'
    result = openclaw_hook.handle_repo_command(f"/runtime ingest {payload}", root=workspace)
    assert result["ok"] is True
    assert result["ingress"]["status"] == "success"

    approvals = openclaw_hook.handle_repo_command("/approvals status", root=workspace)
    assert approvals["ok"] is True

    domains = openclaw_hook.handle_repo_command("/discord domains status", root=workspace)
    assert domains["ok"] is True

    outbox_status = openclaw_hook.handle_repo_command("/outbox status", root=workspace)
    assert outbox_status["ok"] is True

    outbox_deliver = openclaw_hook.handle_repo_command("/outbox deliver", root=workspace)
    assert outbox_deliver["ok"] is True

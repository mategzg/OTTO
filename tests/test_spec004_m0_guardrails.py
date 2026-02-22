import json
from pathlib import Path

from scripts.runtime_guardrails import redact_no_leak_report
from scripts.nl_skill_router import run_nl_router
from scripts.outbox_delivery import run_deliver
from scripts.outbox_queue import enqueue_message
from scripts.repo_root import set_canonical_root
from scripts.session_memory_manager import append_event


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    for d in ("openclaw", "scripts", "ops", "brain", "docs/_inbox", "logs", "state"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_dm_scope_whatsapp_requires_real_peer(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    try:
        append_event(
            workspace,
            {
                "channel": "whatsapp",
                "chat_type": "dm",
                "peer_id": "_",
                "message_id": "m1",
                "text": "hola",
            },
        )
        assert False, "expected dm_scope_violation"
    except ValueError as exc:
        assert "dm_scope_violation" in str(exc)


def test_send_policy_blocks_cron_hook_to_clients(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    enqueue_message(
        workspace,
        channel="whatsapp",
        target="client-01",
        text="hola",
        source_ref="cron:/job/test",
        metadata={"recipient_type": "client"},
    )
    out = run_deliver(workspace, max_items_per_run=5)
    assert out["report"]["summary"]["blocked_by_policy"] == 1


def test_tool_allow_deny_per_agent_negative(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    policy = {
        "version": 1,
        "tool_policy": {
            "default": {"allow": ["*"], "deny": []},
            "agents": {"agent_x": {"allow": ["status.check"], "deny": ["odoo.cotizar"]}},
        },
    }
    (workspace / "state" / "runtime_guardrails_policy.json").write_text(json.dumps(policy), encoding="utf-8")
    out = run_nl_router(workspace, text="cotizar", channel="whatsapp", agent_id="agent_x")
    assert out["status"] == "success"
    assert out["plan"]["tool_policy"]["allowed"] is False
    assert out["plan"]["selected_target"] == "rag.answer"


def test_no_leak_redaction_removes_attachments():
    report = {
        "event": {"attachments": [{"path": "/tmp/a.pdf"}]},
        "attachments": [{"path": "/tmp/a.pdf"}],
        "media": ["x"],
        "files": ["y"],
    }
    out = redact_no_leak_report(report)
    assert out["event"]["attachments"] == []
    assert out["attachments"] == []
    assert out["media"] == []
    assert out["files"] == []


def test_no_leak_outbox_archive_omits_tool_outputs(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    enqueue_message(
        workspace,
        channel="telegram_owner",
        target="owner",
        text="hola",
        source_ref="runtime:s1",
        metadata={"recipient_type": "owner"},
    )

    import scripts.outbox_delivery as outbox_delivery

    def _fake_send(channel: str, target: str, text: str, timeout_seconds: int = 10):
        return {"ok": True, "reason": "sent", "cmd": ["openclaw", "message", "send"], "returncode": 0, "stdout": "x", "stderr": "y"}

    monkeypatch.setattr(outbox_delivery, "send_message", _fake_send)
    out = run_deliver(workspace, max_items_per_run=5)
    archive_path = workspace / out["report"]["archive"]["ndjson_path"]
    line = archive_path.read_text(encoding="utf-8").splitlines()[0]
    row = json.loads(line)
    assert "stdout" not in json.dumps(row)
    assert "stderr" not in json.dumps(row)

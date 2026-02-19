import json
from pathlib import Path

from scripts.hook_backlog import append_event, run_replay, run_scan
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / ".openclaw").mkdir(parents=True, exist_ok=True)
    (root / ".openclaw" / "CANONICAL_ROOT.json").write_text(
        json.dumps({"root_realpath": str(root.resolve())}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def _payload(message_id: str = "m1") -> dict:
    return {
        "type": "message",
        "action": "received",
        "timestamp": "2026-02-19T02:00:00+00:00",
        "sessionKey": "sess-1",
        "context": {
            "workspaceDir": "",
            "channelId": "telegram",
            "accountId": "acc",
            "conversationId": "conv-1",
            "messageId": message_id,
            "timestamp": "2026-02-19T02:00:00+00:00",
            "content": "hola mundo",
            "attachments": [],
            "metadata": {"threadId": "", "channelName": "dm"},
        },
    }


def test_hook_backlog_append_and_scan_deterministic(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = append_event(workspace, _payload("m-1"))
    assert out["status"] == "queued"
    first = run_scan(workspace)["report"]["summary"]
    second = run_scan(workspace)["report"]["summary"]
    assert first == second
    assert first["pending_count"] == 1


def test_hook_backlog_replay_processes_and_archives(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    append_event(workspace, _payload("m-1"))
    append_event(workspace, _payload("m-2"))

    monkeypatch.setattr(
        "scripts.channel_ingress_adapter.handle_runtime_event",
        lambda _root, _event: {"status": "success", "session_id": "sid_test"},
    )

    out = run_replay(workspace, max_events=10, max_runtime_seconds=5)
    report = out["report"]
    assert report["summary"]["processed_count"] == 2
    assert report["summary"]["pending_count"] == 0
    assert report["archive"]["item_count"] == 2
    assert (workspace / report["archive"]["manifest_path"]).is_file()

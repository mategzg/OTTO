import json
from pathlib import Path

from scripts.outbox_delivery import run_deliver, run_scan
from scripts.repo_root import set_canonical_root
from scripts.telegram_delivery import send_message


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_outbox_queue_scan_and_delivery_with_mock_cli(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "owner_chat")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    send_message(workspace, "mensaje 1")
    send_message(workspace, "mensaje 2")

    scan = run_scan(workspace)
    assert scan["report"]["summary"]["queue_pending"] >= 2

    import scripts.outbox_delivery as outbox_delivery

    def _fake_send(channel: str, target: str, text: str, timeout_seconds: int = 10):
        return {"ok": True, "reason": "sent", "cmd": ["openclaw", "message", "send"], "returncode": 0}

    monkeypatch.setattr(outbox_delivery, "send_message", _fake_send)
    delivered = run_deliver(workspace, max_items_per_run=10)
    assert delivered["report"]["summary"]["delivered_in_run"] >= 2
    assert delivered["report"]["archive"]["ndjson_path"]
    assert delivered["report"]["archive"]["manifest_path"]

    latest = json.loads((workspace / "docs" / "_inbox" / "outbox_delivery_report_latest.json").read_text(encoding="utf-8"))
    assert latest["summary"]["queue_pending"] == 0
    assert (workspace / latest["archive"]["ndjson_path"]).is_file()
    assert (workspace / latest["archive"]["manifest_path"]).is_file()


def test_outbox_delivery_keeps_pending_when_target_missing(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    send_message(workspace, "mensaje sin target", chat_id="", token="")
    out = run_deliver(workspace, max_items_per_run=5)
    assert out["report"]["summary"]["missing_target"] >= 1
    assert out["report"]["summary"]["queue_pending"] >= 1

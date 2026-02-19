import json
from pathlib import Path

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


def _materialized_state(queue_path: Path) -> dict:
    if not queue_path.is_file():
        return {}
    state = {}
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        row = json.loads(text)
        rid = str(row.get("id", ""))
        if not rid:
            continue
        if row.get("event_type") == "enqueue":
            state[rid] = row
        elif row.get("event_type") == "delivery" and rid in state:
            state[rid]["status"] = row.get("status", state[rid].get("status"))
    return state


def test_telegram_delivery_dry_run(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = send_message(workspace, "hola owner", dry_run=True)
    assert out["sent"] is False
    assert out["queued"] is False
    assert out["reason"] == "dry_run"


def test_telegram_delivery_queues_message_even_without_credentials(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    out = send_message(workspace, "mensaje sin credenciales", dry_run=False)
    assert out["queued"] is True
    assert out["reason"] == "queued_for_delivery"
    assert out["queue_path"] == "docs/_inbox/outbox_queue.ndjson"
    assert (workspace / "docs" / "_inbox" / "outbox_latest.md").is_file()
    queue = workspace / "docs" / "_inbox" / "outbox_queue.ndjson"
    state = _materialized_state(queue)
    assert len(state) == 1
    item = next(iter(state.values()))
    assert item["channel"] == "telegram_owner"
    assert item["target"] == ""


def test_telegram_delivery_queues_with_target_from_env(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat123")
    out = send_message(workspace, "mensaje en cola", dry_run=False)
    assert out["queued"] is True
    queue = workspace / "docs" / "_inbox" / "outbox_queue.ndjson"
    state = _materialized_state(queue)
    item = next(iter(state.values()))
    assert item["target"] == "chat123"
    log_payload = json.loads((workspace / "logs" / "telegram_delivery_latest.json").read_text(encoding="utf-8"))
    assert log_payload["queued"] is True

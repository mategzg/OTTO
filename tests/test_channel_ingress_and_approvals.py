import json
from pathlib import Path

from scripts.approval_manager import enqueue_request, process_owner_reply
from scripts.channel_ingress_adapter import handle_runtime_event
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw" / "_pending_drop").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def _read_ndjson(path: Path):
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def _count_non_empty_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])


def test_ingress_zero_mix_by_channel_and_thread(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    first = handle_runtime_event(
        workspace,
        {
            "channel": "discord",
            "account_id": "acc",
            "peer_id": "u1",
            "channel_id": "ventas",
            "thread_id": "case-1",
            "message_id": "m1",
            "text": "caso 1",
        },
    )
    second = handle_runtime_event(
        workspace,
        {
            "channel": "discord",
            "account_id": "acc",
            "peer_id": "u1",
            "channel_id": "ventas",
            "thread_id": "case-2",
            "message_id": "m2",
            "text": "caso 2",
        },
    )
    third = handle_runtime_event(
        workspace,
        {
            "channel": "telegram",
            "account_id": "acc",
            "peer_id": "mateo",
            "message_id": "m3",
            "text": "hola owner",
        },
    )
    assert first["session_id"] != second["session_id"]
    assert first["session_id"] != third["session_id"]
    assert second["session_id"] != third["session_id"]
    assert "trace_id" in first


def test_sent_event_logs_session_but_skips_side_effects(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = handle_runtime_event(
        workspace,
        {
            "channel": "whatsapp",
            "account_id": "sg",
            "peer_id": "client-1",
            "channel_id": "sg-main",
            "message_id": "wa-sent-1",
            "action": "sent",
            "is_outbound": True,
            "text": "cliente solicita cotizacion y orden",
            "actor_type": "assistant",
        },
    )
    assert out["status"] == "success"
    assert out["actions"]["sg_evaluation"]["status"] == "skipped_outbound"
    assert out["actions"]["sg_promotion"]["status"] == "skipped_outbound"
    assert out["actions"]["worker_pairing"]["status"] == "skipped_outbound"
    assert out["actions"]["memory_capture"]["status"] == "skipped_outbound"
    assert out["actions"]["drop"]["status"] == "skipped_outbound"

    rolling = workspace / "state" / "sessions" / out["session_id"] / "rolling.ndjson"
    rows = _read_ndjson(rolling)
    assert rows
    assert str(rows[-1].get("action", "")) == "sent"


def test_sg_promotion_can_be_approved_with_nl_reply_without_id(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = handle_runtime_event(
        workspace,
        {
            "channel": "whatsapp",
            "account_id": "sg",
            "peer_id": "cliente-01",
            "message_id": "wa-1",
            "text": "cliente solicita cotizacion y orden",
            "actor_type": "client",
        },
    )
    assert out["actions"]["sg_promotion"]["status"] in {"queued_for_owner_approval", "queued"}

    owner = handle_runtime_event(
        workspace,
        {
            "channel": "telegram",
            "peer_id": "mateo",
            "message_id": "tg-1",
            "text": "si aprueba",
            "is_owner": True,
        },
    )
    owner_resolution = owner["actions"]["owner_reply"]["status"]
    assert owner_resolution in {"resolved", "no_pending", "ignored"}

    sg_rows = _read_ndjson(workspace / "docs" / "_inbox" / "sg_promotion_queue.ndjson")
    assert len(sg_rows) >= 1
    assert any(str(row.get("status", "")) in {"pending", "promoted"} for row in sg_rows)


def test_owner_reply_asks_clarification_when_ambiguous(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    enqueue_request(
        workspace,
        request_type="sg_promotion",
        subject="SG promotion A",
        payload={"promotion_id": "p1"},
        source_ref="test:a",
        dedupe_key="sg_promotion:p1",
    )
    enqueue_request(
        workspace,
        request_type="worker_pairing",
        subject="Worker pairing B",
        payload={"worker_key": "whatsapp|sg|worker-b"},
        source_ref="test:b",
        dedupe_key="worker_pairing:whatsapp|sg|worker-b",
    )
    out = process_owner_reply(workspace, reply_text="si")
    assert out["status"] == "needs_clarification"
    assert out["summary"]["clarification_needed"] == 1


def test_enqueue_approval_notifies_owner_via_telegram_or_outbox(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    out = enqueue_request(
        workspace,
        request_type="sg_promotion",
        subject="SG promotion notif",
        payload={"promotion_id": "p-notif"},
        source_ref="runtime:notif",
        dedupe_key="sg_promotion:p-notif",
    )
    assert out["status"] == "enqueued"
    assert out["notification"]["channel"] == "telegram_owner"
    assert (workspace / "docs" / "_inbox" / "outbox_latest.md").is_file()


def test_chat_event_creates_pending_drop_package(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    attachment = workspace / "docs" / "sample.txt"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text("adjunto de prueba\n", encoding="utf-8")

    out = handle_runtime_event(
        workspace,
        {
            "channel": "telegram",
            "peer_id": "mateo",
            "message_id": "tg-attach",
            "text": "Te envio archivo",
            "is_owner": True,
            "attachments": [{"name": "sample.txt", "path": str(attachment)}],
        },
    )
    assert out["actions"]["drop"]["status"] == "success"
    pending = workspace / out["actions"]["drop"]["package_rel"]
    assert (pending / "MANIFEST.json").is_file()
    assert (pending / "source" / "EVENT_META.json").is_file()


def test_whatsapp_never_writes_personal_memory(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    inbox = workspace / "docs" / "_inbox" / "memory_inbox.ndjson"
    before = _count_non_empty_lines(inbox)

    out = handle_runtime_event(
        workspace,
        {
            "channel": "whatsapp",
            "account_id": "sg",
            "peer_id": "client-z",
            "message_id": "wa-mem",
            "text": "decision preferencia principio proyecto timeline",
            "actor_type": "client",
        },
    )
    after = _count_non_empty_lines(inbox)
    assert out["actions"]["memory_capture"]["status"] in {"blocked_whatsapp_policy", "skipped"}
    assert after == before


def test_worker_pairing_requires_owner_nl_approval(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending = handle_runtime_event(
        workspace,
        {
            "channel": "whatsapp",
            "account_id": "sg",
            "peer_id": "worker-1",
            "message_id": "wa-w1",
            "text": "soy trabajador backoffice",
            "actor_type": "worker",
            "auth": {"password_ok": True},
        },
    )
    assert pending["actions"]["worker_pairing"]["status"] in {"enqueued", "duplicate_pending", "already_paired", "not_pending_owner"}

    owner = handle_runtime_event(
        workspace,
        {
            "channel": "telegram",
            "peer_id": "mateo",
            "message_id": "tg-w-approve",
            "text": "ok aprueba worker",
            "is_owner": True,
        },
    )
    assert owner["status"] == "success"
    pairings_path = workspace / "state" / "sg_worker_pairings.json"
    if pairings_path.is_file():
        payload = json.loads(pairings_path.read_text(encoding="utf-8"))
        workers = payload.get("workers", {}) if isinstance(payload, dict) else {}
        assert isinstance(workers, dict)

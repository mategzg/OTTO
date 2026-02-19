import json
import shutil
import subprocess
from pathlib import Path

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


def _openclaw_payload(action: str, *, thread_id: str = ""):
    return {
        "type": "message",
        "action": action,
        "timestamp": "2026-02-18T10:00:00+00:00",
        "sessionKey": "sess-openclaw-1",
        "context": {
            "workspaceDir": "",
            "channelId": "discord",
            "accountId": "acc-discord",
            "conversationId": "conv-100",
            "messageId": f"m-{action}-{thread_id or 'main'}",
            "timestamp": "2026-02-18T10:00:01+00:00",
            "content": f"content-{action}-{thread_id or 'main'}",
            "metadata": {
                "threadId": thread_id,
                "senderId": "user-1",
                "senderName": "Mateo",
                "channelName": "#Finanzas",
            },
        },
    }


def test_openclaw_received_thread_changes_session_id(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    no_thread = handle_runtime_event(workspace, _openclaw_payload("received", thread_id=""))
    with_thread = handle_runtime_event(workspace, _openclaw_payload("received", thread_id="thread-777"))
    assert no_thread["session_id"] != with_thread["session_id"]
    assert with_thread["event"]["domain_slug"] == "finanzas"


def test_openclaw_sent_is_appended_to_same_session(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    received = handle_runtime_event(workspace, _openclaw_payload("received", thread_id="thread-1"))
    sent = handle_runtime_event(workspace, _openclaw_payload("sent", thread_id="thread-1"))
    assert received["session_id"] == sent["session_id"]

    rolling = workspace / "state" / "sessions" / received["session_id"] / "rolling.ndjson"
    rows = _read_ndjson(rolling)
    assert len(rows) >= 2
    actions = [str(item.get("action", "")) for item in rows[-2:]]
    assert actions == ["received", "sent"]


def test_workspace_hook_files_exist_with_expected_shape():
    root = Path(__file__).resolve().parents[1]
    hook_md = root / "hooks" / "otto-runtime-bridge" / "HOOK.md"
    handler = root / "hooks" / "otto-runtime-bridge" / "handler.js"
    assert hook_md.is_file()
    assert handler.is_file()
    hook_text = hook_md.read_text(encoding="utf-8").lower()
    handler_text = handler.read_text(encoding="utf-8").lower()
    assert "message:received" in hook_text
    assert "message:sent" in hook_text
    assert "channel_ingress_adapter.py" in handler_text


def test_workspace_hook_handler_appends_backlog_even_when_fast_path_not_available(tmp_path: Path, monkeypatch):
    if shutil.which("node") is None:
        return
    workspace = _setup(tmp_path, monkeypatch)
    # Ensure fast-path script is missing so callback path fails, but backlog append should still happen.
    missing_script = workspace / "scripts" / "channel_ingress_adapter.py"
    if missing_script.exists():
        missing_script.unlink()

    handler_path = Path(__file__).resolve().parents[1] / "hooks" / "otto-runtime-bridge" / "handler.js"
    event = {
        "type": "message",
        "action": "received",
        "timestamp": "2026-02-19T02:00:00+00:00",
        "sessionKey": "hook-sess",
        "context": {
            "workspaceDir": str(workspace),
            "channelId": "telegram",
            "accountId": "acc",
            "conversationId": "conv-hook",
            "messageId": "msg-hook",
            "content": "hello from hook",
            "metadata": {"threadId": "", "channelName": "dm"},
        },
    }
    js = (
        "const h=require(process.argv[1]);"
        "const ev=JSON.parse(process.argv[2]);"
        "Promise.resolve(h(ev)).then(()=>setTimeout(()=>process.exit(0),120));"
    )
    subprocess.run(["node", "-e", js, str(handler_path), json.dumps(event)], check=True)

    backlog = workspace / "state" / "hook_backlog" / "events.ndjson"
    assert backlog.is_file()
    lines = [line for line in backlog.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines

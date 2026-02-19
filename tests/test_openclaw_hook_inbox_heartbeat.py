from pathlib import Path

from scripts import openclaw_hook
from scripts.repo_root import set_canonical_root


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


def test_openclaw_hook_inbox_and_heartbeat_commands(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    pending = workspace / "vault" / "inbox_raw" / "_pending_drop"
    (pending / "inbox.txt").write_text("hello", encoding="utf-8")

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    status = openclaw_hook.handle_repo_command("/inbox status", root=workspace)
    assert status["ok"] is True

    intake = openclaw_hook.handle_repo_command("/inbox intake", root=workspace)
    assert intake["ok"] is True

    normalize = openclaw_hook.handle_repo_command("/inbox normalize", root=workspace)
    assert normalize["ok"] is True

    run_hb = openclaw_hook.handle_repo_command("/heartbeat run", root=workspace)
    assert run_hb["ok"] is True

    hb_status = openclaw_hook.handle_repo_command("/heartbeat status", root=workspace)
    assert hb_status["ok"] is True

    outbox = workspace / "docs" / "_inbox" / "outbox_latest.md"
    assert outbox.is_file()

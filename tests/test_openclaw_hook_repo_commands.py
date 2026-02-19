from pathlib import Path

from scripts import openclaw_hook
from scripts.repo_root import set_canonical_root


def _mk_markers(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / ".git").mkdir(parents=True, exist_ok=True)


def _setup_home(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / ".openclaw" / "workspace"
    _mk_markers(workspace)
    monkeypatch.setenv("HOME", str(home))
    return home, workspace


def test_repo_roots_and_setroot(monkeypatch, tmp_path: Path):
    home, workspace = _setup_home(tmp_path, monkeypatch)

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    roots = openclaw_hook.handle_repo_command("/repo roots", root=workspace)
    assert roots["ok"] is True
    roots_again = openclaw_hook.handle_repo_command("/repo roots", root=workspace)
    assert [x["candidate_id"] for x in roots["candidates"]] == [x["candidate_id"] for x in roots_again["candidates"]]

    safe = [c for c in roots["candidates"] if c["safe_for_pin"]]
    assert safe

    setroot = openclaw_hook.handle_repo_command(f"/repo setroot {safe[0]['candidate_id']}", root=workspace)
    assert setroot["ok"] is True
    assert "Root limpio pinneado" in setroot["message"]


def test_repo_salvage_and_apply(monkeypatch, tmp_path: Path):
    home, workspace = _setup_home(tmp_path, monkeypatch)
    set_canonical_root(workspace, created_by="test")

    ghost = home / "C:\\Users\\demo"
    _mk_markers(ghost)
    (ghost / "docs").mkdir(parents=True, exist_ok=True)
    (ghost / "docs" / "new.md").write_text("new", encoding="utf-8")

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    salvage = openclaw_hook.handle_repo_command("/repo salvage", root=workspace)
    assert salvage["ok"] is True

    apply_salvage = openclaw_hook.handle_repo_command("/repo apply-salvage", root=workspace)
    assert apply_salvage["ok"] is True
    assert (workspace / "docs" / "new.md").is_file()


def test_repo_fix_runs_end_to_end(monkeypatch, tmp_path: Path):
    home, workspace = _setup_home(tmp_path, monkeypatch)
    set_canonical_root(workspace, created_by="test")

    ghost = home / "C:\\Users\\demo"
    _mk_markers(ghost)

    backup = home / "_OLD_BAD_PATH_BACKUP.bak_1"
    _mk_markers(backup)

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    result = openclaw_hook.handle_repo_command("/repo fix", root=workspace)
    assert result["ok"] is True
    assert result["summary"]["pending_count"] == 0


def test_repo_fix_requires_pinned(monkeypatch, tmp_path: Path):
    home, workspace = _setup_home(tmp_path, monkeypatch)

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    result = openclaw_hook.handle_repo_command("/repo fix", root=workspace)
    assert result["ok"] is False


def test_unknown_command(monkeypatch, tmp_path: Path):
    home, workspace = _setup_home(tmp_path, monkeypatch)

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})
    result = openclaw_hook.handle_repo_command("/repo nope", root=workspace)
    assert result["ok"] is False


def test_context_surface_and_fix_commands(monkeypatch, tmp_path: Path):
    home, workspace = _setup_home(tmp_path, monkeypatch)
    set_canonical_root(workspace, created_by="test")

    (workspace / "brain" / "AGENTS.md").write_text("nested drift", encoding="utf-8")
    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    scan = openclaw_hook.handle_repo_command("/context surface", root=workspace)
    assert scan["ok"] is True
    assert scan["summary"]["drift_grave_count"] >= 1

    fix = openclaw_hook.handle_repo_command("/context fix", root=workspace)
    assert fix["ok"] is True
    assert fix["summary"]["drift_grave_count"] == 0
    assert not (workspace / "brain" / "AGENTS.md").exists()

    status = openclaw_hook.handle_repo_command("/context status", root=workspace)
    assert status["ok"] is True
    assert status["summary"]["drift_count"] == 0

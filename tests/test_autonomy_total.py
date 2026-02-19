from pathlib import Path

from scripts import openclaw_hook
from scripts.autonomy_tick import autonomy_pause, autonomy_resume, run_autonomy_tick
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw").mkdir(parents=True, exist_ok=True)


def _mk_source(root: Path, name: str = "auto_source") -> None:
    src = root / "vault" / "inbox_raw" / name
    src.mkdir(parents=True, exist_ok=True)
    (src / "notes.md").write_text("openclaw repo operations and routing\n", encoding="utf-8")


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_autonomy_tick_processes_pending_then_idle(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _mk_source(workspace)

    send = lambda _msg: {"ok": False, "sent": False, "reason": "missing_config"}
    first = run_autonomy_tick(root=workspace, force=True, max_sources_per_tick=1, send_func=send)
    assert first["status"] == "success"
    assert first["processed_ids"]
    assert (workspace / "docs" / "_inbox" / "autonomy_latest.json").is_file()
    assert (workspace / "logs" / "autonomy_latest.json").is_file()

    second = run_autonomy_tick(root=workspace, force=True, max_sources_per_tick=1, send_func=send)
    assert second["status"] == "idle"


def test_autonomy_pause_resume(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    send = lambda _msg: {"ok": False, "sent": False, "reason": "missing_config"}

    pause = autonomy_pause(workspace, hours=1)
    assert pause["ok"] is True

    paused = run_autonomy_tick(root=workspace, force=False, send_func=send)
    assert paused["status"] == "paused"

    resume = autonomy_resume(workspace)
    assert resume["ok"] is True

    resumed = run_autonomy_tick(root=workspace, force=False, send_func=send)
    assert resumed["status"] in {"idle", "success"}


def test_openclaw_hook_autonomy_commands(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _mk_source(workspace, "hook_auto")

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    status = openclaw_hook.handle_repo_command("/autonomy status", root=workspace)
    assert status["ok"] is True

    pause = openclaw_hook.handle_repo_command("/autonomy pause 1", root=workspace)
    assert pause["ok"] is True

    resume = openclaw_hook.handle_repo_command("/autonomy resume", root=workspace)
    assert resume["ok"] is True

    run_now = openclaw_hook.handle_repo_command("/autonomy run", root=workspace)
    assert run_now["ok"] is True

    last = openclaw_hook.handle_repo_command("/autonomy last", root=workspace)
    assert last["ok"] is True


def test_autonomy_tick_preflight_surface_fix(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _mk_source(workspace, "surface_case")
    (workspace / "brain" / "AGENTS.md").write_text("drift", encoding="utf-8")

    send = lambda _msg: {"ok": False, "sent": False, "reason": "missing_config"}
    out = run_autonomy_tick(root=workspace, force=True, max_sources_per_tick=1, send_func=send)

    assert out["status"] in {"success", "idle"}
    assert out["surface_scan"]["summary"]["drift_grave_count"] == 0
    assert out["surface_scan"].get("fix_actions")
    assert not (workspace / "brain" / "AGENTS.md").exists()

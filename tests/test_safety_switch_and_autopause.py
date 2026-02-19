import json
from pathlib import Path

from scripts.autonomy_tick import run_autonomy_tick
from scripts.heartbeat_worker import run_heartbeat_once
from scripts.repo_root import set_canonical_root
from scripts.safety_switch import get_safety_status, pause_switch, resume_switch


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


def test_safety_switch_pause_resume_roundtrip(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    paused = pause_switch(workspace, hours=1, reason="test_pause", set_by="manual")
    assert paused["paused"] is True
    assert "test_pause" in paused["reason"]

    resumed = resume_switch(workspace, reason="test_resume", set_by="manual")
    assert resumed["paused"] is False
    status = get_safety_status(workspace, auto_expire=True)
    assert status["paused"] is False


def test_heartbeat_respects_safety_pause(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pause_switch(workspace, hours=1, reason="safety_hold", set_by="manual")
    out = run_heartbeat_once(workspace, force=True)
    assert out["report"]["status"] == "paused_safety"


def test_autonomy_tick_respects_safety_pause(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pause_switch(workspace, hours=1, reason="safety_hold", set_by="manual")
    out = run_autonomy_tick(root=workspace, force=False)
    assert out["status"] == "paused_safety"

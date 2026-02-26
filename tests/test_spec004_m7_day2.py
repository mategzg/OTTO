from __future__ import annotations

from pathlib import Path

from scripts.day2_autonomy import cron_session_id, heartbeat_reply, run_fault_injection
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    for d in ("openclaw", "scripts", "ops", "brain", "docs/_inbox", "logs", "state", "audit/M7"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_heartbeat_ok_when_no_alert():
    assert heartbeat_reply(False) == "HEARTBEAT_OK"


def test_cron_session_id_format():
    assert cron_session_id("sharepoint-sync") == "cron:sharepoint-sync"


def test_fault_injection_opens_cron_breaker(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    out = run_fault_injection(w)
    assert out["status"] == "ok"
    assert out["after"]["cron_jobs"]["allowed"] is False

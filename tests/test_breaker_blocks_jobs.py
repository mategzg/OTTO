from pathlib import Path

from scripts.heartbeat_worker import run_heartbeat_once
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


def test_breaker_open_skips_delegation_and_marks_job_status(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)

    import scripts.heartbeat_worker as hw

    monkeypatch.setattr(hw, "run_outbox_deliver", lambda *_a, **_k: {"report": {"summary": {"queue_pending": 0, "delivered_in_run": 0, "failed_in_run": 0}}, "paths": {}})
    monkeypatch.setattr(hw, "run_hook_backlog_scan", lambda *_a, **_k: {"report": {"summary": {"pending_count": 0}}, "paths": {}})
    monkeypatch.setattr(hw, "run_prod_doctor", lambda *_a, **_k: {"report": {"status": "ok", "summary": {}, "go_no_go": "go"}, "paths": {}})
    monkeypatch.setattr(hw, "delegate_to_coder", lambda *_a, **_k: {"status": "delegated", "coder_used": "codex", "items_delegated": 1, "active_mission_id": "x"})

    def _fake_should_allow(_root, *, resource: str):
        if resource == "cron_jobs":
            return {"allowed": False, "status": "open", "reason": "cooldown"}
        if resource == "retrieval":
            return {"allowed": False, "status": "open", "reason": "cooldown"}
        if resource == "tooling":
            return {"allowed": False, "status": "open", "reason": "cooldown"}
        return {"allowed": True, "status": "closed"}

    monkeypatch.setattr(hw, "should_allow", _fake_should_allow)

    out = run_heartbeat_once(workspace, force=True)
    summary = out["report"]["summary"]

    assert summary["delegation_status"] == "cooldown_skip"
    assert summary["research_status"] == "skipped_cooldown"
    assert summary["odoo_status"] == "skipped_cooldown"
    assert summary["breaker_cron_jobs_allowed"] is False

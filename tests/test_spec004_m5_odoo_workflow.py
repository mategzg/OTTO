from __future__ import annotations

from pathlib import Path

from scripts.odoo_workflow import run_flow
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    for d in ("openclaw", "scripts", "ops", "brain", "docs/_inbox", "logs", "state", "audit/M5"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_dry_run_before_side_effects(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    out = run_flow(w, lead_id="L1", dry_run=True)
    assert out["status"] == "dry_run"
    assert out["handoff"]["state"] == "AwaitApproval"


def test_block_without_approval(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    out = run_flow(w, lead_id="L2", dry_run=False, approved=False)
    assert out["status"] == "awaiting_approval"
    assert out["blocked_without_approval"] is True


def test_requires_valid_resume_token(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    await_out = run_flow(w, lead_id="L3", dry_run=False, approved=False)
    bad = run_flow(w, lead_id="L3", dry_run=False, approved=True, resume_token="wrong")
    assert bad["status"] == "invalid_resume_token"
    ok = run_flow(w, lead_id="L3", dry_run=False, approved=True, resume_token=await_out["handoff"]["resume_token"])
    assert ok["status"] == "completed"


def test_idempotency_key_stable(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    a = run_flow(w, lead_id="L4", dry_run=True)
    b = run_flow(w, lead_id="L4", dry_run=True)
    assert a["idempotency_key"] == b["idempotency_key"]

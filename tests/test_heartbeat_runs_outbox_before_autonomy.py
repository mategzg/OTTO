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


def test_heartbeat_runs_outbox_delivery_before_autonomy(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    call_order = []

    import scripts.heartbeat_worker as hw

    def _fake_outbox(*args, **kwargs):
        call_order.append("outbox")
        return {
            "report": {"summary": {"queue_pending": 1, "delivered_in_run": 1, "failed_in_run": 0}},
            "paths": {"markdown": "docs/_inbox/outbox_delivery_report_latest.md"},
        }

    def _fake_autonomy(*args, **kwargs):
        call_order.append("autonomy")
        return {"status": "idle", "paths": {"markdown": "docs/_inbox/autonomy_latest.md"}}

    def _fake_backlog_scan(*args, **kwargs):
        call_order.append("backlog_scan")
        return {"report": {"summary": {"pending_count": 0}}, "paths": {"markdown": "docs/_inbox/hook_backlog_report_latest.md"}}

    def _fake_backlog_replay(*args, **kwargs):
        call_order.append("backlog_replay")
        return {"report": {"summary": {"pending_count": 0, "selected_count": 0, "failed_count": 0}, "state": {"consecutive_failures": 0, "stall_ticks": 0}}, "paths": {"markdown": "docs/_inbox/hook_backlog_report_latest.md"}}

    def _fake_prod_doctor(*args, **kwargs):
        call_order.append("prod_doctor")
        return {"report": {"status": "ok", "summary": {}}, "paths": {"markdown": "docs/_inbox/prod_doctor_latest.md"}}

    monkeypatch.setattr(hw, "run_outbox_deliver", _fake_outbox)
    monkeypatch.setattr(hw, "run_hook_backlog_scan", _fake_backlog_scan)
    monkeypatch.setattr(hw, "run_hook_backlog_replay", _fake_backlog_replay)
    monkeypatch.setattr(hw, "run_prod_doctor", _fake_prod_doctor)
    monkeypatch.setattr(hw, "run_autonomy_tick", _fake_autonomy)

    out = run_heartbeat_once(workspace, force=True)
    assert out["report"]["status"] in {"success", "partial"}
    assert call_order.index("outbox") < call_order.index("autonomy")
    assert call_order.index("backlog_replay") < call_order.index("autonomy")

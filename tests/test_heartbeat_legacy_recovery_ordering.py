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


def test_heartbeat_runs_legacy_recovery_before_autonomy(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    call_order = []

    import scripts.heartbeat_worker as hw

    monkeypatch.setattr(
        hw,
        "run_outbox_deliver",
        lambda *_args, **_kwargs: call_order.append("outbox")
        or {"report": {"summary": {"queue_pending": 0, "delivered_in_run": 0, "failed_in_run": 0}}},
    )
    monkeypatch.setattr(
        hw,
        "run_project_docs_apply",
        lambda *_args, **_kwargs: call_order.append("project_docs")
        or {"report": {"status": "no_change", "updated_files": [], "paths": {}}},
    )
    monkeypatch.setattr(
        hw,
        "run_hook_backlog_scan",
        lambda *_args, **_kwargs: call_order.append("backlog_scan")
        or {"report": {"summary": {"pending_count": 0}}},
    )
    monkeypatch.setattr(
        hw,
        "run_hook_backlog_replay",
        lambda *_args, **_kwargs: call_order.append("backlog_replay")
        or {
            "report": {
                "summary": {"pending_count": 0, "selected_count": 0, "failed_count": 0},
                "state": {"consecutive_failures": 0, "stall_ticks": 0},
            }
        },
    )
    monkeypatch.setattr(
        hw,
        "run_legacy_recovery_once",
        lambda *_args, **_kwargs: call_order.append("legacy_recovery")
        or {
            "report": {
                "status": "disabled",
                "summary": {
                    "selected_count": 0,
                    "packaged_count": 0,
                    "blocked_count": 0,
                    "legacy_scan_ran": False,
                    "legacy_disabled_reason": "policy_disabled",
                },
            }
        },
    )
    monkeypatch.setattr(hw, "run_intake_scan", lambda *_args, **_kwargs: {"report": {"summary": {}}})
    monkeypatch.setattr(hw, "run_intake_apply", lambda *_args, **_kwargs: {"report": {"apply": {"ingested": [], "ingested_count": 0}}})
    monkeypatch.setattr(hw, "run_normalize", lambda *_args, **_kwargs: {"report": {"summary": {"normalized_count": 0, "slice_count": 0}}})
    monkeypatch.setattr(
        hw,
        "run_session_maintenance",
        lambda *_args, **_kwargs: call_order.append("runtime")
        or {"summary": {"sessions_touched": 0, "compactions_done": 0, "distills_done": 0}},
    )
    monkeypatch.setattr(hw, "process_pending_approvals", lambda *_args, **_kwargs: {"summary": {}, "delivery": {"sent": False, "reason": "none"}})
    monkeypatch.setattr(hw, "process_promotions", lambda *_args, **_kwargs: {"summary": {}})
    monkeypatch.setattr(hw, "run_prod_doctor", lambda *_args, **_kwargs: {"report": {"status": "ok", "summary": {}}})
    monkeypatch.setattr(
        hw,
        "run_autonomy_tick",
        lambda *_args, **_kwargs: call_order.append("autonomy") or {"status": "idle", "paths": {}},
    )

    out = run_heartbeat_once(workspace, force=True)
    assert out["report"]["status"] in {"success", "partial"}
    assert call_order.index("legacy_recovery") < call_order.index("autonomy")
    assert call_order.index("legacy_recovery") > call_order.index("backlog_replay")
    assert out["report"]["summary"]["legacy_scan_ran"] is False
    assert out["report"]["summary"]["legacy_disabled_reason"] == "policy_disabled"

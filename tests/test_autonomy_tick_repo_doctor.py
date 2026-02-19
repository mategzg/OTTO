from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.autonomy_tick import run_repo_reality_doctor_job
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


def test_autonomy_job_alerts_when_not_pinned(tmp_path: Path, monkeypatch):
    home, workspace = _setup_home(tmp_path, monkeypatch)

    sent = []

    def fake_send(msg: str):
        sent.append(msg)
        return {"ok": True, "sent": True}

    # Without pin, get_canonical_root may still resolve, but root_drift should alert.
    out = run_repo_reality_doctor_job(
        root=workspace,
        now=datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc),
        interval_hours=24,
        dedupe_hours=24,
        send_func=fake_send,
    )
    assert out["status"] == "ok"
    assert len(sent) >= 1


def test_autonomy_job_no_alert_when_pinned_and_clean(tmp_path: Path, monkeypatch):
    home, workspace = _setup_home(tmp_path, monkeypatch)
    set_canonical_root(workspace, created_by="test")

    sent = []

    def fake_send(msg: str):
        sent.append(msg)
        return {"ok": True, "sent": True}

    out = run_repo_reality_doctor_job(
        root=workspace,
        now=datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc),
        interval_hours=24,
        dedupe_hours=24,
        send_func=fake_send,
    )
    assert out["status"] == "ok"
    assert out["summary"]["pending_count"] == 0
    assert sent == []


def test_autonomy_job_dedupes_and_respects_interval(tmp_path: Path, monkeypatch):
    home, workspace = _setup_home(tmp_path, monkeypatch)
    set_canonical_root(workspace, created_by="test")

    ghost = home / "C:\\Users\\demo"
    _mk_markers(ghost)

    sent = []

    def fake_send(msg: str):
        sent.append(msg)
        return {"ok": True, "sent": True}

    t0 = datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc)
    out1 = run_repo_reality_doctor_job(root=workspace, now=t0, interval_hours=24, dedupe_hours=24, send_func=fake_send)
    assert out1["status"] == "ok"
    assert len(sent) == 1

    out2 = run_repo_reality_doctor_job(
        root=workspace,
        now=t0 + timedelta(hours=1),
        interval_hours=24,
        dedupe_hours=24,
        send_func=fake_send,
    )
    assert out2["status"] == "skipped_interval"
    assert len(sent) == 1

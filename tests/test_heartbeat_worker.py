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


def test_heartbeat_once_ingests_and_runs_autonomy(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    pending = workspace / "vault" / "inbox_raw" / "_pending_drop"
    (pending / "payload.md").write_text("OpenClaw ops notes", encoding="utf-8")

    out = run_heartbeat_once(workspace, force=True)
    assert out["report"]["status"] == "success"
    assert out["report"]["summary"]["ingested_count"] >= 1
    assert "runtime_summary" in out["report"]
    assert "sg_promotion_summary" in out["report"]
    assert "project_docs_summary" in out["report"]
    assert "project_docs_status" in out["report"]["summary"]
    assert (workspace / "docs" / "_inbox" / "heartbeat_latest.json").is_file()
    assert (workspace / "logs" / "heartbeat_latest.json").is_file()


def test_heartbeat_lock(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    lock = workspace / "state" / "heartbeat_worker.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("123\n", encoding="utf-8")

    out = run_heartbeat_once(workspace, force=True)
    assert out["report"]["status"] == "locked"

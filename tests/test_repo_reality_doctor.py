from pathlib import Path

from scripts.repo_reality_doctor import (
    apply_salvage_plan,
    build_salvage_plan,
    run_doctor,
    run_full_fix,
)
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


def _mk_home_workspace(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / ".openclaw" / "workspace"
    _mk_markers(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return home, workspace


def test_detect_pathlike_and_backup_candidates(tmp_path: Path, monkeypatch):
    home, workspace = _mk_home_workspace(tmp_path, monkeypatch)

    bad = home / "C:\\Users\\demo"
    _mk_markers(bad)

    backup = home / "_OLD_BAD_PATH_BACKUP.bak_1"
    _mk_markers(backup)

    report = run_doctor(workspace, apply=False, max_depth=5)
    types = {item["candidate_type"] for item in report["candidates"]}

    assert "pathlike_folder" in types
    assert "old_backup_root" in types


def test_salvage_manifest_and_conflict_policy(tmp_path: Path, monkeypatch):
    home, workspace = _mk_home_workspace(tmp_path, monkeypatch)

    (workspace / "docs").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "same.md").write_text("existing", encoding="utf-8")

    bad = home / "C:\\Users\\demo"
    _mk_markers(bad)
    (bad / "docs").mkdir(parents=True, exist_ok=True)
    (bad / "docs" / "same.md").write_text("different", encoding="utf-8")
    (bad / "docs" / "new.md").write_text("new", encoding="utf-8")

    plan = build_salvage_plan(workspace, max_depth=5)
    assert plan["summary"]["salvage_candidate_count"] >= 1
    assert plan["summary"]["conflict_count"] >= 1

    for item in plan["salvage"]["candidates"]:
        assert Path(item["manifest_path"]).is_file()

    result = apply_salvage_plan(workspace)
    assert result["ok"] is True
    assert (workspace / "docs" / "new.md").is_file()
    assert (workspace / "docs" / "same.md").read_text(encoding="utf-8") == "existing"


def test_run_full_fix_quarantines_candidates(tmp_path: Path, monkeypatch):
    home, workspace = _mk_home_workspace(tmp_path, monkeypatch)

    bad = home / "C:\\Users\\demo"
    _mk_markers(bad)
    (bad / "docs").mkdir(parents=True, exist_ok=True)
    (bad / "docs" / "x.md").write_text("x", encoding="utf-8")

    backup = home / "_OLD_BAD_PATH_BACKUP.bak_1"
    _mk_markers(backup)

    result = run_full_fix(workspace, max_depth=5)
    assert result["status"] == "ok"

    q = workspace / "vault" / "_quarantine"
    assert q.exists()
    readmes = list(q.rglob("README.md"))
    assert readmes

    final = result["report"]
    assert final["summary"]["pending_count"] == 0

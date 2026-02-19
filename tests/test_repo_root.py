from pathlib import Path

import pytest

from scripts import repo_root


def _mk_markers(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)


def test_set_canonical_root_rejects_pathlike(tmp_path: Path):
    bad = tmp_path / "C:\\Users\\demo"
    _mk_markers(bad)

    with pytest.raises(RuntimeError):
        repo_root.set_canonical_root(bad, created_by="test")


def test_propose_clean_root_prefers_clean_candidate(tmp_path: Path):
    clean = tmp_path / "clean_repo"
    _mk_markers(clean)
    (clean / ".git").mkdir()

    bad = tmp_path / "C:\\Users\\demo"
    _mk_markers(bad)
    (bad / ".git").mkdir()

    candidates = repo_root.list_root_candidates(bad)
    clean_rows = [c for c in candidates if c.path == str(clean.resolve())]
    bad_rows = [c for c in candidates if c.path == str(bad.resolve())]

    assert clean_rows and clean_rows[0].clean is True
    assert bad_rows and bad_rows[0].clean is False


def test_get_pinned_root_from_home_workspace_marker(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / ".openclaw" / "workspace"
    workspace.mkdir(parents=True)
    (workspace / ".git").mkdir()

    monkeypatch.setenv("HOME", str(home))
    repo_root.set_canonical_root(workspace, created_by="test")

    foreign_anchor = tmp_path / "elsewhere"
    foreign_anchor.mkdir(parents=True)

    pinned = repo_root.get_pinned_root(foreign_anchor, require_clean=True)
    assert pinned == workspace.resolve()


def test_assert_safe_dir_name_blocks_pathlike():
    with pytest.raises(RuntimeError):
        repo_root.assert_safe_dir_name("C:\\Users\\bad")

    assert repo_root.assert_safe_dir_name("normal_dir") == "normal_dir"

from pathlib import Path

from scripts.dropbox_intake import run_apply, run_scan
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


def test_dropbox_intake_scan_and_apply(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    pending = workspace / "vault" / "inbox_raw" / "_pending_drop"

    (pending / "notes.txt").write_text("hello", encoding="utf-8")
    bundle = pending / "bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "a.md").write_text("# A", encoding="utf-8")

    scan = run_scan(workspace)
    assert scan["report"]["summary"]["pending_count"] == 2
    assert scan["report"]["summary"]["new_count"] == 2

    apply = run_apply(workspace)
    assert apply["report"]["apply"]["ingested_count"] == 2

    sources_root = workspace / "vault" / "inbox_raw" / "sources"
    source_dirs = [p for p in sources_root.iterdir() if p.is_dir()]
    assert source_dirs
    for source_dir in source_dirs:
        assert (source_dir / "MANIFEST.json").is_file()
        assert (source_dir / "HINTS.json").is_file()
        assert (source_dir / "README.md").is_file()

    rescanned = run_scan(workspace)
    assert rescanned["report"]["summary"]["pending_count"] == 0


def test_dropbox_intake_dedupe(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    pending = workspace / "vault" / "inbox_raw" / "_pending_drop"
    (pending / "same.txt").write_text("same", encoding="utf-8")

    first = run_apply(workspace)
    assert first["report"]["apply"]["ingested_count"] == 1

    # Re-add same payload -> deduped by fingerprint
    (pending / "same.txt").write_text("same", encoding="utf-8")
    second_scan = run_scan(workspace)
    assert second_scan["report"]["summary"]["duplicate_count"] >= 1

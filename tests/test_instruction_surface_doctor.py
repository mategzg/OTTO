from pathlib import Path

from scripts.instruction_surface_doctor import run_surface_fix, run_surface_scan
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_surface_scan_detects_allowed_and_drift(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    (workspace / "AGENTS.md").write_text("root wrapper\n", encoding="utf-8")
    (workspace / "brain" / "AGENTS.md").write_text("nested drift\n", encoding="utf-8")

    out = run_surface_scan(workspace)
    summary = out["report"]["summary"]

    assert summary["allowed_count"] == 1
    assert summary["drift_count"] == 1
    assert summary["drift_grave_count"] == 1


def test_surface_fix_quarantines_drift_with_manifest(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    (workspace / "brain" / "CLAUDE.md").write_text("nested drift\n", encoding="utf-8")

    out = run_surface_fix(workspace)
    summary = out["report"]["summary"]
    fix_summary = out["report"]["fix_summary"]

    assert fix_summary["moved_count"] == 1
    assert summary["drift_count"] == 0
    assert summary["drift_grave_count"] == 0
    assert not (workspace / "brain" / "CLAUDE.md").exists()

    quarantine = workspace / "vault" / "_quarantine" / "instruction_drift"
    manifests = sorted(quarantine.rglob("MANIFEST.json"))
    readmes = sorted(quarantine.rglob("README.md"))
    assert manifests
    assert readmes


def test_surface_scan_marks_allowed_dump_as_needs_user(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    (workspace / "AGENTS.md").write_text("x" * 220000, encoding="utf-8")

    out = run_surface_scan(workspace)
    items = out["report"]["items"]
    root_agents = [item for item in items if item["path"] == "AGENTS.md"][0]
    assert root_agents["classification"] == "allowed"
    assert root_agents["needs_user"] is True

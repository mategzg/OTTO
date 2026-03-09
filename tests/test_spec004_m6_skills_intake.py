from __future__ import annotations

import zipfile
from pathlib import Path

from scripts.repo_root import set_canonical_root
from scripts.skills_intake import run_intake


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    for d in ("openclaw", "scripts", "ops", "brain", "docs/_inbox", "logs", "state", "audit/M6"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def _mk_zip(path: Path, files: dict[str, str]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_promotes_valid_skill_pack(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    pack = w / "valid_pack.zip"
    _mk_zip(pack, {"SKILL.md": "# Skill\nopenclaw automation workflow"})
    out = run_intake(w, pack_path=str(pack))
    assert out["status"] == "promoted"


def test_rejects_untrusted_or_invalid_pack(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    pack = w / "bad_pack.zip"
    _mk_zip(pack, {"README.md": "no skill"})
    out = run_intake(w, pack_path=str(pack))
    assert out["status"] == "rejected"


def test_rollback_last_promoted(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    pack = w / "valid_pack.zip"
    _mk_zip(pack, {"SKILL.md": "# Skill\nopenclaw automation workflow"})
    out = run_intake(w, pack_path=str(pack))
    assert out["status"] == "promoted"
    rb = run_intake(w, pack_path="", rollback=True)
    assert rb["status"] == "rolled_back"

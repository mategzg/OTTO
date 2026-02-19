import json
from pathlib import Path

from scripts.capability_inventory import run_scan
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "memory").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "repo_map").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "hooks" / "otto-runtime-bridge").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "_salvage").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "demo.py").write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--scan', action='store_true')\n",
        encoding="utf-8",
    )
    (root / "brain" / "note.md").write_text("# Brain\nruntime memory outbox\n", encoding="utf-8")
    (root / "memory" / "00_INDEX.md").write_text("# memory\n", encoding="utf-8")
    (root / "state" / "channel_runtime_policy.json").write_text("{}", encoding="utf-8")
    (root / "repo_map" / "00_INDEX.md").write_text("# map\n", encoding="utf-8")
    (root / "tests" / "test_stub.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (root / "hooks" / "otto-runtime-bridge" / "HOOK.md").write_text("# hook\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
    (root / "SOUL.md").write_text("# SOUL\n", encoding="utf-8")
    (root / "PROJECT_BRIEF.md").write_text("# brief\n", encoding="utf-8")
    (root / "REPO_MAP.md").write_text("# repomap\n", encoding="utf-8")
    (root / "vault" / "_salvage" / "lost.md").write_text("legacy text\n", encoding="utf-8")


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_capability_inventory_deterministic_and_excludes_coldstore(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = run_scan(workspace)
    report = out["report"]

    assert report["summary"]["items_count"] >= 6
    assert (workspace / "state" / "capability_inventory.json").is_file()
    assert (workspace / "docs" / "_inbox" / "capability_inventory_latest.json").is_file()
    assert (workspace / "logs" / "capability_inventory_latest.json").is_file()

    paths = [item["path"] for item in report["items"]]
    assert "scripts/demo.py" in paths
    assert "brain/note.md" in paths
    assert "vault/_salvage/lost.md" not in paths

    payload = json.loads((workspace / "state" / "capability_inventory.json").read_text(encoding="utf-8"))
    assert payload["summary"]["items_count"] == report["summary"]["items_count"]

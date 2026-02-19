from pathlib import Path

from scripts.legacy_coldstore_audit import run_scan
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "_salvage").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "_quarantine").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_legacy_coldstore_audit_classifies_buckets(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    (workspace / "vault" / "_salvage" / "feature_runtime.md").write_text(
        "new runtime hook router policy\n",
        encoding="utf-8",
    )
    (workspace / "vault" / "_quarantine" / "secret_notes.txt").write_text(
        "api key = abc\n",
        encoding="utf-8",
    )
    (workspace / "vault" / "_quarantine" / "AGENTS.md").write_text("# drift\n", encoding="utf-8")

    out = run_scan(workspace)
    report = out["report"]
    buckets = {item["path"]: item["bucket"] for item in report["items"]}

    assert buckets["vault/_salvage/feature_runtime.md"] == "doc_recoverable"
    assert buckets["vault/_quarantine/secret_notes.txt"] == "sensitive_blocked"
    assert buckets["vault/_quarantine/AGENTS.md"] == "instruction_drift_blocked"
    assert report["summary"]["items_count"] == 3
    assert (workspace / "state" / "legacy_coldstore_index.json").is_file()

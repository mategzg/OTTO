import json
from pathlib import Path

from scripts.legacy_capability_inventory import run_scan
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


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_legacy_capability_inventory_schema_and_counts(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    coldstore = {
        "items": [
            {
                "candidate_id": "x1",
                "path": "vault/_salvage/staged/scripts/new_worker.py",
                "bucket": "code_candidate_review",
                "kind_heuristic": "code",
                "size": 500,
                "sha256": "sha-x1",
                "value_score": 8,
                "value_keywords": ["runtime", "hook"],
                "feature_signature": "sig-x1",
            },
            {
                "candidate_id": "x2",
                "path": "vault/_salvage/staged/brain/domains/new/00_INDEX.md",
                "bucket": "doc_recoverable",
                "kind_heuristic": "doc",
                "size": 200,
                "sha256": "sha-x2",
                "value_score": 6,
                "value_keywords": ["brain", "router"],
                "feature_signature": "sig-x2",
            },
            {
                "candidate_id": "x3",
                "path": "vault/_salvage/staged/docs/_inbox/report_latest.md",
                "bucket": "doc_recoverable",
                "kind_heuristic": "doc",
                "size": 180,
                "sha256": "sha-x3",
                "value_score": 9,
                "value_keywords": ["runtime"],
                "feature_signature": "sig-x3",
            },
        ]
    }
    current = {
        "items": [
            {
                "path": "scripts/new_worker.py",
                "sha256": "sha-x1",
                "kind": "code",
            }
        ]
    }
    (workspace / "state" / "legacy_coldstore_index.json").write_text(
        json.dumps(coldstore, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (workspace / "state" / "capability_inventory.json").write_text(
        json.dumps(current, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    out = run_scan(workspace)
    report = out["report"]
    assert report["version"] == 1
    assert report["summary"]["legacy_items_scanned_count"] == 3
    assert report["summary"]["legacy_filtered_count"] >= 2
    assert (workspace / "state" / "legacy_capability_inventory.json").is_file()
    assert (workspace / "docs" / "_inbox" / "legacy_capability_inventory_latest.json").is_file()
    assert (workspace / "logs" / "legacy_capability_inventory_latest.json").is_file()
    assert "brain_node" in report["summary"]["counts_by_type"] or "script" in report["summary"]["counts_by_type"]

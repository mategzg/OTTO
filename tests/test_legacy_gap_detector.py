import json
from pathlib import Path

from scripts.legacy_gap_detector import run_scan
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


def test_legacy_gap_detector_detects_missing_and_duplicates(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    inventory = {
        "items": [
            {
                "path": "scripts/existing.py",
                "sha256": "abc123",
                "feature_signature": "sig001",
                "keywords": ["runtime", "hook"],
            }
        ]
    }
    coldstore = {
        "items": [
            {
                "candidate_id": "c1",
                "path": "vault/_salvage/existing_copy.py",
                "bucket": "code_candidate_review",
                "kind_heuristic": "code",
                "size": 100,
                "sha256": "abc123",
                "value_score": 3,
                "value_keywords": ["runtime", "hook"],
                "feature_signature": "sig001",
            },
            {
                "candidate_id": "c2",
                "path": "vault/_salvage/new_doc.md",
                "bucket": "doc_recoverable",
                "kind_heuristic": "doc",
                "size": 120,
                "sha256": "def456",
                "value_score": 4,
                "value_keywords": ["memory", "policy"],
                "feature_signature": "sig777",
            },
        ]
    }
    (workspace / "state" / "capability_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (workspace / "state" / "legacy_coldstore_index.json").write_text(
        json.dumps(coldstore, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    out = run_scan(workspace)
    report = out["report"]
    assert report["summary"]["duplicate_exact_count"] == 1
    assert report["summary"]["missing_count"] == 1
    assert report["doc_recoverable_missing"][0]["candidate_id"] == "c2"
    assert (workspace / "state" / "legacy_gap_report.json").is_file()

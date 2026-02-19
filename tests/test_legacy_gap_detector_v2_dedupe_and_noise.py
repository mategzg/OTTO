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


def test_legacy_gap_v2_suppresses_noise_artifacts_and_dedupes(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    inventory = {
        "items": [
            {
                "path": "scripts/existing.py",
                "sha256": "sha-existing",
                "feature_signature": "sig-existing",
                "keywords": ["runtime"],
            }
        ]
    }
    coldstore = {
        "items": [
            {
                "candidate_id": "a1",
                "path": "vault/_quarantine/bad_path_roots/x/C:\\Users\\a\\C:\\Users\\a\\docs/_inbox/noisy_report_latest.md",
                "bucket": "doc_recoverable",
                "kind_heuristic": "doc",
                "size": 111,
                "sha256": "sha-noise",
                "value_score": 9,
                "value_keywords": ["runtime", "router"],
                "feature_signature": "sig-noise",
            },
            {
                "candidate_id": "a2",
                "path": "vault/_salvage/pack/docs/_inbox/another_report.md",
                "bucket": "doc_recoverable",
                "kind_heuristic": "doc",
                "size": 111,
                "sha256": "sha-artifact",
                "value_score": 8,
                "value_keywords": ["runtime"],
                "feature_signature": "sig-art",
            },
            {
                "candidate_id": "a3",
                "path": "vault/_salvage/pack/scripts/new_capability.py",
                "bucket": "code_candidate_review",
                "kind_heuristic": "code",
                "size": 300,
                "sha256": "sha-useful",
                "value_score": 9,
                "value_keywords": ["runtime", "hook"],
                "feature_signature": "sig-useful",
            },
            {
                "candidate_id": "a4",
                "path": "vault/_quarantine/nested_repo_copies/y/scripts/new_capability.py",
                "bucket": "code_candidate_review",
                "kind_heuristic": "code",
                "size": 300,
                "sha256": "sha-useful",
                "value_score": 9,
                "value_keywords": ["runtime", "hook"],
                "feature_signature": "sig-useful",
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
    assert report["version"] == 2
    assert report["summary"]["suppressed_path_noise_count"] >= 1
    assert report["summary"]["excluded_artifacts_count"] >= 1
    assert report["summary"]["suppressed_duplicates_count"] >= 0

    top = report["top_missing_unique"]
    assert top
    top_paths = [item["path"] for item in top]
    assert all("/docs/_inbox/" not in p.replace("\\", "/") for p in top_paths)
    assert all("/logs/" not in p.replace("\\", "/") for p in top_paths)
    assert all("/ops/" not in p.replace("\\", "/") for p in top_paths)

    keys = [item["canonical_coldstore_key"] for item in top]
    assert len(keys) == len(set(keys))

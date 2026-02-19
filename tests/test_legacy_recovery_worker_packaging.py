import json
from pathlib import Path

from scripts.legacy_recovery_worker import run_once
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
    (root / "vault" / "inbox_raw" / "_pending_drop").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_legacy_recovery_worker_packages_only_safe_docs(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    safe_path = workspace / "vault" / "_salvage" / "useful_runtime.md"
    safe_path.write_text("runtime ingest policy docs\n", encoding="utf-8")
    blocked_path = workspace / "vault" / "_salvage" / "secrets.txt"
    blocked_path.write_text("api key = hidden\n", encoding="utf-8")

    policy = {
        "enabled": True,
        "interval_minutes": 1,
        "max_files_per_tick": 5,
        "max_total_bytes_per_tick": 2_000_000,
        "recoverable_extensions": [".md", ".txt", ".json"],
        "denylist_extensions": [".env"],
        "forbidden_buckets": ["sensitive_blocked", "instruction_drift_blocked", "code_candidate_review"],
        "target_drop_base": "vault/inbox_raw/_pending_drop/_legacy_recovery",
    }
    gap_report = {
        "doc_recoverable_missing": [
            {
                "candidate_id": "safe1",
                "path": "vault/_salvage/useful_runtime.md",
                "bucket": "doc_recoverable",
                "size": safe_path.stat().st_size,
                "priority_score": 100,
            },
            {
                "candidate_id": "blocked1",
                "path": "vault/_salvage/secrets.txt",
                "bucket": "doc_recoverable",
                "size": blocked_path.stat().st_size,
                "priority_score": 90,
            },
        ]
    }
    (workspace / "state" / "legacy_recovery_policy.json").write_text(
        json.dumps(policy, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (workspace / "state" / "legacy_gap_report.json").write_text(
        json.dumps(gap_report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    out = run_once(workspace, force=True)
    report = out["report"]
    assert report["status"] == "packaged"
    assert report["summary"]["packaged_count"] == 1
    assert report["summary"]["blocked_count"] >= 1

    batch_path = workspace / report["batch_path"]
    assert (batch_path / "README.md").is_file()
    assert (batch_path / "MANIFEST.json").is_file()
    assert (batch_path / "EVENT_META.json").is_file()

    state = json.loads((workspace / "state" / "legacy_recovery_state.json").read_text(encoding="utf-8"))
    assert "safe1" in state["processed_candidate_ids"]

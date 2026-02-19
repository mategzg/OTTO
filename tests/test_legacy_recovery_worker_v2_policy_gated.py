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
    (root / "vault" / "inbox_raw" / "_pending_drop").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_recovery_v2_disabled_by_default(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = run_once(workspace, force=True)
    assert out["report"]["status"] == "disabled"
    assert out["report"]["summary"]["packaged_count"] == 0


def test_recovery_v2_allow_types_excludes_scripts_hooks(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    doc_src = workspace / "vault" / "_salvage" / "useful.md"
    doc_src.write_text("brain note\n", encoding="utf-8")
    code_src = workspace / "vault" / "_salvage" / "scripts" / "code.py"
    code_src.parent.mkdir(parents=True, exist_ok=True)
    code_src.write_text("print('x')\n", encoding="utf-8")

    inventory = {
        "potential_missing_candidates": [
            {
                "candidate_id": "d1",
                "path": "vault/_salvage/useful.md",
                "legacy_type": "doc_value",
                "bucket": "doc_recoverable",
                "canonical_coldstore_key": "k1",
                "content_hash": "h1",
                "priority_score": 100,
                "size": doc_src.stat().st_size,
            },
            {
                "candidate_id": "c1",
                "path": "vault/_salvage/scripts/code.py",
                "legacy_type": "script",
                "bucket": "code_candidate_review",
                "canonical_coldstore_key": "k2",
                "content_hash": "h2",
                "priority_score": 200,
                "size": code_src.stat().st_size,
            },
        ]
    }
    policy = {
        "enabled": True,
        "interval_minutes": 1,
        "scan_interval_hours": 1,
        "max_items_per_tick": 5,
        "max_bytes_per_tick": 1_000_000,
        "allow_types": ["doc_value", "brain_node"],
        "target_drop_base": "vault/inbox_raw/_pending_drop/legacy_recovery",
    }
    (workspace / "state" / "legacy_capability_inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (workspace / "state" / "legacy_recovery_policy.json").write_text(
        json.dumps(policy, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    out = run_once(workspace, force=True)
    report = out["report"]
    assert report["status"] == "packaged"
    assert report["summary"]["packaged_count"] == 1
    assert report["packaged"][0]["source_path"] == "vault/_salvage/useful.md"
    blocked_reasons = [x["reason"] for x in report["blocked"]]
    assert any(reason.startswith("type_not_allowed") or reason.startswith("forbidden_bucket") for reason in blocked_reasons)

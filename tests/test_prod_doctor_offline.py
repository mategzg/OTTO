import json
from pathlib import Path

from scripts.prod_doctor import run_prod_doctor
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
    (root / ".openclaw").mkdir(parents=True, exist_ok=True)
    (root / ".openclaw" / "CANONICAL_ROOT.json").write_text(
        json.dumps({"root_realpath": str(root.resolve())}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "HEARTBEAT.md").write_text("python3 scripts/heartbeat_worker.py --once --root .\n", encoding="utf-8")
    (root / "state" / "heartbeat_policy.json").write_text(
        json.dumps({"version": 1, "interval_minutes": 30}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "_inbox" / "outbox_queue.ndjson").write_text("", encoding="utf-8")


def test_prod_doctor_offline_no_cli_marks_gap(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    monkeypatch.setenv("PATH", "")  # force no openclaw cli

    out = run_prod_doctor(workspace, force=True)
    report = out["report"]
    assert report["status"] in {"ok", "partial"}
    assert report["go_no_go"] in {"go_with_limits", "blocked", "go"}
    assert any("openclaw CLI" in gap or "openclaw CLI" in check.get("gap", "") for check in report["checks"] for gap in [check.get("gap", "")])
    assert (workspace / "docs" / "_inbox" / "prod_doctor_latest.json").is_file()
    assert (workspace / "logs" / "prod_doctor_latest.json").is_file()

import json
import subprocess
from pathlib import Path

from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / ".openclaw").mkdir(parents=True, exist_ok=True)
    (root / ".openclaw" / "CANONICAL_ROOT.json").write_text(
        json.dumps({"root_realpath": str(root.resolve())}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "openclaw" / "CONTEXT_MAP.md").write_text("# context\n", encoding="utf-8")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "hooks" / "otto-runtime-bridge").mkdir(parents=True, exist_ok=True)
    (root / "hooks" / "otto-runtime-bridge" / "HOOK.md").write_text("status: experimental\n", encoding="utf-8")
    (root / "hooks" / "otto-runtime-bridge" / "handler.js").write_text("module.exports = {};\n", encoding="utf-8")
    (root / "HEARTBEAT.md").write_text("python3 scripts/heartbeat_worker.py --once --root .\n", encoding="utf-8")
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "state" / "heartbeat_policy.json").write_text(
        json.dumps({"interval_minutes": 30, "version": 1}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "state" / "channel_runtime_policy.json").write_text(
        json.dumps(
            {
                "version": 1,
                "session_id_schema": {
                    "fields": ["channel", "account_id", "peer_id", "channel_id", "thread_id"],
                },
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox" / "instruction_surface_report_latest.json").write_text(
        json.dumps({"summary": {"drift_grave_count": 0}}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "_inbox" / "workspace_hygiene_report_latest.json").write_text(
        json.dumps({"summary": {"candidate_count": 0, "sensitive_count": 0}}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (root / "docs" / "_inbox" / "repo_reality_report_latest.json").write_text(
        json.dumps({"summary": {"pending_count": 0}}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_openclaw_compat_audit_generates_reports(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")

    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "openclaw_compat_audit.py"
    subprocess.run(["python3", str(script), "--root", str(workspace)], check=True)

    report_json = workspace / "docs" / "_inbox" / "openclaw_compat_audit_latest.json"
    report_md = workspace / "docs" / "_inbox" / "openclaw_compat_audit_latest.md"
    report_log = workspace / "logs" / "openclaw_compat_audit_latest.json"
    assert report_json.is_file()
    assert report_md.is_file()
    assert report_log.is_file()

    payload = json.loads(report_json.read_text(encoding="utf-8"))
    area_names = [str(item.get("name", "")) for item in payload.get("matrix", [])]
    assert "Hooks (message received/sent)" in area_names
    assert "Heartbeat behavior" in area_names
    assert payload.get("go_no_go") in {"go", "go_with_limits", "no_go"}

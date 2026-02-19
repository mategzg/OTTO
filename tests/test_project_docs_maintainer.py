import json
from pathlib import Path

from scripts.project_docs_maintainer import run_apply, run_scan
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
    (root / "SOUL.md").write_text("# SOUL\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "openclaw" / "CONTEXT_MAP.md").write_text("# CONTEXT_MAP\n", encoding="utf-8")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "memory").mkdir(parents=True, exist_ok=True)
    (root / "memory" / "00_INDEX.md").write_text("# memory\n", encoding="utf-8")
    (root / "brain" / "domains" / "openclaw_ops").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "domains" / "ingest").mkdir(parents=True, exist_ok=True)
    (root / "hooks" / "otto-runtime-bridge").mkdir(parents=True, exist_ok=True)
    (root / "hooks" / "otto-runtime-bridge" / "HOOK.md").write_text("# hook\n", encoding="utf-8")
    (root / "hooks" / "otto-runtime-bridge" / "handler.js").write_text("module.exports={};\n", encoding="utf-8")

    # Mandatory source stubs used by maintainer extraction.
    for rel in [
        "scripts/heartbeat_worker.py",
        "scripts/autonomy_tick.py",
        "scripts/channel_ingress_adapter.py",
        "scripts/session_memory_manager.py",
        "scripts/brain_ingest_router.py",
        "scripts/write_router.py",
        "scripts/dropbox_intake.py",
        "scripts/chatgpt_export_normalize.py",
        "scripts/outbox_delivery.py",
        "scripts/openclaw_cli.py",
        "scripts/approval_manager.py",
        "scripts/sg_promotion.py",
        "scripts/hook_backlog.py",
        "scripts/prod_doctor.py",
        "scripts/safety_switch.py",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# stub\n", encoding="utf-8")


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_maintainer_apply_generates_docs_and_reports(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = run_apply(workspace, force=True)
    assert out["report"]["status"] == "updated"
    assert (workspace / "PROJECT_BRIEF.md").is_file()
    assert (workspace / "REPO_MAP.md").is_file()
    assert (workspace / "repo_map" / "00_INDEX.md").is_file()
    assert (workspace / "docs" / "_inbox" / "project_docs_report_latest.json").is_file()
    assert (workspace / "logs" / "project_docs_latest.json").is_file()


def test_maintainer_scan_no_change_after_apply(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    run_apply(workspace, force=True)
    out = run_scan(workspace, force=True)
    assert out["report"]["status"] in {"no_change", "needs_update"}
    assert out["report"]["signature_new"]
    assert out["report"]["signature_new"] == out["report"]["signature_old"]


def test_maintainer_excludes_vault_from_signature(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    first = run_apply(workspace, force=True)["report"]["signature_new"]
    raw = workspace / "vault" / "inbox_raw" / "_pending_drop" / "payload.txt"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("raw-data\n", encoding="utf-8")
    second = run_scan(workspace, force=True)["report"]["signature_new"]
    assert first == second


def test_maintainer_interval_respected(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    run_apply(workspace, force=True)
    out = run_apply(workspace, force=False)
    assert out["report"]["status"] == "skipped_interval"
    state = json.loads((workspace / "state" / "project_docs_state.json").read_text(encoding="utf-8"))
    assert "last_run_utc" in state

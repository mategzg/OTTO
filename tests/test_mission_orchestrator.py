import json
from pathlib import Path

from scripts.mission_orchestrator import (
    run_close,
    run_emit_prompts,
    run_init,
    run_learn,
    run_status,
)
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "PROJECT_BRIEF.md").write_text("# PROJECT_BRIEF\n", encoding="utf-8")
    (root / "REPO_MAP.md").write_text("# REPO_MAP\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "openclaw" / "CONTEXT_MAP.md").write_text("# CONTEXT_MAP\n", encoding="utf-8")
    (root / "repo_map").mkdir(parents=True, exist_ok=True)
    (root / "repo_map" / "00_INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "brain" / "domains" / "openclaw_ops").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "domains" / "openclaw_ops" / "00_INDEX.md").write_text("# OPS\n", encoding="utf-8")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw" / "_pending_drop").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_mission_init_creates_isolated_plan_and_deterministic_counter(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    one = run_init(
        workspace,
        title="Odoo ingestion hardening",
        channel="telegram",
        peer_id="mateo",
        thread_id="",
        size="M",
    )["report"]
    two = run_init(
        workspace,
        title="Odoo ingestion hardening",
        channel="telegram",
        peer_id="mateo",
        thread_id="",
        size="M",
    )["report"]

    assert one["mission_id"] != two["mission_id"]
    assert one["mission_id"].startswith("msn_")
    assert one["mission_id"].split("_")[-1] == "01"
    assert two["mission_id"].split("_")[-1] == "02"
    assert (workspace / "state" / "missions" / one["mission_id"] / "PLAN.md").is_file()
    assert (workspace / "state" / "missions" / two["mission_id"] / "PLAN.md").is_file()


def test_plan_template_varies_by_size(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = run_init(
        workspace,
        title="Complex runtime bridge for multi channel operations",
        channel="discord",
        peer_id="ops-team",
        thread_id="thread-1",
        size="L",
    )["report"]
    mission_id = out["mission_id"]
    plan = (workspace / "state" / "missions" / mission_id / "PLAN.md").read_text(encoding="utf-8")
    assert "Mission size: `L`" in plan
    assert "## Objective" in plan
    assert "## Work Breakdown Structure" in plan
    assert "## Gates" in plan
    assert "Roles asignados: A, B, C" in plan


def test_emit_prompts_writes_latest_and_mission_history(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    init = run_init(
        workspace,
        title="Mission prompts test",
        channel="telegram",
        peer_id="mateo",
        size="XL",
    )["report"]
    mission_id = init["mission_id"]
    out = run_emit_prompts(workspace, mission_id=mission_id)["report"]

    assert out["status"] == "success"
    assert out["summary"]["roles_count"] == 4
    assert (workspace / "docs" / "_inbox" / "mission_prompts_latest.json").is_file()
    assert (workspace / "docs" / "_inbox" / "mission_prompts_latest.md").is_file()
    prompts_dir = workspace / "state" / "missions" / mission_id / "prompts"
    assert any(p.suffix == ".json" for p in prompts_dir.iterdir())
    assert any(p.suffix == ".md" for p in prompts_dir.iterdir())

    sample_md = sorted(prompts_dir.glob("*.md"))[0].read_text(encoding="utf-8")
    assert "HANDOFF_FILE (MUST):" in sample_md
    assert f"docs/_inbox/subagent_handoffs/{mission_id}__" in sample_md


def test_learn_packages_to_pending_drop_and_dedupes(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    mission_id = run_init(
        workspace,
        title="Learning package test",
        channel="whatsapp",
        peer_id="worker-1",
        thread_id="case-10",
        size="S",
    )["report"]["mission_id"]

    first = run_learn(workspace, mission_id=mission_id, stdin_text="Key finding: route by source_ref.")["report"]
    assert first["status"] == "success"
    package = workspace / first["learning_paths"]["package"]
    assert (package / "README.md").is_file()
    assert (package / "MANIFEST.json").is_file()
    assert (package / "source" / "EVENT_META.json").is_file()
    assert (package / "source" / "CONTENT.md").is_file()

    second = run_learn(workspace, mission_id=mission_id, stdin_text="Key finding: route by source_ref.")["report"]
    assert second["status"] == "skipped_duplicate"


def test_close_and_status(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    mission_id = run_init(
        workspace,
        title="Close test",
        channel="discord",
        peer_id="team",
        thread_id="t-2",
        size="M",
    )["report"]["mission_id"]
    closed = run_close(workspace, mission_id=mission_id, summary="Done with tests and docs.")["report"]
    assert closed["status"] == "success"
    status = run_status(workspace, mission_id=mission_id)["report"]
    assert status["details"]["status"] == "completed"
    meta = json.loads((workspace / "state" / "missions" / mission_id / "mission.json").read_text(encoding="utf-8"))
    assert meta["status"] == "completed"

from pathlib import Path

from scripts import openclaw_hook
from scripts.brain_index_build import build_registry
from scripts.brain_ingest_router import run_apply, run_plan
from scripts.corpus_triage import run_triage
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "openclaw" / "CONTEXT_MAP.md").write_text("# Context\n", encoding="utf-8")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw").mkdir(parents=True, exist_ok=True)


def _mk_source(root: Path, source_name: str = "source_alpha") -> Path:
    src = root / "vault" / "inbox_raw" / source_name
    src.mkdir(parents=True, exist_ok=True)
    (src / "notes.md").write_text("Operational notes for ingestion routing.\n", encoding="utf-8")
    (src / "facts.json").write_text('{"kind":"fact","value":"alpha"}\n', encoding="utf-8")
    return src


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_corpus_triage_is_deterministic_and_read_only(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    source = _mk_source(workspace)

    first = run_triage(workspace)
    second = run_triage(workspace)

    assert first["report"]["summary"] == second["report"]["summary"]
    assert [item["source_hash"] for item in first["report"]["sources"]] == [
        item["source_hash"] for item in second["report"]["sources"]
    ]
    assert source.exists()
    assert not (workspace / "vault" / "inbox_raw" / "_processed").exists()


def test_plan_only_does_not_modify_brain_tree(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _mk_source(workspace)

    before = sorted(
        p.resolve().relative_to(workspace.resolve()).as_posix()
        for p in (workspace / "brain").rglob("*")
        if p.is_file()
    )

    plan_out = run_plan(workspace)

    after = sorted(
        p.resolve().relative_to(workspace.resolve()).as_posix()
        for p in (workspace / "brain").rglob("*")
        if p.is_file()
    )

    assert plan_out["plan"]["status"] == "ok"
    assert before == after
    assert (workspace / plan_out["paths"]["plan_file"]).is_file()
    assert len(plan_out["plan"]["routing_decisions"]) == 1
    assert plan_out["plan"]["routing_decisions"][0]["source_id"] == plan_out["plan"]["sources"][0]["source_id"]


def test_apply_creates_domain_cards_and_moves_processed(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    source = _mk_source(workspace, "client_payload")

    plan_out = run_plan(workspace)
    assert plan_out["plan"]["status"] == "ok"
    source_id = plan_out["plan"]["sources"][0]["source_id"]

    apply_out = run_apply(workspace, plan_id=plan_out["plan"]["plan_id"])
    report = apply_out["report"]

    assert report["status"] == "success"
    assert report["summary"]["created"] >= 1
    assert report["summary"]["processed_moves"] == 1
    assert (workspace / "brain" / "domains" / "external_ingest" / "00_INDEX.md").is_file()
    assert list((workspace / "brain" / "cards" / "external_ingest").glob("*.md"))
    assert not source.exists()

    processed = list((workspace / "vault" / "inbox_raw" / "_processed").glob(f"*_{source_id}"))
    assert processed
    assert (processed[0] / "MANIFEST.json").is_file()
    assert (processed[0] / "README.md").is_file()


def test_apply_memory_category_appends_memory_inbox(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    source = _mk_source(workspace, "preferences_profile")
    (source / "notes.md").write_text("Mateo preference decision project timeline.\n", encoding="utf-8")

    plan_out = run_plan(workspace)
    assert plan_out["plan"]["status"] == "ok"
    assert plan_out["plan"]["routing_decisions"][0]["category"] == "memory_human"

    apply_out = run_apply(workspace, plan_id=plan_out["plan"]["plan_id"])
    assert apply_out["report"]["status"] == "success"
    inbox = workspace / "docs" / "_inbox" / "memory_inbox.ndjson"
    assert inbox.is_file()
    lines = [line for line in inbox.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines


def test_apply_blocked_plan_keeps_pending_source(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pending = _mk_source(workspace, "blocked_source")

    suspicious = workspace / "vault" / "inbox_raw" / ".vscode"
    suspicious.mkdir(parents=True, exist_ok=True)

    plan_out = run_plan(workspace)
    assert plan_out["plan"]["status"] == "blocked"
    assert "suspicious_entries_in_inbox" in plan_out["plan"]["stop_reasons"]

    apply_out = run_apply(workspace, plan_id=plan_out["plan"]["plan_id"])
    assert apply_out["report"]["status"] == "blocked"
    assert pending.exists()
    assert not (workspace / "vault" / "inbox_raw" / "_processed").exists()


def test_openclaw_hook_brain_commands(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _mk_source(workspace, "hook_source")

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    status_before = openclaw_hook.handle_repo_command("/brain status", root=workspace)
    assert status_before["ok"] is True
    assert status_before["status"]["pending_sources"] == 1

    triage = openclaw_hook.handle_repo_command("/brain triage", root=workspace)
    assert triage["ok"] is True

    plan_result = openclaw_hook.handle_repo_command("/brain plan", root=workspace)
    assert plan_result["ok"] is True
    plan_id = plan_result["plan_id"]

    apply_result = openclaw_hook.handle_repo_command(f"/brain apply {plan_id}", root=workspace)
    assert apply_result["ok"] is True

    status_after = openclaw_hook.handle_repo_command("/brain status", root=workspace)
    assert status_after["ok"] is True
    assert status_after["status"]["pending_sources"] == 0

    outbox = workspace / "docs" / "_inbox" / "outbox_latest.md"
    assert outbox.is_file()


def test_brain_index_registry_does_not_include_vault_raw(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    (workspace / "brain" / "00_INDEX.md").write_text("# Brain\n", encoding="utf-8")
    raw = workspace / "vault" / "inbox_raw" / "raw_source"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "raw.md").write_text("# Raw\n", encoding="utf-8")
    processed = workspace / "vault" / "inbox_raw" / "_processed" / "x" / "source"
    processed.mkdir(parents=True, exist_ok=True)
    (processed / "processed.md").write_text("# Processed\n", encoding="utf-8")

    registry = build_registry(workspace, namespace="brain")
    assert registry["node_count"] >= 1
    paths = [node["path"] for node in registry["nodes"]]
    assert all(path.startswith("brain/") for path in paths)
    assert all("vault/" not in path for path in paths)


def test_reserved_instruction_filename_forces_inbox_only_and_safe_derivative(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    source = _mk_source(workspace, "reserved_corpus")
    (source / "AGENTS.md").write_text("nested agents sample", encoding="utf-8")

    plan_out = run_plan(workspace)
    assert plan_out["plan"]["status"] == "ok"
    decision = plan_out["plan"]["routing_decisions"][0]
    assert decision["category"] == "inbox_only"
    assert decision["rule_id"] == "reserved_filename_guardrail"
    assert "AGENTS.md" in decision["reserved_files"]
    for op in plan_out["plan"]["operations"]:
        assert Path(op.get("target_rel", "")).name not in {"AGENTS.md", "CLAUDE.md", "AGENTS.override.md", "CLAUDE.local.md"}

    apply_out = run_apply(workspace, plan_id=plan_out["plan"]["plan_id"])
    assert apply_out["report"]["status"] == "success"
    safe_cards = list((workspace / "brain" / "cards" / "external_ingest").glob("*agents_example.md"))
    assert safe_cards

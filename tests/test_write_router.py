from pathlib import Path

from scripts.corpus_triage import run_triage
from scripts.repo_root import set_canonical_root
from scripts.write_router import build_routing_decisions, load_policy, run_write_router


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw").mkdir(parents=True, exist_ok=True)


def _mk_source(root: Path, name: str, text: str) -> None:
    src = root / "vault" / "inbox_raw" / name
    src.mkdir(parents=True, exist_ok=True)
    (src / "notes.md").write_text(text, encoding="utf-8")


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_write_router_policy_created_and_deterministic(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _mk_source(workspace, "ops_source", "openclaw repo hygiene gates")

    triage = run_triage(workspace)["report"]
    policy_first = load_policy(workspace, create_if_missing=True)
    policy_second = load_policy(workspace, create_if_missing=True)
    decisions_first = build_routing_decisions(triage["sources"], policy_first)
    decisions_second = build_routing_decisions(triage["sources"], policy_second)

    assert policy_first == policy_second
    assert decisions_first == decisions_second
    assert (workspace / "state" / "write_router_policy.json").is_file()


def test_write_router_classifies_categories(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    _mk_source(workspace, "ops_material", "openclaw otto repo root autonomy")
    _mk_source(workspace, "preferences_notes", "Mateo preference decision timeline")
    _mk_source(workspace, "prompt_pack", "prompt template protocol style")

    triage = run_triage(workspace)["report"]
    out = run_write_router(workspace, triage_report=triage)

    by_name = {item["source_name"]: item for item in out["report"]["routing_decisions"]}
    assert by_name["ops_material"]["category"] == "ops_system"
    assert by_name["preferences_notes"]["category"] == "memory_human"
    assert by_name["prompt_pack"]["category"] == "templates"


def test_write_router_reserved_filename_forces_inbox_only(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    src = workspace / "vault" / "inbox_raw" / "reserved_case"
    src.mkdir(parents=True, exist_ok=True)
    (src / "AGENTS.md").write_text("nested reserved", encoding="utf-8")

    triage = run_triage(workspace)["report"]
    out = run_write_router(workspace, triage_report=triage)

    decision = out["report"]["routing_decisions"][0]
    assert decision["category"] == "inbox_only"
    assert decision["rule_id"] == "reserved_filename_guardrail"
    assert "AGENTS.md" in decision["reserved_files"]

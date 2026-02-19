import json
from pathlib import Path

from scripts import openclaw_hook
from scripts.autonomy_tick import run_autonomy_tick
from scripts.corpus_triage import run_triage
from scripts.memory_capture import run_capture
from scripts.memory_compact import run_memory_compact
from scripts.memory_index_build import run_memory_index_build
from scripts.memory_query import run_memory_query
from scripts.repo_root import set_canonical_root
from scripts.write_router import run_write_router


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
    (root / "SOUL.md").write_text("# SOUL\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "openclaw" / "CONTEXT_MAP.md").write_text("# Context\n", encoding="utf-8")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def _read_ndjson(path: Path):
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        rows.append(json.loads(text))
    return rows


def test_memory_capture_appends_inbox(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    out = run_capture(
        workspace,
        record_type="profile_fact",
        key="",
        source_ref="manual:test",
        confidence="high",
        tags_csv="user,test",
        text="I prefer concise reports",
        fields={},
    )

    assert out["status"] == "ok"
    inbox = workspace / "docs" / "_inbox" / "memory_inbox.ndjson"
    rows = _read_ndjson(inbox)
    assert rows
    assert rows[0]["type"] == "profile_fact"


def test_memory_compact_dedupe_and_supersedes(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    run_capture(
        workspace,
        record_type="preference",
        key="preference:language:python",
        source_ref="manual:first",
        confidence="low",
        tags_csv="lang",
        text="Use python",
        fields={"category": "language", "rule": "Use python"},
    )
    run_capture(
        workspace,
        record_type="preference",
        key="preference:language:python",
        source_ref="manual:second",
        confidence="high",
        tags_csv="lang",
        text="Use python for automation tasks",
        fields={"category": "language", "rule": "Use python for automation tasks"},
    )

    out = run_memory_compact(workspace, apply=True)
    assert out["report"]["status"] == "success"

    pref_rows = _read_ndjson(workspace / "memory" / "03_PREFERENCES.ndjson")
    assert len(pref_rows) == 2

    active = [row for row in pref_rows if row["status"] == "active" and row["best_known"]]
    superseded = [row for row in pref_rows if row["status"] == "superseded" and not row["best_known"]]
    assert len(active) == 1
    assert len(superseded) == 1
    assert superseded[0]["id"] in active[0]["supersedes"]

    inbox = workspace / "docs" / "_inbox" / "memory_inbox.ndjson"
    assert inbox.read_text(encoding="utf-8").strip() == ""
    processed = list((workspace / "docs" / "_inbox" / "memory_inbox" / "_processed").glob("*_MANIFEST.json"))
    assert processed


def test_memory_index_and_query_with_evidence(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    run_capture(
        workspace,
        record_type="decision",
        key="decision:planner:2026-02-18",
        source_ref="manual:decision",
        confidence="high",
        tags_csv="ops,planning",
        text="Use deterministic planner",
        fields={"topic": "planner", "decision": "Use deterministic planner", "as_of": "2026-02-18T00:00:00+00:00"},
    )
    run_memory_compact(workspace, apply=True)

    index_out = run_memory_index_build(workspace)
    assert index_out["index"]["summary"]["record_count"] >= 1

    query_out = run_memory_query(
        workspace,
        question="What did we decide about planner?",
        k=3,
        types=["decision"],
        include_superseded=False,
        evidence=True,
        output_format="json",
    )
    assert query_out["result_count"] >= 1
    assert query_out["results"][0]["source_ref"]


def test_write_router_memory_human_targets_memory_inbox(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    src = workspace / "vault" / "inbox_raw" / "preferences_notes"
    src.mkdir(parents=True, exist_ok=True)
    (src / "notes.md").write_text("Mateo preference timeline decision", encoding="utf-8")

    triage = run_triage(workspace)["report"]
    out = run_write_router(workspace, triage_report=triage)

    decision = out["report"]["routing_decisions"][0]
    assert decision["category"] == "memory_human"
    memory_dest = [item for item in decision["destinations"] if item.get("kind") == "memory_inbox"]
    assert memory_dest
    assert memory_dest[0]["path"] == "docs/_inbox/memory_inbox.ndjson"


def test_openclaw_hook_memory_commands(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    monkeypatch.setattr(openclaw_hook, "send_telegram_message", lambda _text: {"ok": False, "sent": False, "reason": "missing_config"})

    capture = openclaw_hook.handle_repo_command("/memory capture yo prefiero respuestas cortas", root=workspace)
    assert capture["ok"] is True

    status = openclaw_hook.handle_repo_command("/memory status", root=workspace)
    assert status["ok"] is True
    assert status["status"]["inbox_pending"] >= 1

    compact = openclaw_hook.handle_repo_command("/memory compact", root=workspace)
    assert compact["ok"] is True

    ask = openclaw_hook.handle_repo_command("/memory ask que prefiero", root=workspace)
    assert ask["ok"] is True

    outbox = workspace / "docs" / "_inbox" / "outbox_latest.md"
    assert outbox.is_file()


def test_autonomy_tick_processes_memory_inbox(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    run_capture(
        workspace,
        record_type="profile_fact",
        key="profile:goal",
        source_ref="manual:goal",
        confidence="medium",
        tags_csv="profile",
        text="My goal is shipping MemoryOS",
        fields={"fact": "Goal is shipping MemoryOS"},
    )

    send = lambda _msg: {"ok": False, "sent": False, "reason": "missing_config"}
    out = run_autonomy_tick(root=workspace, force=True, max_sources_per_tick=1, send_func=send)

    assert out["status"] in {"success", "idle"}
    assert out["memory"]["compact_status"] == "success"
    assert out["memory"]["index_status"] == "success"
    assert (workspace / "state" / "memory_index.json").is_file()

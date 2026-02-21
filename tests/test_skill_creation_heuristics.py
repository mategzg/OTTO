import json
from pathlib import Path

from scripts.skill_creation_heuristics import evaluate_creation


def test_creation_heuristic_create_and_audit(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)

    import scripts.skill_creation_heuristics as h

    monkeypatch.setattr(h, "get_canonical_root", lambda root: Path(root).resolve())

    out = evaluate_creation(
        tmp_path,
        route_type="tool",
        selected_target="rag.answer",
        repeat_count_30d=7,
        impact_score=9,
        risk_score=2,
        generality_score=8,
        latency_cost_score=4,
        trace_id="trace-1",
    )
    assert out["decision"] == "create"
    assert out["eligible"] is True
    assert out["score"] >= out["threshold_create"]

    log_path = tmp_path / "logs" / "skill_creation_decisions.ndjson"
    assert log_path.is_file()
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["trace_id"] == "trace-1"
    assert rows[-1]["decision"] == "create"


def test_creation_heuristic_defers_on_risk(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)

    import scripts.skill_creation_heuristics as h

    monkeypatch.setattr(h, "get_canonical_root", lambda root: Path(root).resolve())

    out = evaluate_creation(
        tmp_path,
        route_type="workflow",
        selected_target="status.check",
        repeat_count_30d=8,
        impact_score=10,
        risk_score=9,
        trace_id="trace-2",
    )
    assert out["decision"] == "defer"
    assert out["reason"] == "risk_above_limit"
    assert out["requires_approval"] is True

from pathlib import Path

from scripts.golden_regression_gate import run_gate


def test_golden_gate_runs_and_writes_report(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)

    (tmp_path / "state" / "golden_set_spec002.json").write_text(
        '{"version":1,"items":[{"id":"g1","question":"Recuérdame mañana pagar internet","expected_intent":"reminder_request","expected_route_type":"skill","expected_target":"reminder.create"}] }\n',
        encoding="utf-8",
    )
    (tmp_path / "state" / "golden_regression_thresholds.json").write_text(
        '{"min_total":1,"min_pass_rate":0.0,"min_ndcg":0.0,"min_mrr":0.0,"min_groundedness":0.0}\n',
        encoding="utf-8",
    )

    import scripts.golden_regression_gate as gg

    monkeypatch.setattr(gg, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(
        gg,
        "run_golden_regression",
        lambda *_a, **_k: {
            "summary": {"total": 1, "pass_rate": 1.0, "metrics": {"ndcg": 1.0, "mrr": 1.0, "groundedness": 1.0}}
        },
    )

    out = run_gate(tmp_path)
    assert out["status"] == "pass"
    assert (tmp_path / "docs" / "_inbox" / "golden_regression_gate_latest.json").is_file()

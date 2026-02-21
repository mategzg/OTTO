from pathlib import Path

from scripts.golden_regression_runner import run_golden_regression


def test_golden_regression_generates_reports(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)

    (tmp_path / "state" / "golden_set_spec002.json").write_text(
        """
{
  "version": 1,
  "items": [
    {
      "id": "g1",
      "question": "Recuérdame mañana pagar internet",
      "expected_intent": "reminder_request",
      "expected_route_type": "skill",
      "expected_target": "reminder.create"
    }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    import scripts.golden_regression_runner as gr

    monkeypatch.setattr(gr, "get_canonical_root", lambda root: Path(root).resolve())

    out = run_golden_regression(tmp_path)
    assert out["summary"]["total"] == 1
    assert (tmp_path / "docs" / "_inbox" / "golden_regression_latest.json").is_file()
    assert (tmp_path / "docs" / "_inbox" / "golden_regression_latest.md").is_file()
    assert (tmp_path / "logs" / "golden_regression_runs.ndjson").is_file()

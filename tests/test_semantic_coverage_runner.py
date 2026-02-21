from pathlib import Path

from scripts.semantic_coverage_runner import run_semantic_coverage


def test_semantic_coverage_generates_report(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)
    docs = tmp_path / "brain" / "domains" / "sg_acabados"
    docs.mkdir(parents=True)
    (docs / "card_odoo_operations.md").write_text(
        "# Odoo\nFlujo de cotizacion, cliente, factura y cobranza\n",
        encoding="utf-8",
    )

    (tmp_path / "state" / "semantic_coverage_policy.json").write_text(
        """
{
  "version": 1,
  "domains": {
    "sg_acabados": {
      "paths": ["brain/domains/sg_acabados"],
      "synonyms": {"cotizacion": ["quote"]},
      "representative_queries": ["quote para cliente"]
    }
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    import scripts.semantic_coverage_runner as sc

    monkeypatch.setattr(sc, "get_canonical_root", lambda root: Path(root).resolve())

    out = run_semantic_coverage(tmp_path)
    assert out["summary"]["queries_total"] == 1
    assert (tmp_path / "docs" / "_inbox" / "semantic_coverage_latest.json").is_file()
    assert (tmp_path / "docs" / "_inbox" / "semantic_coverage_latest.md").is_file()

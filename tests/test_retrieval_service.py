from pathlib import Path

from scripts.retrieval_service import retrieve


def test_retrieval_service_returns_contract_fields(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "brain" / "domains" / "sg_acabados").mkdir(parents=True)
    (tmp_path / "brain" / "domains" / "sg_acabados" / "card.md").write_text(
        "# Odoo\nProceso de cotizacion y cliente en Odoo\n", encoding="utf-8"
    )

    import scripts.retrieval_service as rs

    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())

    out = retrieve(tmp_path, query="cotizacion cliente", principal_ctx={"user_id": "u1"})
    assert "final_topk" in out
    assert "diagnostics" in out
    if out["final_topk"]:
        row = out["final_topk"][0]
        for key in ["chunk_id", "doc_id", "doc_version", "path", "section_path", "locator", "content_hash", "text", "scores"]:
            assert key in row
        for score_key in ["bm25", "vector", "fused", "rerank"]:
            assert score_key in row["scores"]

from pathlib import Path

from scripts.retrieval_service import retrieve


def _seed_repo(tmp_path: Path) -> None:
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "brain" / "domains" / "sg_acabados").mkdir(parents=True)


def test_retrieval_hybrid_fusion_outputs_scores(tmp_path: Path, monkeypatch):
    _seed_repo(tmp_path)
    (tmp_path / "brain" / "domains" / "sg_acabados" / "a.md").write_text(
        "# A\nCotizacion de marmol para cliente premium\n", encoding="utf-8"
    )

    import scripts.retrieval_service as rs

    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())

    out = retrieve(tmp_path, query="cotizacion cliente premium", principal_ctx={"user_id": "u1"})
    assert out["diagnostics"]["lexical_candidates"] >= 1
    assert out["diagnostics"]["vector_candidates"] >= 1
    assert out["diagnostics"]["union_count"] >= 1
    assert out["final_topk"]
    row = out["final_topk"][0]
    assert row["scores"]["bm25"] >= 0
    assert row["scores"]["vector"] >= 0
    assert row["scores"]["fused"] >= 0
    assert row["scores"]["rerank"] >= 0


def test_rerank_can_change_order_vs_fused(tmp_path: Path, monkeypatch):
    _seed_repo(tmp_path)
    (tmp_path / "brain" / "domains" / "sg_acabados" / "b.md").write_text(
        "# B\n"
        "cotizacion cliente proceso urgente\n"
        "flujo oficial de cotizacion para cliente SG\n",
        encoding="utf-8",
    )

    import scripts.retrieval_service as rs

    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())

    out = retrieve(tmp_path, query="cotizacion para cliente", principal_ctx={"user_id": "u1"})
    reranked = out["reranked"]
    assert len(reranked) >= 2

    # If rerank is active, top rerank should prioritize phrase match line.
    top = reranked[0]
    assert "cotizacion para cliente" in top["text"].lower()

from pathlib import Path

from scripts.retrieval_service import retrieve


def test_whatsapp_client_cannot_retrieve_personal_vision(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)

    (tmp_path / "memory" / "vision").mkdir(parents=True)
    (tmp_path / "memory" / "vision" / "10_NORTH_STAR.md").write_text(
        "Mi visión personal en Austin\n", encoding="utf-8"
    )

    (tmp_path / "brain" / "domains" / "sg_acabados").mkdir(parents=True)
    (tmp_path / "brain" / "domains" / "sg_acabados" / "public.md").write_text(
        "Catálogo SG y cotizaciones\n", encoding="utf-8"
    )

    import scripts.retrieval_service as rs

    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())

    out = retrieve(
        tmp_path,
        query="cual es mi vision personal",
        principal_ctx={"channel": "whatsapp", "actor_type": "client", "user_id": "u1"},
    )

    paths = [str(row.get("path", "")) for row in out.get("final_topk", [])]
    assert all(not p.startswith("memory/") for p in paths)
    assert out.get("diagnostics", {}).get("channel_filtered_count", 0) >= 1

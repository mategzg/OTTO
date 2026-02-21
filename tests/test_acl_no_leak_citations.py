from pathlib import Path

from scripts.nl_skill_router import run_nl_router


def _setup(tmp_path: Path):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "brain" / "domains" / "sg_acabados").mkdir(parents=True)
    (tmp_path / "state" / "retrieval_policy.json").write_text(
        '{"retrieval_v2": {"enabled": true, "lexical_top_n": 10, "vector_top_n": 10, "final_top_k": 5, "max_chunks_per_doc": 2, "min_evidence_score": 0.0}}\n',
        encoding="utf-8",
    )
    (tmp_path / "brain" / "domains" / "sg_acabados" / "doc_a.md").write_text(
        "<!-- acl_allow: user:u_a -->\nProceso oficial cotizacion grupo A\n", encoding="utf-8"
    )
    (tmp_path / "brain" / "domains" / "sg_acabados" / "doc_b.md").write_text(
        "<!-- acl_allow: user:u_b -->\nProceso secreto grupo B\n", encoding="utf-8"
    )


def test_acl_no_leak_in_router_retrieval_pack(tmp_path: Path, monkeypatch):
    _setup(tmp_path)

    import scripts.nl_skill_router as router

    monkeypatch.setattr(router, "get_canonical_root", lambda root: Path(root).resolve())

    out = run_nl_router(
        tmp_path,
        text="explicame proceso oficial cotizacion",
        channel="telegram",
        conversation_id="u_a",
        thread_id="t",
        message_id="m",
    )

    pack = out.get("retrieval_v2", {}).get("pack", {})
    topk = pack.get("final_topk", [])
    paths = {row.get("path", "") for row in topk}
    assert topk
    assert all("doc_b.md" not in p for p in paths)

from pathlib import Path

from scripts.retrieval_service import retrieve


def _setup(tmp_path: Path):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    base = tmp_path / "brain" / "domains" / "sg_acabados"
    base.mkdir(parents=True)
    (base / "doc_a.md").write_text("<!-- acl_allow: group:a -->\nProceso de cotizacion cliente A\n", encoding="utf-8")
    (base / "doc_b.md").write_text("<!-- acl_allow: group:b -->\nProceso de cotizacion cliente B\n", encoding="utf-8")


def test_acl_no_leak_in_candidates_and_topk(tmp_path: Path, monkeypatch):
    _setup(tmp_path)

    import scripts.retrieval_service as rs

    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())

    out = retrieve(
        tmp_path,
        query="cotizacion cliente",
        principal_ctx={"user_id": "u_a", "group_ids": ["a"], "roles": []},
    )

    union_paths = {row["path"] for row in out["candidates_union"]}
    topk_paths = {row["path"] for row in out["final_topk"]}

    assert any("doc_a.md" in p for p in union_paths)
    assert all("doc_b.md" not in p for p in union_paths)
    assert all("doc_b.md" not in p for p in topk_paths)
    assert out["diagnostics"]["acl_filtered_count"] >= 1

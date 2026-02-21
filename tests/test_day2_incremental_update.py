from pathlib import Path

from scripts.day2_doc_inventory import run_day2_inventory_sync
from scripts.retrieval_service import retrieve


def _setup(root: Path):
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "domains" / "sg_acabados").mkdir(parents=True, exist_ok=True)


def test_day2_incremental_update_and_doc_rot_detection(tmp_path: Path, monkeypatch):
    _setup(tmp_path)
    import scripts.day2_doc_inventory as d2
    import scripts.retrieval_service as rs

    monkeypatch.setattr(d2, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())

    p = tmp_path / "brain" / "domains" / "sg_acabados" / "update.md"
    p.write_text("Version antigua proceso Odoo\n", encoding="utf-8")
    run_day2_inventory_sync(tmp_path)

    p.write_text("Version nueva proceso Odoo actualizado\n", encoding="utf-8")
    out2 = run_day2_inventory_sync(tmp_path)
    assert out2["summary"]["modified"] >= 1

    r = retrieve(tmp_path, query="actualizado", principal_ctx={"user_id": "u1"})
    assert any("update.md" in x["path"] for x in r["final_topk"])

    p.write_text("\n\n", encoding="utf-8")
    out3 = run_day2_inventory_sync(tmp_path)
    assert out3["summary"]["doc_rot"] >= 1

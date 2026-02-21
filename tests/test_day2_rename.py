from pathlib import Path

from scripts.day2_doc_inventory import run_day2_inventory_sync
from scripts.retrieval_service import retrieve


def _setup(root: Path):
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "brain" / "domains" / "sg_acabados").mkdir(parents=True, exist_ok=True)


def test_day2_rename_keeps_visibility_on_new_path(tmp_path: Path, monkeypatch):
    _setup(tmp_path)
    import scripts.day2_doc_inventory as d2
    import scripts.retrieval_service as rs

    monkeypatch.setattr(d2, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())

    old = tmp_path / "brain" / "domains" / "sg_acabados" / "old.md"
    old.write_text("Proceso oficial de inventario\n", encoding="utf-8")
    run_day2_inventory_sync(tmp_path)

    old.rename(tmp_path / "brain" / "domains" / "sg_acabados" / "new.md")
    out = run_day2_inventory_sync(tmp_path)

    assert out["summary"]["renamed"] >= 1
    r = retrieve(tmp_path, query="inventario oficial", principal_ctx={"user_id": "u1"})
    paths = {x["path"] for x in r["final_topk"]}
    assert any("new.md" in p for p in paths)

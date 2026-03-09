from pathlib import Path

from scripts.sharepoint_sync import run_incremental_sync


def _seed_repo(tmp_path: Path) -> None:
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)


def test_sharepoint_incremental_and_classification(tmp_path: Path, monkeypatch):
    _seed_repo(tmp_path)
    src = tmp_path / "SG Acabados"
    src.mkdir(parents=True)
    (src / "ventas.md").write_text("cotizacion marmol", encoding="utf-8")
    (src / "personal_notas.txt").write_text("privado", encoding="utf-8")

    import scripts.sharepoint_sync as ss

    monkeypatch.setattr(ss, "get_canonical_root", lambda root: Path(root).resolve())

    first = run_incremental_sync(tmp_path, source_root=src)
    assert first["status"] == "ok"
    assert first["processed"] == 2

    second = run_incremental_sync(tmp_path, source_root=src)
    assert second["processed"] == 0

    processed = tmp_path / "vault" / "inbox_raw" / "_processed" / "sharepoint_sg_acabados"
    bodies = "\n".join(p.read_text(encoding="utf-8") for p in processed.glob("*.md"))
    assert "audience:sg" in bodies
    assert "audience:personal" in bodies
    assert "route_target: brain/domains/sg_acabados" in bodies
    assert "route_target: brain/domains/personal_ops" in bodies

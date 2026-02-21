from pathlib import Path

import scripts.memory_index_build as memory_index_build


def test_memory_index_includes_profile_and_vision_markdown_maps(tmp_path: Path, monkeypatch):
    # minimal canonical markers for repo_root resolver
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    (tmp_path / "memory" / "profile").mkdir(parents=True)
    (tmp_path / "memory" / "vision").mkdir(parents=True)

    (tmp_path / "memory" / "01_PROFILE_CURRENT.md").write_text("# Profile Current\n\n- fact\n", encoding="utf-8")
    (tmp_path / "memory" / "02_PRINCIPLES_CURRENT.md").write_text("# Principles\n\n- rule\n", encoding="utf-8")
    (tmp_path / "memory" / "profile" / "10_IDENTITY.md").write_text("# Identity\n\nText\n", encoding="utf-8")
    (tmp_path / "memory" / "vision" / "10_NORTH_STAR.md").write_text("# North Star\n\nText\n", encoding="utf-8")

    monkeypatch.setattr(memory_index_build, "get_canonical_root", lambda root: Path(root).resolve())

    index = memory_index_build.build_memory_index(tmp_path)
    records = index["records"]

    keys = {row.get("key") for row in records.values()}
    assert "memory/profile/10_IDENTITY.md" in keys
    assert "memory/vision/10_NORTH_STAR.md" in keys

    types = {row.get("type") for row in records.values()}
    assert "profile_doc" in types
    assert "vision_doc" in types

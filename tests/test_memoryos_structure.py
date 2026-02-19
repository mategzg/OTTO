from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_index_exists_and_links_master_indexes():
    text = _read("INDEX.md")
    assert "brain/00_INDEX.md" in text
    assert "openclaw/00_INDEX.md" in text


def test_wrappers_point_to_index_hub():
    assert "INDEX.md" in _read("SOUL.md")
    assert "INDEX.md" in _read("AGENTS.md")
    assert "INDEX.md" in _read("CLAUDE.md")


def test_brain_namespace_minimum_docs_exist():
    required = [
        "brain/00_INDEX.md",
        "brain/01_BRAIN_PROTOCOL.md",
        "brain/02_NODE_TEMPLATE.md",
        "brain/03_CARD_SCHEMA.md",
    ]
    for rel_path in required:
        assert (ROOT / rel_path).is_file()

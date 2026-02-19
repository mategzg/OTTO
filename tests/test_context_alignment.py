from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_agents_and_claude_reference_canon_and_hub():
    agents = _read("AGENTS.md")
    claude = _read("CLAUDE.md")

    assert "CEO.md" in agents
    assert "INDEX.md" in agents
    assert "CEO.md" in claude
    assert "INDEX.md" in claude


def test_soul_points_to_index():
    assert "INDEX.md" in _read("SOUL.md")


def test_context_map_exists_in_openclaw():
    assert (ROOT / "openclaw/CONTEXT_MAP.md").is_file()


def test_hubs_redirect_to_context_authority():
    assert "openclaw/CONTEXT_MAP.md" in _read("INDEX.md")
    assert "openclaw/CONTEXT_MAP.md" in _read("openclaw/00_INDEX.md")
    assert "openclaw/CONTEXT_MAP.md" in _read("brain/00_INDEX.md")


def test_vault_raw_is_gitignored():
    gitignore = _read(".gitignore")
    assert "vault/chatgpt_export_raw/" in gitignore
    assert "vault/chatgpt_export_raw/**" in gitignore


def test_only_ceo_claims_canonical_authority():
    ceo = _read("CEO.md")
    agents = _read("AGENTS.md")
    claude = _read("CLAUDE.md")

    assert "Canonical operating guide" in ceo
    assert "Canonical operating guide" not in agents
    assert "Canonical operating guide" not in claude

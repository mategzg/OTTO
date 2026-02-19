from pathlib import Path

from scripts.brain_index_build import _iter_markdown_paths

ROOT = Path(__file__).resolve().parents[1]


def test_openclaw_ops_domain_structure_has_required_sections():
    required = [
        ROOT / "brain" / "domains" / "openclaw_ops" / "00_INDEX.md",
        ROOT / "brain" / "domains" / "openclaw_ops" / "01_ROUTER.md",
        ROOT / "brain" / "domains" / "openclaw_ops" / "02_RUN_PROTOCOL.md",
        ROOT / "brain" / "domains" / "openclaw_ops" / "03_REPO_REALITY.md",
        ROOT / "brain" / "domains" / "openclaw_ops" / "04_WORKSPACE_HYGIENE.md",
        ROOT / "brain" / "domains" / "openclaw_ops" / "05_HOOKS_COMMANDS.md",
        ROOT / "brain" / "domains" / "openclaw_ops" / "07_DELEGATION_POLICY.md",
    ]
    for node in required:
        assert node.is_file(), f"missing node: {node}"
        text = node.read_text(encoding="utf-8")
        assert "## Use when" in text
        assert "## Avoid when" in text
        assert "## Routing" in text


def test_cards_have_source_ref_and_paths_exist():
    cards_dir = ROOT / "brain" / "cards" / "openclaw_ops"
    cards = sorted(cards_dir.glob("*.md"))
    assert cards, "no cards found"

    for card in cards:
        lines = card.read_text(encoding="utf-8").splitlines()
        source_lines = [line for line in lines if line.lower().startswith("source_ref:")]
        assert source_lines, f"missing source_ref in {card}"
        refs = []
        for line in source_lines:
            raw = line.split(":", 1)[1].strip()
            refs.extend([r.strip() for r in raw.split(";") if r.strip()])
        assert refs, f"empty source_ref in {card}"
        for ref in refs:
            assert (ROOT / ref).exists(), f"source_ref does not exist: {ref} ({card})"


def test_indexer_excludes_vault_and_tooling_paths(tmp_path: Path):
    (tmp_path / "brain").mkdir(parents=True)
    (tmp_path / "brain" / "00_INDEX.md").write_text("# Brain\n", encoding="utf-8")
    (tmp_path / "brain" / ".vscode").mkdir(parents=True)
    (tmp_path / "brain" / ".vscode" / "tool.md").write_text("# Tool\n", encoding="utf-8")
    (tmp_path / "vault" / "inbox_raw" / "claude_inverse_engineering").mkdir(parents=True)
    (tmp_path / "vault" / "inbox_raw" / "claude_inverse_engineering" / "raw.md").write_text("# Raw\n", encoding="utf-8")
    (tmp_path / "vault" / "_quarantine" / "x").mkdir(parents=True)
    (tmp_path / "vault" / "_quarantine" / "x" / "q.md").write_text("# Q\n", encoding="utf-8")

    found = [path.relative_to(tmp_path).as_posix() for path in _iter_markdown_paths(tmp_path, "brain")]
    assert "brain/00_INDEX.md" in found
    assert "brain/.vscode/tool.md" not in found

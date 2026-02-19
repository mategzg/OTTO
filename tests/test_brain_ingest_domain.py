from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ingest_domain_structure_has_required_sections():
    required = [
        ROOT / "brain" / "domains" / "ingest" / "00_INDEX.md",
        ROOT / "brain" / "domains" / "ingest" / "01_ROUTER.md",
        ROOT / "brain" / "domains" / "ingest" / "02_PIPELINE.md",
        ROOT / "brain" / "domains" / "ingest" / "03_DOMAIN_NAMING.md",
        ROOT / "brain" / "domains" / "ingest" / "04_SPLIT_HEURISTICS.md",
        ROOT / "brain" / "domains" / "ingest" / "05_PENDING_POLICY.md",
        ROOT / "brain" / "domains" / "ingest" / "06_WRITE_ROUTER.md",
    ]
    for node in required:
        assert node.is_file(), f"missing node: {node}"
        text = node.read_text(encoding="utf-8")
        assert "## Use when" in text
        assert "## Avoid when" in text
        assert "## Routing" in text

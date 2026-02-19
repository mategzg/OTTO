from pathlib import Path

import pytest

from scripts.brain_index_build import _iter_markdown_paths, build_registry, write_outputs


def test_build_registry_is_deterministic(tmp_path: Path):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True)

    (brain / "02_b.md").write_text(
        """---
tags: [beta, alpha]
---

# Node B

Tags: extra, alpha

Link: [Node A](01_a.md)
""",
        encoding="utf-8",
    )
    (brain / "01_a.md").write_text(
        "# Node A\n\nTags: alpha\n",
        encoding="utf-8",
    )

    first = build_registry(tmp_path, namespace="brain")
    second = build_registry(tmp_path, namespace="brain")

    assert first == second
    assert first["node_count"] == 2
    assert [node["path"] for node in first["nodes"]] == ["brain/01_a.md", "brain/02_b.md"]
    assert first["nodes"][1]["tags"] == ["alpha", "beta", "extra"]
    assert first["nodes"][1]["deep_links"] == ["01_a.md"]


def test_write_outputs_uses_docs_and_logs_when_state_not_versioned(tmp_path: Path):
    (tmp_path / "brain").mkdir(parents=True)
    (tmp_path / "brain" / "00_INDEX.md").write_text("# Brain\n", encoding="utf-8")

    registry = build_registry(tmp_path, namespace="brain")
    outputs = write_outputs(tmp_path, registry)

    relative = [path.relative_to(tmp_path).as_posix() for path in outputs]
    assert relative == [
        "docs/_inbox/brain_registry_latest.json",
        "logs/brain_index_build_latest.json",
    ]

    first_registry = (tmp_path / "docs" / "_inbox" / "brain_registry_latest.json").read_text(encoding="utf-8")
    first_log = (tmp_path / "logs" / "brain_index_build_latest.json").read_text(encoding="utf-8")

    write_outputs(tmp_path, registry)

    second_registry = (tmp_path / "docs" / "_inbox" / "brain_registry_latest.json").read_text(encoding="utf-8")
    second_log = (tmp_path / "logs" / "brain_index_build_latest.json").read_text(encoding="utf-8")

    assert first_registry == second_registry
    assert first_log == second_log


def test_iter_markdown_paths_excludes_quarantine_and_detected_nested_copy(tmp_path: Path):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True)
    (brain / "00_INDEX.md").write_text("# Brain\n", encoding="utf-8")
    (brain / "01_keep.md").write_text("# Keep\n", encoding="utf-8")
    tooling = brain / ".vscode"
    tooling.mkdir(parents=True)
    (tooling / "tooling.md").write_text("# Tooling\n", encoding="utf-8")

    ghost = brain / "ghost_copy"
    ghost.mkdir(parents=True)
    (ghost / "99_skip.md").write_text("# Skip\n", encoding="utf-8")

    q = tmp_path / "vault" / "_quarantine" / "nested_repo_copies" / "x"
    q.mkdir(parents=True)
    (q / "q.md").write_text("# Q\n", encoding="utf-8")
    s = tmp_path / "vault" / "_salvage" / "x" / "staged"
    s.mkdir(parents=True)
    (s / "s.md").write_text("# S\n", encoding="utf-8")

    report_path = tmp_path / "docs" / "_inbox" / "repo_reality_report_latest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        """
{
  "candidates": [
    { "path": "brain/ghost_copy" }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    found = [path.relative_to(tmp_path).as_posix() for path in _iter_markdown_paths(tmp_path, "brain")]
    assert "brain/01_keep.md" in found
    assert "brain/ghost_copy/99_skip.md" not in found
    assert "brain/.vscode/tooling.md" not in found


def test_iter_markdown_paths_excludes_kept_and_quarantined_state(tmp_path: Path):
    brain = tmp_path / "brain"
    brain.mkdir(parents=True)
    (brain / "00_INDEX.md").write_text("# Brain\n", encoding="utf-8")
    (brain / "keep_copy").mkdir(parents=True)
    (brain / "keep_copy" / "01_skip.md").write_text("# Skip\n", encoding="utf-8")
    (brain / "quarantine_copy").mkdir(parents=True)
    (brain / "quarantine_copy" / "02_skip.md").write_text("# Skip\n", encoding="utf-8")

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "repo_reality_allowlist.json").write_text(
        """
{
  "kept_paths": {
    "aaa111": "brain/keep_copy"
  }
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (state_dir / "repo_reality_state.json").write_text(
        """
{
  "quarantine_moves": [
    { "from": "brain/quarantine_copy", "to": "vault/_quarantine/nested_repo_copies/x" }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    found = [path.relative_to(tmp_path).as_posix() for path in _iter_markdown_paths(tmp_path, "brain")]
    assert "brain/00_INDEX.md" in found
    assert "brain/keep_copy/01_skip.md" not in found
    assert "brain/quarantine_copy/02_skip.md" not in found


def test_iter_markdown_paths_rejects_namespace_outside_allowlist(tmp_path: Path):
    with pytest.raises(ValueError):
        list(_iter_markdown_paths(tmp_path, "private"))

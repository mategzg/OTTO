import json
from pathlib import Path

import scripts.repomap_index_build as repomap_index_build
import scripts.repomap_query as repomap_query


def test_repomap_index_and_query_returns_relevant_paths(tmp_path: Path, monkeypatch):
    # minimal canonical markers for repo_root resolver
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    (tmp_path / "repo_map").mkdir(parents=True)
    (tmp_path / "REPO_MAP.md").write_text("# REPO MAP\n\nRuntime ingress and policies.\n", encoding="utf-8")
    (tmp_path / "repo_map" / "10_RUNTIME_INGRESS.md").write_text(
        "# 10 Runtime Ingress\n\nCovers ingress pipeline and routing.\n", encoding="utf-8"
    )
    (tmp_path / "repo_map" / "95_MISSION_ORCHESTRATION.md").write_text(
        "# 95 Mission Orchestration\n\nDelegation, roles and orchestration.\n", encoding="utf-8"
    )

    monkeypatch.setattr(repomap_index_build, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(repomap_query, "get_canonical_root", lambda root: Path(root).resolve())

    out = repomap_index_build.build(tmp_path)
    assert out["summary"]["record_count"] == 3

    reg = tmp_path / "state" / "repomap_registry.json"
    assert reg.is_file()
    payload = json.loads(reg.read_text(encoding="utf-8"))
    assert payload["summary"]["record_count"] == 3

    q = repomap_query.query(tmp_path, "runtime ingress orchestration", k=3)
    paths = [row["path"] for row in q["results"]]
    assert "repo_map/10_RUNTIME_INGRESS.md" in paths
    assert "repo_map/95_MISSION_ORCHESTRATION.md" in paths

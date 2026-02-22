from __future__ import annotations

import json
from pathlib import Path

from scripts.repo_root import set_canonical_root
from scripts.sharepoint_sync import run_sync
from scripts.retrieval_service import retrieve


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    for d in ("openclaw", "scripts", "ops", "brain", "docs/_inbox", "logs", "state"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_delta_and_idempotent_rerun(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    feed = {
        "delta_token": "d1",
        "changes": [
            {"id": "1", "op": "upsert", "name": "doc_a", "title": "A", "content": "precio", "audience": "client", "etag": "e1", "modified_at": "2026-01-01"}
        ],
    }
    (w / "state" / "sharepoint_source_feed.json").write_text(json.dumps(feed), encoding="utf-8")
    out1 = run_sync(w)
    assert out1["created"] == 1
    out2 = run_sync(w)
    assert out2["idempotent_rerun"] is True


def test_rename_delete_tombstones(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    feed1 = {"delta_token": "d1", "changes": [{"id": "1", "op": "upsert", "name": "doc_a", "title": "A", "content": "x", "audience": "staff"}]}
    (w / "state" / "sharepoint_source_feed.json").write_text(json.dumps(feed1), encoding="utf-8")
    run_sync(w)

    feed2 = {"delta_token": "d2", "changes": [{"id": "1", "op": "upsert", "name": "doc_b", "title": "B", "content": "y", "audience": "staff"}]}
    (w / "state" / "sharepoint_source_feed.json").write_text(json.dumps(feed2), encoding="utf-8")
    out2 = run_sync(w)
    assert out2["renamed"] == 1

    feed3 = {"delta_token": "d3", "changes": [{"id": "1", "op": "delete"}]}
    (w / "state" / "sharepoint_source_feed.json").write_text(json.dumps(feed3), encoding="utf-8")
    out3 = run_sync(w)
    assert out3["deleted"] == 1
    tomb = (w / "state" / "sharepoint_tombstones.ndjson").read_text(encoding="utf-8")
    assert "rename" in tomb and "delete" in tomb


def test_audience_enforcement_in_retrieval(tmp_path: Path, monkeypatch):
    w = _setup(tmp_path, monkeypatch)
    feed = {
        "delta_token": "d1",
        "changes": [
            {"id": "1", "op": "upsert", "name": "c", "title": "Client", "content": "catalogo premium", "audience": "client"},
            {"id": "2", "op": "upsert", "name": "i", "title": "Internal", "content": "interno secreto", "audience": "internal"},
        ],
    }
    (w / "state" / "sharepoint_source_feed.json").write_text(json.dumps(feed), encoding="utf-8")
    run_sync(w)
    pack = retrieve(w, query="catalogo premium", principal_ctx={"audience": "client"}, filters={"audience": "client"})
    assert all(x.get("audience") == "client" for x in pack.get("final_topk", []))

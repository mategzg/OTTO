from __future__ import annotations

import json
from pathlib import Path

from scripts.chat_to_inbox_drop import run_chat_to_drop
from scripts.pending_ingest_trigger import run_trigger
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    for d in ("openclaw", "scripts", "ops", "brain", "docs/_inbox", "logs", "state", "vault/inbox_raw/_pending_drop"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_attachment_classification_and_hash(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    f = workspace / "sample.pdf"
    f.write_text("hola", encoding="utf-8")
    event = {
        "channel": "telegram",
        "peer_id": "u1",
        "message_id": "m1",
        "text": "adjunto",
        "attachments": [{"name": "sample.pdf", "path": str(f)}],
    }
    out = run_chat_to_drop(workspace, event=event, session_id="s1", source_label="test")
    meta = Path(workspace / out["package_rel"] / "source" / "ATTACHMENTS.json")
    payload = json.loads(meta.read_text(encoding="utf-8"))
    a = payload["attachments"][0]
    assert a["attachment_type"] == "document"
    assert len(a["sha256"]) == 64


def test_idempotent_hash_no_duplicate_ingest(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    p = workspace / "vault" / "inbox_raw" / "_pending_drop" / "pkg1"
    p.mkdir(parents=True, exist_ok=True)
    (p / "a.txt").write_text("same", encoding="utf-8")

    first = run_trigger(workspace, max_entries=10)
    # re-add same content
    p2 = workspace / "vault" / "inbox_raw" / "_pending_drop" / "pkg2"
    p2.mkdir(parents=True, exist_ok=True)
    (p2 / "a.txt").write_text("same", encoding="utf-8")
    second = run_trigger(workspace, max_entries=10)

    assert first["report"]["ingested_count"] >= 1
    assert second["report"]["ingested_count"] == 0


def test_backpressure_multiple_uploads(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    base = workspace / "vault" / "inbox_raw" / "_pending_drop"
    for i in range(12):
        d = base / f"pkg{i}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"f{i}.txt").write_text(f"x{i}", encoding="utf-8")
    out = run_trigger(workspace, max_entries=5)
    assert out["report"]["ingested_count"] == 5
    assert out["report"]["backpressure"]["active"] is True


def test_trigger_to_done_latency_and_report(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    d = workspace / "vault" / "inbox_raw" / "_pending_drop" / "pkg"
    d.mkdir(parents=True, exist_ok=True)
    (d / "x.txt").write_text("ok", encoding="utf-8")
    out = run_trigger(workspace, max_entries=3)
    assert out["report"]["trigger_to_done_ms"] >= 0
    assert Path(workspace / out["paths"]["json"]).is_file()

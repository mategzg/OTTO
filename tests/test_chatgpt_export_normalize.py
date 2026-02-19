import json
from pathlib import Path

from scripts.chatgpt_export_normalize import run_normalize
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw" / "sources").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_chatgpt_normalize_from_conversations_json(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    source = workspace / "vault" / "inbox_raw" / "sources" / "20260218T000000Z_abcd1234"
    payload = source / "source"
    payload.mkdir(parents=True, exist_ok=True)

    conversations = [
        {
            "id": "conv-1",
            "title": "Test",
            "mapping": {
                "node-1": {
                    "message": {
                        "id": "msg-1",
                        "author": {"role": "user"},
                        "create_time": 1700000000,
                        "content": {"parts": ["Hola mundo"]},
                    }
                },
                "node-2": {
                    "message": {
                        "id": "msg-2",
                        "author": {"role": "assistant"},
                        "create_time": 1700000100,
                        "content": {"parts": ["Respuesta"]},
                    }
                },
            },
        }
    ]
    (payload / "conversations.json").write_text(json.dumps(conversations), encoding="utf-8")
    (source / "HINTS.json").write_text(json.dumps({"suspected_kind": "chatgpt_export_candidate"}), encoding="utf-8")

    out = run_normalize(workspace, source_id="abcd1234")
    summary = out["report"]["summary"]
    assert summary["chatgpt_detected_count"] >= 1
    assert summary["normalized_count"] >= 1

    normalized = source / "normalized"
    assert (normalized / "messages.ndjson").is_file()
    assert (normalized / "conversations.ndjson").is_file()
    assert (normalized / "slices_index.json").is_file()


def test_chatgpt_normalize_generic_corpus_no_fail(monkeypatch, tmp_path: Path):
    workspace = _setup(tmp_path, monkeypatch)
    source = workspace / "vault" / "inbox_raw" / "sources" / "20260218T000000Z_ffee1111"
    payload = source / "source"
    payload.mkdir(parents=True, exist_ok=True)
    (payload / "notes.txt").write_text("generic notes", encoding="utf-8")
    (source / "HINTS.json").write_text(json.dumps({"suspected_kind": "generic_corpus"}), encoding="utf-8")

    out = run_normalize(workspace, source_id="ffee1111")
    assert out["report"]["summary"]["target_count"] == 1
    result = out["report"]["normalized_results"][0]
    assert result["suspected_kind"] == "generic_corpus"
    assert result["normalized"] is False

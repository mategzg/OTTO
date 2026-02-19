import json
from pathlib import Path

from scripts.chat_to_inbox_drop import run_chat_to_drop
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_chat_to_drop_creates_package_with_manifest(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    doc = workspace / "sample.txt"
    doc.write_text("hola", encoding="utf-8")

    out = run_chat_to_drop(
        workspace,
        event={
            "channel": "telegram",
            "peer_id": "mateo",
            "message_id": "m1",
            "timestamp": "2026-02-18T00:00:00+00:00",
            "text": "aqui va un documento",
            "attachments": [{"path": str(doc), "name": "sample.txt"}],
        },
        session_id="sid_test",
        source_label="runtime_message",
    )
    assert out["status"] == "success"
    package = workspace / out["package_rel"]
    assert (package / "README.md").is_file()
    assert (package / "MANIFEST.json").is_file()
    assert (package / "source" / "message.txt").is_file()
    assert (package / "source" / "sample.txt").is_file()

    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["file_count"] >= 3

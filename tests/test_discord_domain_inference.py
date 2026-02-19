import json
from pathlib import Path

from scripts.channel_ingress_adapter import handle_runtime_event
from scripts.corpus_triage import run_triage
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (root / "openclaw").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "ops").mkdir(parents=True, exist_ok=True)
    (root / "brain").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "_inbox").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "inbox_raw" / "_pending_drop").mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_discord_domain_inference_persists_mapping(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = handle_runtime_event(
        workspace,
        {
            "channel": "discord",
            "account_id": "acc",
            "peer_id": "u-fin",
            "channel_id": "chan-fin-1",
            "channel_name": "#Finanzas",
            "message_id": "m-fin-1",
            "text": "reporte simple",
        },
    )
    assert out["event"]["domain_slug"] == "finanzas"

    mapping_path = workspace / "state" / "discord_domains.json"
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    domains = payload.get("domains", {})
    assert domains["chan-fin-1"]["domain_slug"] == "finanzas"
    assert domains["chan-fin-1"]["channel_name_last_seen"] == "#Finanzas"


def test_discord_channel_rename_updates_name_without_breaking_slug(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    handle_runtime_event(
        workspace,
        {
            "channel": "discord",
            "account_id": "acc",
            "peer_id": "u-fin",
            "channel_id": "chan-fin-1",
            "channel_name": "#Finanzas",
            "message_id": "m-fin-1",
            "text": "mensaje uno",
        },
    )
    out = handle_runtime_event(
        workspace,
        {
            "channel": "discord",
            "account_id": "acc",
            "peer_id": "u-fin",
            "channel_id": "chan-fin-1",
            "channel_name": "#Finance-Team",
            "message_id": "m-fin-2",
            "text": "mensaje dos",
        },
    )
    assert out["event"]["domain_slug"] == "finanzas"

    mapping_path = workspace / "state" / "discord_domains.json"
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    domains = payload.get("domains", {})
    assert domains["chan-fin-1"]["domain_slug"] == "finanzas"
    assert domains["chan-fin-1"]["channel_name_last_seen"] == "#Finance-Team"


def test_discord_missing_channel_name_falls_back_unknown(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = handle_runtime_event(
        workspace,
        {
            "channel": "discord",
            "account_id": "acc",
            "peer_id": "u-x",
            "channel_id": "chan-x",
            "message_id": "m-x-1",
            "text": "sin nombre de canal",
        },
    )
    assert out["event"]["domain_slug"] == "unknown"
    mapping = json.loads((workspace / "state" / "discord_domains.json").read_text(encoding="utf-8"))
    assert mapping["domains"]["chan-x"]["domain_slug"] == "unknown"


def test_discord_drop_event_meta_contains_recommended_domain(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    attach = workspace / "docs" / "finanzas.txt"
    attach.parent.mkdir(parents=True, exist_ok=True)
    attach.write_text("contenido", encoding="utf-8")

    out = handle_runtime_event(
        workspace,
        {
            "channel": "discord",
            "account_id": "acc",
            "peer_id": "u-drop",
            "channel_id": "chan-fin-9",
            "channel_name": "#Finanzas",
            "thread_id": "thread-abc",
            "message_id": "m-drop",
            "text": "adjunto de dominio",
            "attachments": [{"name": "finanzas.txt", "path": str(attach)}],
        },
    )
    assert out["actions"]["drop"]["status"] == "success"
    package = workspace / out["actions"]["drop"]["package_rel"] / "source" / "EVENT_META.json"
    payload = json.loads(package.read_text(encoding="utf-8"))
    assert payload["recommended_domain"] == "finanzas"
    assert payload["domain_slug"] == "finanzas"
    assert payload["channel_name"] == "#Finanzas"


def test_triage_prefers_recommended_domain_from_event_meta(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    source_dir = workspace / "vault" / "inbox_raw" / "sources" / "src-domain-1" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "notes.txt").write_text("contenido generico", encoding="utf-8")
    (source_dir / "EVENT_META.json").write_text(
        json.dumps(
            {
                "channel": "discord",
                "channel_id": "chan-fin-77",
                "channel_name": "#Finanzas",
                "domain_slug": "finanzas",
                "recommended_domain": "finanzas",
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    triage = run_triage(workspace)["report"]
    assert triage["sources"]
    assert triage["sources"][0]["recommended_domain"] == "finanzas"

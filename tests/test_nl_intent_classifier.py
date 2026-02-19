import json
from pathlib import Path

from scripts.nl_intent_classifier import classify_intent, run_classifier
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


def test_classifier_detects_corpus_and_memory_signals():
    text = "Decision: prefiero este enfoque\n" + ("linea\n" * 30)
    out = classify_intent(text=text, attachments=[], channel="telegram", actor_type="")
    assert "contains_corpus" in out["labels"]
    assert "memory_worthy" in out["labels"]
    assert out["confidence"] in {"high", "medium"}


def test_classifier_detects_worker_auth_whatsapp():
    out = classify_intent(
        text="Soy trabajador backoffice, password ok para atender orden",
        attachments=[],
        channel="whatsapp",
        actor_type="worker",
    )
    assert "requires_worker_auth" in out["labels"]
    assert "sg_worthy" in out["labels"]


def test_run_classifier_writes_log(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = run_classifier(
        workspace,
        text="Adjunto cotizacion del cliente",
        attachments=[{"name": "cotizacion.pdf"}],
        channel="whatsapp",
        actor_type="client",
    )
    assert out["result"]["primary_intent"]
    log_path = workspace / "logs" / "nl_intent_classifier_latest.json"
    assert log_path.is_file()
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["result"]["labels"]

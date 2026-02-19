from pathlib import Path

from scripts.repo_root import set_canonical_root
from scripts.sg_channel_policy import evaluate_sg_event
from scripts.sg_promotion import approve_promotion, enqueue_promotion, process_promotions


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


def test_sg_policy_classification_and_auth(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    out = evaluate_sg_event(
        workspace,
        {
            "channel": "whatsapp",
            "text": "soy trabajador backoffice, orden del cliente",
            "actor_type": "worker",
            "auth": {"password_ok": True, "owner_approved": False},
        },
    )
    assert out["actor"] == "worker"
    assert out["auth"]["status"] in {"pending_owner", "challenge"}


def test_sg_promotion_auto_low_and_approval_high(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)

    low = enqueue_promotion(
        workspace,
        {"text": "estado de seguimiento", "source_ref": "runtime:a", "sensitivity": "low"},
    )
    assert low["status"] == "enqueued"

    high = enqueue_promotion(
        workspace,
        {"text": "token secreto del cliente", "source_ref": "runtime:b", "sensitivity": "high"},
    )
    assert high["status"] == "enqueued"

    first = process_promotions(workspace)
    assert first["summary"]["promoted_auto"] >= 1
    assert first["summary"]["pending_approval"] >= 1

    second = approve_promotion(workspace, high["promotion_id"])
    assert second["summary"]["promoted"] >= 2

from __future__ import annotations

from pathlib import Path

from scripts.evidence_guard import build_and_validate
from scripts.repo_root import set_canonical_root
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


def test_audience_filter_before_topk(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    p1 = workspace / "brain" / "sg" / "doc_client.md"
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("<!-- audience: client -->\nprecio final cliente premium\n", encoding="utf-8")
    p2 = workspace / "brain" / "sg" / "doc_internal.md"
    p2.write_text("<!-- audience: internal -->\nprecio final cliente premium\n", encoding="utf-8")

    pack = retrieve(
        workspace,
        query="precio final cliente",
        principal_ctx={"audience": "client"},
        retrieval_mode="grounded_answer",
        filters={"audience": "client"},
    )
    assert pack["diagnostics"]["requested_audience"] == "client"
    assert pack["diagnostics"]["audience_filtered_count"] >= 1
    assert all(str(x.get("audience", "")) == "client" for x in pack.get("final_topk", []))


def test_answer_gate_blocks_wrong_audience_citations():
    pack = {
        "final_topk": [
            {"path": "brain/sg/internal.md", "audience": "internal", "doc_id": "d", "doc_version": "1", "section_path": "", "locator": {}, "content_hash": "x"}
        ],
        "diagnostics": {"requested_audience": "client", "abstention_hint": False},
    }
    out = build_and_validate(mode="grounded_answer", answer="ok", retrieval_pack=pack, confidence="high", actions_taken=[])
    assert out["valid"] is False
    assert out["reason"] == "audience_mismatch"
    assert out["output"]["answer"] == "NO_VERIFICADO"


def test_answer_gate_abstains_without_evidence():
    pack = {"final_topk": [], "diagnostics": {"requested_audience": "client", "abstention_hint": True}}
    out = build_and_validate(mode="grounded_answer", answer="ok", retrieval_pack=pack, confidence="high", actions_taken=[])
    assert out["valid"] is False
    assert out["output"]["answer"] == "NO_VERIFICADO"

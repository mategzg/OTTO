from pathlib import Path

from scripts.evidence_guard import build_and_validate
from scripts.nl_skill_router import run_nl_router


def test_grounded_requires_citations():
    out = build_and_validate(mode="grounded_answer", answer="x", retrieval_pack={"final_topk": [], "diagnostics": {}}, confidence="high")
    assert out["valid"] is False
    assert out["output"]["answer"] == "NO_VERIFICADO"


def test_abstention_out_of_kb_from_router(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)

    # Enable retrieval v2 with very high threshold to force abstention hint.
    (tmp_path / "state" / "retrieval_policy.json").write_text(
        '{"retrieval_v2": {"enabled": true, "min_evidence_score": 1000}}\n',
        encoding="utf-8",
    )

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    out = run_nl_router(
        tmp_path,
        text="hecho interno que no existe",
        channel="telegram",
        conversation_id="u1",
        thread_id="t",
        message_id="m",
    )
    assert out["status"] == "success"
    assert out["evidence_guard"]["valid"] is False
    assert out["evidence_guard"]["output"]["answer"] == "NO_VERIFICADO"

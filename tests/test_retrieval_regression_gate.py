import json
from pathlib import Path

from scripts.retrieval_regression_gate import run_gate


def test_retrieval_regression_by_category_author(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "brain" / "domains" / "sg_acabados").mkdir(parents=True)
    (tmp_path / "brain" / "domains" / "sg_acabados" / "filosofia.md").write_text("filosofia comercial de valor\n", encoding="utf-8")

    (tmp_path / "state" / "retrieval_regression_set.json").write_text(
        json.dumps({
            "thresholds": {"min_hit_rate": 0.5},
            "items": [
                {"query": "filosofia comercial", "expect": "filosofia", "category": "filosofia", "author": "mateo"}
            ],
        }),
        encoding="utf-8",
    )

    import scripts.retrieval_regression_gate as rg

    import scripts.retrieval_service as rs
    monkeypatch.setattr(rg, "get_canonical_root", lambda root: Path(root).resolve())
    monkeypatch.setattr(rs, "get_canonical_root", lambda root: Path(root).resolve())
    out = run_gate(tmp_path)
    assert out["status"] == "pass"
    assert out["summary"]["categories"]["filosofia"] >= 1.0
    assert out["summary"]["authors"]["mateo"] >= 1.0

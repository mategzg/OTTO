#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root
from scripts.retrieval_service import retrieve

SET_PATH = Path("state/retrieval_regression_set.json")
REPORT_PATH = Path("docs/_inbox/retrieval_regression_gate_latest.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def run_gate(root: str | Path) -> Dict[str, Any]:
    canonical = get_canonical_root(root)
    payload = _load_json(canonical / SET_PATH)
    items = payload.get("items", []) if isinstance(payload.get("items", []), list) else []
    thresholds = payload.get("thresholds", {}) if isinstance(payload.get("thresholds", {}), dict) else {}
    min_hit = float(thresholds.get("min_hit_rate", 0.7))

    results: List[Dict[str, Any]] = []
    by_cat: Dict[str, List[int]] = {}
    by_author: Dict[str, List[int]] = {}

    for item in items:
        query = str(item.get("query", "")).strip()
        expect = str(item.get("expect", "")).strip().lower()
        category = str(item.get("category", "unknown"))
        author = str(item.get("author", "unknown"))
        out = retrieve(canonical, query=query, principal_ctx={"user_id": "qa"})
        hay = "\n".join(r.get("text", "") for r in out.get("final_topk", [])) .lower()
        ok = bool(expect and expect in hay)
        results.append({"query": query, "expect": expect, "ok": ok, "category": category, "author": author})
        by_cat.setdefault(category, []).append(1 if ok else 0)
        by_author.setdefault(author, []).append(1 if ok else 0)

    def rate(xs: List[int]) -> float:
        return float(sum(xs)) / float(len(xs)) if xs else 0.0

    categories = {k: rate(v) for k, v in sorted(by_cat.items())}
    authors = {k: rate(v) for k, v in sorted(by_author.items())}
    global_rate = rate([1 if r["ok"] else 0 for r in results])

    out = {
        "status": "pass" if global_rate >= min_hit else "fail",
        "summary": {
            "total": len(results),
            "global_hit_rate": global_rate,
            "min_hit_rate": min_hit,
            "categories": categories,
            "authors": authors,
        },
        "results": results,
    }
    rp = canonical / REPORT_PATH
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return out

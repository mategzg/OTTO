#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path
from typing import Dict, Any, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")


def query(root: str | Path, q: str, k: int = 6) -> Dict[str, Any]:
    r = get_canonical_root(root)
    reg = r / "state" / "repomap_registry.json"
    if not reg.is_file():
        from scripts.repomap_index_build import build
        build(r)
    data = json.loads(reg.read_text(encoding="utf-8"))
    tokens = sorted(set(TOKEN_RE.findall(q.lower())))
    scores: Dict[str, int] = {}
    for t in tokens:
        for rid in data.get("inverted", {}).get(t, []):
            scores[rid] = scores.get(rid, 0) + 1
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:max(1, k)]
    results: List[Dict[str, Any]] = []
    for rid, sc in ranked:
        rec = data["records"].get(rid, {})
        results.append({"path": rec.get("path"), "title": rec.get("title"), "score": sc, "source_ref": rec.get("source_ref")})
    return {"question": q, "tokens": tokens, "result_count": len(results), "results": results, "version": 1}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--q", required=True)
    ap.add_argument("--k", type=int, default=6)
    args = ap.parse_args()
    out = query(args.root, args.q, args.k)
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))

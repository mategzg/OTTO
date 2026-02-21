#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/retrieval_policy.json")

TOKEN_RE = re.compile(r"[a-z0-9_áéíóúñ]+", re.IGNORECASE)

DEFAULT_POLICY: Dict[str, Any] = {
    "retrieval_v2": {
        "enabled": False,
        "lexical_top_n": 20,
        "vector_top_n": 20,
        "final_top_k": 12,
        "max_chunks_per_doc": 3,
        "min_evidence_score": 0.1,
    }
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text or "") if len(t) > 1]


def _policy(root: Path) -> Dict[str, Any]:
    payload = _load_json(root / POLICY_PATH)
    out = dict(DEFAULT_POLICY["retrieval_v2"])
    incoming = payload.get("retrieval_v2", {}) if isinstance(payload.get("retrieval_v2"), dict) else {}
    out.update(incoming)
    return out


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _scan_docs(root: Path) -> List[Dict[str, Any]]:
    paths: List[Path] = []
    for rel in ("brain", "memory", "repo_map", "docs"):
        base = root / rel
        if base.exists():
            paths.extend(base.rglob("*.md"))
    out: List[Dict[str, Any]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(root).as_posix()
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue
            out.append(
                {
                    "chunk_id": f"{rel}:{idx}",
                    "doc_id": rel,
                    "doc_version": _content_hash(text),
                    "path": rel,
                    "section_path": "",
                    "locator": {"start_line": idx, "end_line": idx},
                    "content_hash": _content_hash(line),
                    "text": line,
                    "tokens": _tokenize(line),
                }
            )
    return out


def retrieve(
    root: str | Path,
    *,
    query: str,
    principal_ctx: Dict[str, Any] | None = None,
    retrieval_mode: str = "grounded_answer",
    filters: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    cfg = _policy(canonical_root)

    q_tokens = _tokenize(query)
    chunks = _scan_docs(canonical_root)

    lexical_top_n = max(1, int(cfg.get("lexical_top_n", 20)))
    vector_top_n = max(1, int(cfg.get("vector_top_n", 20)))
    final_top_k = max(1, int(cfg.get("final_top_k", 12)))
    max_chunks_per_doc = max(1, int(cfg.get("max_chunks_per_doc", 3)))

    lexical_hits: List[Dict[str, Any]] = []
    vector_hits: List[Dict[str, Any]] = []

    for c in chunks:
        overlap = len(set(q_tokens).intersection(set(c.get("tokens", []))))
        if overlap <= 0:
            continue
        bm25 = float(overlap)
        vector = float(overlap) / max(1.0, len(q_tokens))
        entry = dict(c)
        entry["scores"] = {"bm25": bm25, "vector": vector, "fused": 0.0, "rerank": 0.0}
        lexical_hits.append(entry)
        vector_hits.append(entry)

    lexical_hits.sort(key=lambda x: (-x["scores"]["bm25"], x["path"], x["locator"]["start_line"]))
    vector_hits.sort(key=lambda x: (-x["scores"]["vector"], x["path"], x["locator"]["start_line"]))

    lexical_hits = lexical_hits[:lexical_top_n]
    vector_hits = vector_hits[:vector_top_n]

    # union + dedupe
    union: Dict[str, Dict[str, Any]] = {}
    for row in lexical_hits + vector_hits:
        cid = row["chunk_id"]
        if cid not in union:
            union[cid] = row

    # simple fused and rerank (deterministic)
    reranked: List[Dict[str, Any]] = []
    for cid, row in union.items():
        in_lex = next((i for i, r in enumerate(lexical_hits, start=1) if r["chunk_id"] == cid), None)
        in_vec = next((i for i, r in enumerate(vector_hits, start=1) if r["chunk_id"] == cid), None)
        rrf = 0.0
        if in_lex is not None:
            rrf += 1.0 / (60 + in_lex)
        if in_vec is not None:
            rrf += 1.0 / (60 + in_vec)
        row2 = dict(row)
        row2["scores"] = {
            "bm25": float(row["scores"]["bm25"]),
            "vector": float(row["scores"]["vector"]),
            "fused": float(rrf),
            "rerank": float(rrf),
        }
        reranked.append(row2)

    reranked.sort(key=lambda x: (-x["scores"]["rerank"], x["path"], x["locator"]["start_line"]))

    # packer constraints
    final_topk: List[Dict[str, Any]] = []
    per_doc: Dict[str, int] = {}
    for row in reranked:
        doc = row["doc_id"]
        used = per_doc.get(doc, 0)
        if used >= max_chunks_per_doc:
            continue
        final_topk.append(row)
        per_doc[doc] = used + 1
        if len(final_topk) >= final_top_k:
            break

    max_score = max((float(r["scores"]["rerank"]) for r in final_topk), default=0.0)
    min_score = min((float(r["scores"]["rerank"]) for r in final_topk), default=0.0)

    return {
        "query_rewrites": [query],
        "candidates_lexical": lexical_hits,
        "candidates_vector": vector_hits,
        "candidates_union": list(union.values()),
        "reranked": reranked,
        "final_topk": final_topk,
        "diagnostics": {
            "retrieval_mode": retrieval_mode,
            "enabled": bool(cfg.get("enabled", False)),
            "acl_filtered_count": 0,
            "dedupe_count": max(0, len(lexical_hits) + len(vector_hits) - len(union)),
            "rerank_model": "rrf_v1",
            "scores_summary": {"min": min_score, "max": max_score},
            "coverage": len(final_topk),
            "min_evidence_score": float(cfg.get("min_evidence_score", 0.1)),
            "abstention_hint": max_score < float(cfg.get("min_evidence_score", 0.1)),
            "principal_ctx": principal_ctx or {},
            "filters": filters or {},
        },
    }

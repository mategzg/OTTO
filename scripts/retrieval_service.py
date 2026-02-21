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
        "rerank_top_m": 30,
        "final_top_k": 12,
        "max_chunks_per_doc": 3,
        "min_evidence_score": 0.1,
        "fusion_mode": "rrf",  # rrf|weighted
        "rrf_k": 60,
        "weighted_bm25": 0.6,
        "weighted_vector": 0.4,
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


def _jaccard(a: List[str], b: List[str]) -> float:
    sa = set(a)
    sb = set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa.intersection(sb))
    uni = len(sa.union(sb))
    return float(inter) / float(max(1, uni))


def _phrase_boost(query: str, text: str) -> float:
    q = " ".join(_tokenize(query))
    t = " ".join(_tokenize(text))
    if q and q in t:
        return 1.0
    # light ordered-token boost
    tokens = _tokenize(query)
    if len(tokens) >= 2:
        two = " ".join(tokens[:2])
        if two in t:
            return 0.35
    return 0.0


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
        doc_version = _content_hash(text)
        for idx, line in enumerate(lines, start=1):
            clean = line.strip()
            if not clean:
                continue
            out.append(
                {
                    "chunk_id": f"{rel}:{idx}",
                    "doc_id": rel,
                    "doc_version": doc_version,
                    "path": rel,
                    "section_path": "",
                    "locator": {"start_line": idx, "end_line": idx},
                    "content_hash": _content_hash(clean),
                    "text": clean,
                    "tokens": _tokenize(clean),
                }
            )
    return out


def _score_chunk(query: str, q_tokens: List[str], chunk: Dict[str, Any]) -> Dict[str, float]:
    tokens = chunk.get("tokens", [])
    overlap = len(set(q_tokens).intersection(set(tokens)))
    bm25 = float(overlap)
    vector = _jaccard(q_tokens, tokens)
    phrase = _phrase_boost(query, str(chunk.get("text", "")))
    return {"bm25": bm25, "vector": vector, "phrase": phrase}


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
    rerank_top_m = max(1, int(cfg.get("rerank_top_m", 30)))
    final_top_k = max(1, int(cfg.get("final_top_k", 12)))
    max_chunks_per_doc = max(1, int(cfg.get("max_chunks_per_doc", 3)))

    lexical_scored: List[Dict[str, Any]] = []
    vector_scored: List[Dict[str, Any]] = []

    for c in chunks:
        s = _score_chunk(query, q_tokens, c)
        if s["bm25"] <= 0 and s["vector"] <= 0:
            continue
        row = dict(c)
        row["scores"] = {"bm25": s["bm25"], "vector": s["vector"], "fused": 0.0, "rerank": 0.0}
        lexical_scored.append(row)
        vector_scored.append(row)

    lexical_scored.sort(key=lambda x: (-x["scores"]["bm25"], x["path"], x["locator"]["start_line"]))
    vector_scored.sort(key=lambda x: (-x["scores"]["vector"], x["path"], x["locator"]["start_line"]))

    lexical_hits = lexical_scored[:lexical_top_n]
    vector_hits = vector_scored[:vector_top_n]

    # union + dedupe
    union: Dict[str, Dict[str, Any]] = {}
    for row in lexical_hits + vector_hits:
        cid = row["chunk_id"]
        if cid not in union:
            union[cid] = row

    # fusion
    fusion_mode = str(cfg.get("fusion_mode", "rrf")).strip().lower()
    rrf_k = max(1, int(cfg.get("rrf_k", 60)))
    w_bm25 = float(cfg.get("weighted_bm25", 0.6))
    w_vector = float(cfg.get("weighted_vector", 0.4))

    fused: List[Dict[str, Any]] = []
    for cid, row in union.items():
        lex_rank = next((i for i, r in enumerate(lexical_hits, start=1) if r["chunk_id"] == cid), None)
        vec_rank = next((i for i, r in enumerate(vector_hits, start=1) if r["chunk_id"] == cid), None)

        if fusion_mode == "weighted":
            fused_score = (w_bm25 * float(row["scores"]["bm25"])) + (w_vector * float(row["scores"]["vector"]))
        else:
            # default rrf
            fused_score = 0.0
            if lex_rank is not None:
                fused_score += 1.0 / float(rrf_k + lex_rank)
            if vec_rank is not None:
                fused_score += 1.0 / float(rrf_k + vec_rank)

        row2 = dict(row)
        row2["scores"] = {
            "bm25": float(row["scores"]["bm25"]),
            "vector": float(row["scores"]["vector"]),
            "fused": float(fused_score),
            "rerank": 0.0,
        }
        fused.append(row2)

    fused.sort(key=lambda x: (-x["scores"]["fused"], x["path"], x["locator"]["start_line"]))

    # rerank stage (deterministic, phrase-aware)
    rerank_input = fused[:rerank_top_m]
    reranked: List[Dict[str, Any]] = []
    for row in rerank_input:
        phrase = _phrase_boost(query, str(row.get("text", "")))
        rerank = float(row["scores"]["fused"]) + (0.2 * phrase)
        row2 = dict(row)
        row2["scores"] = {
            "bm25": float(row["scores"]["bm25"]),
            "vector": float(row["scores"]["vector"]),
            "fused": float(row["scores"]["fused"]),
            "rerank": float(rerank),
        }
        reranked.append(row2)

    reranked.sort(key=lambda x: (-x["scores"]["rerank"], x["path"], x["locator"]["start_line"]))

    # context packer constraints
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

    min_score = min((float(r["scores"]["rerank"]) for r in final_topk), default=0.0)
    max_score = max((float(r["scores"]["rerank"]) for r in final_topk), default=0.0)

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
            "fusion_mode": fusion_mode,
            "lexical_candidates": len(lexical_hits),
            "vector_candidates": len(vector_hits),
            "union_count": len(union),
            "acl_filtered_count": 0,
            "dedupe_count": max(0, len(lexical_hits) + len(vector_hits) - len(union)),
            "rerank_model": "phrase_aware_v1",
            "rerank_latency_ms": 0,
            "scores_summary": {"min": min_score, "max": max_score},
            "coverage": len(final_topk),
            "min_evidence_score": float(cfg.get("min_evidence_score", 0.1)),
            "abstention_hint": max_score < float(cfg.get("min_evidence_score", 0.1)),
            "principal_ctx": principal_ctx or {},
            "filters": filters or {},
        },
    }

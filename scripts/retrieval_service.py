#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/retrieval_policy.json")
TOKEN_RE = re.compile(r"[a-z0-9_áéíóúñ]+", re.IGNORECASE)
STOPWORDS = {
    # es
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "u", "en", "con", "sin",
    "por", "para", "del", "al", "que", "como", "se", "es", "a", "mi", "tu", "su", "lo", "le", "te",
    "si", "no", "ya", "mas", "más", "sobre", "esta", "este", "estos", "estas",
    # en
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "without", "is", "are", "be",
    "as", "by", "from", "at", "that", "this", "these", "those", "it",
}

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
        "channel_path_policy": {
            "whatsapp": {
                "client": {
                    "allow_prefixes": [
                        "brain/domains/sg_acabados/",
                        "brain/sg/",
                        "docs/empresa/public/",
                        "docs/public/",
                    ],
                    "deny_prefixes": [
                        "memory/",
                        "repo_map/",
                        "brain/domains/personal_ops/",
                        "brain/domains/openclaw_ops/",
                    ],
                }
            }
        },
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
    out: List[str] = []
    for raw in TOKEN_RE.findall(text or ""):
        t = raw.lower()
        if len(t) <= 1:
            continue
        if t in STOPWORDS:
            continue
        out.append(t)
    return out


def _policy(root: Path) -> Dict[str, Any]:
    payload = _load_json(root / POLICY_PATH)
    out = dict(DEFAULT_POLICY["retrieval_v2"])
    incoming = payload.get("retrieval_v2", {}) if isinstance(payload.get("retrieval_v2"), dict) else {}
    out.update(incoming)
    return out


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _principal_tokens(principal_ctx: Dict[str, Any] | None) -> Set[str]:
    ctx = principal_ctx or {}
    out: Set[str] = set()
    user_id = str(ctx.get("user_id", "")).strip()
    if user_id:
        out.add(f"user:{user_id}")
    for gid in ctx.get("group_ids", []) if isinstance(ctx.get("group_ids", []), list) else []:
        g = str(gid).strip()
        if g:
            out.add(f"group:{g}")
    for role in ctx.get("roles", []) if isinstance(ctx.get("roles", []), list) else []:
        r = str(role).strip()
        if r:
            out.add(f"role:{r}")
    return out


def _is_allowed(chunk: Dict[str, Any], principal_ctx: Dict[str, Any] | None) -> bool:
    allow = chunk.get("acl_allow", ["public"])
    deny = chunk.get("acl_deny", [])
    allow_set = {str(x).strip().lower() for x in allow if str(x).strip()}
    deny_set = {str(x).strip().lower() for x in deny if str(x).strip()}
    principal = {x.lower() for x in _principal_tokens(principal_ctx)}

    denied = bool(principal.intersection(deny_set))
    if denied:
        return False
    if "public" in allow_set:
        return True
    return bool(principal.intersection(allow_set))


def _extract_doc_acl(lines: List[str]) -> Dict[str, List[str]]:
    acl_allow = ["public"]
    acl_deny: List[str] = []
    for line in lines[:12]:
        l = line.strip().lower()
        if l.startswith("<!--") and "acl_allow:" in l:
            raw = l.split("acl_allow:", 1)[1].replace("-->", "").strip()
            vals = [x.strip() for x in raw.split(",") if x.strip()]
            if vals:
                acl_allow = vals
        if l.startswith("<!--") and "acl_deny:" in l:
            raw = l.split("acl_deny:", 1)[1].replace("-->", "").strip()
            vals = [x.strip() for x in raw.split(",") if x.strip()]
            if vals:
                acl_deny = vals
    return {"acl_allow": acl_allow, "acl_deny": acl_deny}


def _jaccard(a: List[str], b: List[str]) -> float:
    sa = set(a)
    sb = set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa.intersection(sb))
    uni = len(sa.union(sb))
    return float(inter) / float(max(1, uni))


def _phrase_boost(query: str, text: str) -> float:
    q_tokens_raw = [t.lower() for t in TOKEN_RE.findall(query or "") if len(t) > 1]
    t_tokens_raw = [t.lower() for t in TOKEN_RE.findall(text or "") if len(t) > 1]
    q = " ".join(q_tokens_raw)
    t = " ".join(t_tokens_raw)
    if q and q in t:
        return 1.0
    # light ordered-token boost
    if len(q_tokens_raw) >= 2:
        two = " ".join(q_tokens_raw[:2])
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
        acl_meta = _extract_doc_acl(lines)
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
                    "acl_allow": list(acl_meta.get("acl_allow", ["public"])),
                    "acl_deny": list(acl_meta.get("acl_deny", [])),
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


def _channel_path_allowed(path: str, principal_ctx: Dict[str, Any] | None, cfg: Dict[str, Any]) -> bool:
    ctx = principal_ctx or {}
    channel = str(ctx.get("channel", "")).strip().lower()
    actor = str(ctx.get("actor_type", "")).strip().lower() or "client"
    if not channel:
        return True

    channel_policies = cfg.get("channel_path_policy", {}) if isinstance(cfg.get("channel_path_policy", {}), dict) else {}
    chan_cfg = channel_policies.get(channel, {}) if isinstance(channel_policies.get(channel, {}), dict) else {}
    role_cfg = chan_cfg.get(actor, {}) if isinstance(chan_cfg.get(actor, {}), dict) else {}
    if not role_cfg:
        return True

    clean_path = str(path or "").strip().lower()
    allow_prefixes = [str(x).strip().lower() for x in role_cfg.get("allow_prefixes", []) if str(x).strip()]
    deny_prefixes = [str(x).strip().lower() for x in role_cfg.get("deny_prefixes", []) if str(x).strip()]

    if any(clean_path.startswith(prefix) for prefix in deny_prefixes):
        return False
    if allow_prefixes:
        return any(clean_path.startswith(prefix) for prefix in allow_prefixes)
    return True


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
    acl_filtered_count = 0
    channel_filtered_count = 0

    for c in chunks:
        if not _channel_path_allowed(str(c.get("path", "")), principal_ctx, cfg):
            channel_filtered_count += 1
            continue
        if not _is_allowed(c, principal_ctx):
            acl_filtered_count += 1
            continue
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
            "acl_filtered_count": acl_filtered_count,
            "channel_filtered_count": channel_filtered_count,
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

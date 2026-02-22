#!/usr/bin/env python3
import argparse
import hashlib
import re
from collections import Counter, defaultdict

from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-./:@]+")


def tokenize(text: str):
    return [t.lower() for t in TOKEN_RE.findall(text)]


def term_to_index(term: str, dim: int):
    return int(hashlib.md5(term.encode()).hexdigest(), 16) % dim


def sparse_query_vec(text: str, sparse_dim: int = 200000):
    tf = Counter(tokenize(text))
    idx = sorted({term_to_index(t, sparse_dim) for t in tf.keys()})
    vals_map = defaultdict(float)
    for t, c in tf.items():
        vals_map[term_to_index(t, sparse_dim)] += float(c)
    vals = [vals_map[i] for i in idx]
    return models.SparseVector(indices=idx, values=vals)


def build_filter(args):
    must = []
    for field in ["audience", "domain", "channel", "peer_id", "thread_id"]:
        val = getattr(args, field)
        if val:
            must.append(models.FieldCondition(key=field, match=models.MatchValue(value=val)))
    return models.Filter(must=must) if must else None


def rrf_fuse(dense_hits, sparse_hits, k=60):
    scores = defaultdict(float)
    by_id = {}
    for rank, h in enumerate(dense_hits, 1):
        scores[h.id] += 1.0 / (k + rank)
        by_id[h.id] = h
    for rank, h in enumerate(sparse_hits, 1):
        scores[h.id] += 1.0 / (k + rank)
        by_id[h.id] = h
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(s, by_id[i]) for i, s in fused]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--collection", default="rag_local")
    ap.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    ap.add_argument("--model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--top-n-candidates", type=int, default=120)
    ap.add_argument("--top-k-final", type=int, default=10)
    ap.add_argument("--max-per-doc", type=int, default=2)
    ap.add_argument("--sparse-dim", type=int, default=200000)
    ap.add_argument("--audience", default=None)
    ap.add_argument("--domain", default=None)
    ap.add_argument("--channel", default=None)
    ap.add_argument("--peer_id", default=None)
    ap.add_argument("--thread_id", default=None)
    args = ap.parse_args()

    filt = build_filter(args)
    q = QdrantClient(url=args.qdrant_url, timeout=45)

    model = SentenceTransformer(args.model)
    qvec = model.encode([args.query], normalize_embeddings=True)[0].tolist()

    dense_hits = q.search(
        collection_name=args.collection,
        query_vector=models.NamedVector(name="dense", vector=qvec),
        query_filter=filt,
        limit=args.top_n_candidates,
        with_payload=True,
    )

    sq = sparse_query_vec(args.query, args.sparse_dim)
    sparse_hits = []
    if sq.indices:
        sparse_hits = q.search(
            collection_name=args.collection,
            query_vector=models.NamedSparseVector(name="sparse", vector=sq),
            query_filter=filt,
            limit=args.top_n_candidates,
            with_payload=True,
        )

    fused = rrf_fuse(dense_hits, sparse_hits)

    by_doc = defaultdict(int)
    final = []
    for score, h in fused:
        src = h.payload.get("source", "unknown") if h.payload else "unknown"
        if by_doc[src] >= args.max_per_doc:
            continue
        by_doc[src] += 1
        final.append((score, h))
        if len(final) >= args.top_k_final:
            break

    if not final:
        print("NO_VERIFICADO + GAPS: no evidence for requested filters/query")
        return

    for i, (score, h) in enumerate(final, 1):
        p = h.payload or {}
        txt = (p.get("text", "") or "").replace("\n", " ")[:240]
        loc = p.get("locator", p.get("source", "unknown"))
        print(f"[{i}] score={score:.5f} source={p.get('source','unknown')}\n  {txt}\n  Source: {loc}\n")


if __name__ == "__main__":
    main()

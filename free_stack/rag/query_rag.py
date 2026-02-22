#!/usr/bin/env python3
import argparse, re
from collections import defaultdict
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi


def tok(s):
    return re.findall(r"\w+", s.lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--query', required=True)
    ap.add_argument('--collection', default='rag_local')
    ap.add_argument('--qdrant-url', default='http://127.0.0.1:6333')
    ap.add_argument('--model', default='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    ap.add_argument('--top-k', type=int, default=5)
    args = ap.parse_args()

    q = QdrantClient(url=args.qdrant_url, timeout=30)
    model = SentenceTransformer(args.model)
    qvec = model.encode([args.query], normalize_embeddings=True)[0].tolist()

    dense_hits = q.search(collection_name=args.collection, query_vector=qvec, limit=40, with_payload=True)
    docs = [h.payload.get('text', '') for h in dense_hits]

    bm25 = BM25Okapi([tok(d) for d in docs]) if docs else None
    bm_scores = bm25.get_scores(tok(args.query)) if bm25 else []

    fused = []
    for i, h in enumerate(dense_hits):
        dense = float(h.score or 0)
        sparse = float(bm_scores[i]) if len(bm_scores) > i else 0.0
        fused.append((0.7 * dense + 0.3 * (sparse / (max(bm_scores) if len(bm_scores) else 1 or 1)), h))

    fused.sort(key=lambda x: x[0], reverse=True)
    for rank, (score, h) in enumerate(fused[:args.top_k], 1):
        t = h.payload.get('text', '').replace('\n', ' ')[:260]
        s = h.payload.get('source', 'unknown')
        print(f"[{rank}] score={score:.4f} source={s}\n  {t}\n")


if __name__ == '__main__':
    main()

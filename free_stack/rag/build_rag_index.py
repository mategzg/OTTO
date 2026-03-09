#!/usr/bin/env python3
import argparse
import hashlib
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-./:@]+")


def tokenize(text: str):
    return [t.lower() for t in TOKEN_RE.findall(text)]


def split_chunks(text, chunk_size=900, overlap=120):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    out, i = [], 0
    while i < len(text):
        j = min(len(text), i + chunk_size)
        out.append((text[i:j], i, j))
        i += max(1, chunk_size - overlap)
    return out


def iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() == ".txt":
            yield p


def term_to_index(term: str, dim: int):
    return int(hashlib.md5(term.encode()).hexdigest(), 16) % dim


def sparse_from_tokens(tokens, idf_map, sparse_dim=200_000):
    tf = Counter(tokens)
    acc = defaultdict(float)
    for t, c in tf.items():
        idx = term_to_index(t, sparse_dim)
        acc[idx] += float(c) * idf_map.get(t, 1.0)
    indices = sorted(acc.keys())
    values = [acc[i] for i in indices]
    return models.SparseVector(indices=indices, values=values)


def ensure_payload_indexes(q: QdrantClient, collection: str):
    keyword_fields = [
        "audience",
        "domain",
        "channel",
        "peer_id",
        "thread_id",
        "doc_type",
        "source",
        "customer_id",
        "lead_id",
    ]
    int_fields = ["created_at", "updated_at"]
    for f in keyword_fields:
        q.create_payload_index(collection, f, models.PayloadSchemaType.KEYWORD)
    for f in int_fields:
        q.create_payload_index(collection, f, models.PayloadSchemaType.INTEGER)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--collection", default="rag_local")
    ap.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    ap.add_argument("--model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    ap.add_argument("--chunk-size", type=int, default=900)
    ap.add_argument("--overlap", type=int, default=120)
    ap.add_argument("--sparse-dim", type=int, default=200000)
    ap.add_argument("--audience", default="internal")
    ap.add_argument("--domain", default="ops")
    ap.add_argument("--channel", default="telegram")
    ap.add_argument("--peer-id", default="unknown")
    ap.add_argument("--thread-id", default="none")
    ap.add_argument("--doc-type", default="note")
    ap.add_argument("--customer-id", default="")
    ap.add_argument("--lead-id", default="")
    args = ap.parse_args()

    files = list(iter_files(Path(args.input_dir)))
    if not files:
        print("NO_VERIFICADO + GAPS: no .txt files found")
        return

    dense_model = SentenceTransformer(args.model)
    dense_dim = dense_model.get_sentence_embedding_dimension()

    q = QdrantClient(url=args.qdrant_url, timeout=60)
    q.recreate_collection(
        args.collection,
        vectors_config={"dense": models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams()},
    )

    all_chunks = []
    df = Counter()
    for fp in files:
        raw = fp.read_text(errors="ignore")
        for chunk_text, c0, c1 in split_chunks(raw, args.chunk_size, args.overlap):
            toks = tokenize(chunk_text)
            if not toks:
                continue
            all_chunks.append((fp, chunk_text, c0, c1, toks))
            for t in set(toks):
                df[t] += 1

    n_docs = max(1, len(all_chunks))
    idf = {t: math.log((n_docs - f + 0.5) / (f + 0.5) + 1.0) for t, f in df.items()}

    batch = []
    now = int(time.time())
    texts = [x[1] for x in all_chunks]
    dense_vecs = dense_model.encode(texts, normalize_embeddings=True) if texts else []

    for i, (fp, chunk_text, c0, c1, toks) in enumerate(all_chunks):
        dense_vec = dense_vecs[i].tolist()
        sparse_vec = sparse_from_tokens(toks, idf, sparse_dim=args.sparse_dim)
        pid = int(hashlib.md5(f"{fp}:{c0}:{c1}".encode()).hexdigest()[:15], 16)
        payload = {
            "audience": args.audience,
            "domain": args.domain,
            "channel": args.channel,
            "peer_id": args.peer_id,
            "thread_id": args.thread_id,
            "doc_type": args.doc_type,
            "source": str(fp),
            "created_at": int(fp.stat().st_ctime),
            "updated_at": int(fp.stat().st_mtime),
            "customer_id": args.customer_id,
            "lead_id": args.lead_id,
            "text": chunk_text,
            "locator": f"{fp}#char:{c0}-{c1}",
            "indexed_at": now,
        }
        batch.append(
            models.PointStruct(
                id=pid,
                vector={"dense": dense_vec, "sparse": sparse_vec},
                payload=payload,
            )
        )
        if len(batch) >= 128:
            q.upsert(collection_name=args.collection, points=batch)
            batch.clear()
    if batch:
        q.upsert(collection_name=args.collection, points=batch)

    ensure_payload_indexes(q, args.collection)
    print(f"RAG_INDEX_OK collection={args.collection} chunks={len(all_chunks)}")


if __name__ == "__main__":
    main()

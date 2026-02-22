#!/usr/bin/env python3
import argparse, hashlib, re
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer


def split_chunks(text, chunk_size=900, overlap=120):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    out, i = [], 0
    while i < len(text):
        out.append(text[i:i+chunk_size])
        i += max(1, chunk_size - overlap)
    return out


def read_text(path: Path):
    if path.suffix.lower() == '.txt':
        return path.read_text(errors='ignore')
    return ''


def iter_files(root: Path):
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in {'.txt'}:
            yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input-dir', required=True)
    ap.add_argument('--collection', default='rag_local')
    ap.add_argument('--qdrant-url', default='http://127.0.0.1:6333')
    ap.add_argument('--model', default='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    args = ap.parse_args()

    files = list(iter_files(Path(args.input_dir)))
    if not files:
        print('No .txt files found')
        return

    model = SentenceTransformer(args.model)
    dim = model.get_sentence_embedding_dimension()

    q = QdrantClient(url=args.qdrant_url, timeout=60)
    q.recreate_collection(args.collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))

    batch = []
    idx = 1
    total_chunks = 0
    for fp in files:
        text = read_text(fp)
        chunks = split_chunks(text)
        if not chunks:
            continue
        vecs = model.encode(chunks, normalize_embeddings=True)
        for c, v in zip(chunks, vecs):
            hid = int(hashlib.md5(f"{fp}:{idx}".encode()).hexdigest()[:12], 16)
            batch.append(PointStruct(id=hid, vector=v.tolist(), payload={"text": c, "source": str(fp)}))
            idx += 1
            total_chunks += 1
            if len(batch) >= 128:
                q.upsert(collection_name=args.collection, points=batch)
                batch.clear()
    if batch:
        q.upsert(collection_name=args.collection, points=batch)

    print(f'RAG_INDEX_OK files={len(files)} chunks={total_chunks} collection={args.collection}')


if __name__ == '__main__':
    main()

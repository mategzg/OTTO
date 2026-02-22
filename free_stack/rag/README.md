# RAG local optimizado (Qdrant)

## Qué hace
- Chunking con overlap
- Embeddings multilingües locales
- Indexado en Qdrant
- Búsqueda híbrida (dense + BM25) con rerank simple

## 1) Asegura Qdrant
```bash
bash free_stack/start_qdrant.sh
```

## 2) Prepara corpus
Guarda tus textos `.txt` en una carpeta, ejemplo:
`data/rag_corpus/*.txt`

## 3) Construir índice
```bash
python3 free_stack/rag/build_rag_index.py --input-dir data/rag_corpus --collection rag_local
```

## 4) Consultar
```bash
python3 free_stack/rag/query_rag.py --collection rag_local --query "¿Qué decidimos sobre precios de melamina?"
```

## Tip pro
Convierte primero audios/PDF/imagenes a texto con el stack ya instalado, y luego indexa esos `.txt` aquí.

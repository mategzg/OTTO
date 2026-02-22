# RAG local optimizado (Qdrant “oro”)

## Implementado
- Hybrid real en Qdrant:
  - vector `dense` (semántico)
  - vector `sparse` (keywords BM25-like hash tf-idf)
- Filtro estricto por payload antes de topK (anti-leaks)
- Payload indexes para performance
- Query pipeline con RRF + dedupe/diversidad + citas auditables
- Contrato de evidencia: sin evidencia => `NO_VERIFICADO + GAPS`

## 1) Asegura Qdrant
```bash
bash free_stack/start_qdrant.sh
```

## 2) Indexar con metadata de seguridad
```bash
python3 free_stack/rag/build_rag_index.py \
  --input-dir data/rag_corpus \
  --collection rag_local \
  --audience staff \
  --domain sg \
  --channel whatsapp \
  --peer-id 51999999999 \
  --thread-id none \
  --doc-type note
```

## 3) Consultar con filtros (obligatorio)
```bash
python3 free_stack/rag/query_rag.py \
  --collection rag_local \
  --query "SKU-MEL-123 precio" \
  --audience staff \
  --domain sg \
  --channel whatsapp \
  --peer_id 51999999999 \
  --top-n-candidates 120 \
  --top-k-final 10 \
  --max-per-doc 2
```

## 4) Certificación mínima
```bash
python3 free_stack/rag/validate_rag.py
```

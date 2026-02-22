# ChatGPT Reingest v2 — Reporte latest

Fecha (UTC): 2026-02-22T17:08:30Z  
Workspace: `/home/agente/otto-workspace`

## Fuente procesada
- Original: `vault/inbox_raw/sources/20260222T162442Z_065f800160`
- Movida a processed por router: `vault/inbox_raw/_processed/20260222T170659Z_cdf87af412/source/20260222T162442Z_065f800160`

---

## 1) Normalización segura por chunks/slices (sin OOM)
**Estado:** ✅ OK

Se ejecutó normalización streaming con script ad-hoc:
- Script: `scripts/chatgpt_reingest_v2.py`
- Estrategia: `jq -c '.[]' conversations.json` + parse line-by-line en Python (sin cargar ~297MB completos en RAM)
- Regla de ignore: `*:Zone.Identifier`

**Evidencia de ruido ignorado:**
- `Zone.Identifier` detectados en MANIFEST: **643**

**Outputs canónicos v2 generados:**
- `normalized/conversations.ndjson`
- `normalized/messages.ndjson`
- `normalized/attachments.ndjson`
- `normalized/slices_index.json`

**Conteos:**
- Conversaciones: **1887**
- Mensajes: **31499**
- Attachments: **1967**
- Slices: **459**

---

## 2) Dedupe por hash de conversaciones
**Estado:** ✅ OK

- Hash usado: `sha256` sobre JSON canónico de cada conversación
- Hashes únicos: **1887**
- Duplicadas saltadas: **0**

---

## 3) Triage + brain_ingest_router (plan/apply) + write_router
**Estado:** ✅ OK

### Triage
- Reporte: `docs/_inbox/corpus_triage_latest.json`
- Pending sources: **459**
- Pending files: **459**
- Pending bytes: **87,075,797**
- Slice units: **459**

### Write Router
- Reporte: `docs/_inbox/write_router_latest.json`
- Routing: `brain_knowledge=459`

### Brain Ingest Router
- Plan ID ejecutado: `PLAN-20260222T170655Z-b5332134`
- Plan: `docs/_inbox/corpus_assimilation_plan_latest.json`
- Apply: `docs/_inbox/corpus_assimilation_report_latest.json`

**Resultado apply:**
- Created: **100**
- Categoría: `brain_knowledge=100`
- Processed moves: **1**
- Errors: **0**

**Rutas creadas (resumen):**
- Cards: `brain/cards/external_ingest/card_*.md`
- Índices por source: `brain/domains/external_ingest/sources/*_index.md`

---

## 4) Actualización índice de memoria
**Estado:** ✅ OK

- Comando: `python3 scripts/memory_index_build.py --root .`
- Reporte: `docs/_inbox/memory_index_report_latest.json`
- Índice: `state/memory_index.json`

**Resultado:**
- records: **26**
- tokens: **1398**
- parse_errors: **0**

---

## 5) QA mínima (20 queries smoke)
**Estado:** ✅ OK

Se corrieron 20 queries sobre `memory_query.py`.
- Queries: **20**
- Hits (>0 resultados): **20**
- Hit-rate: **1.00**

---

## 6) Pendientes y siguientes pasos
### Pendientes
- Ninguno bloqueante.

### Siguientes pasos sugeridos
1. Si se busca cobertura total de slices en artifacts Brain en una sola tanda, ejecutar otro `--plan/--apply` con `--max-sources` mayor antes de nuevas ingestas.
2. Consolidar o retirar `scripts/chatgpt_reingest_v2.py` si se migra su lógica al pipeline oficial.

---

## Archivos finales solicitados
- `docs/_inbox/chatgpt_reingest_v2_latest.md` ✅
- `docs/_inbox/chatgpt_reingest_v2_latest.json` ✅

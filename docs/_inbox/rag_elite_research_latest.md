# RAG de élite para OTTO (2026): investigación v2 validada con Brave + fetch

Fecha: 2026-02-22  
Método: discovery con `web_search` (Brave) + lectura con `web_fetch` en fuentes primarias/semiprimarias.

---

## Resumen ejecutivo

Para OTTO, la estrategia ganadora 2026 no es “más contexto”, sino **más disciplina de retrieval + evaluación continua + aislamiento estricto**.

**Decisiones núcleo**:
1. **RAG híbrido por defecto** (dense + sparse + rerank) con filtros duros por canal/audiencia/tenant.
2. **Context engineering explícito**: chunking semántico, packing con diversidad (MMR), y contrato claim→cita.
3. **Eval como gate de deploy** (offline+online): groundedness, citation correctness, leakage rate, p95 latency/cost.
4. **Seguridad de RAG-first**: tratar todo documento recuperado como no confiable (prompt injection indirecta).
5. **Rollout por etapas** (shadow/canary) y rollback automático por degradación de métricas.

---

## 1) Arquitectura recomendada (SOTA operable)

### 1.1 Pipeline objetivo
- **Ingesta**: parsing estructural + dedupe + metadata obligatoria.
- **Indexación**: dense + BM25/sparse + fusión (RRF) + particiones de aislamiento.
- **Retrieval**: query understanding/rewrite (condicional), filtros duros, rerank cross-encoder.
- **Generación grounded**: respuesta solo con evidencia citada; abstención cuando no hay soporte.
- **Observabilidad**: trazas por etapa (query rewrite, docs candidatos, scores, citas, costo, latencia).

### 1.2 Por qué
- Azure y OpenAI convergen en patrón: **hybrid retrieval + semantic ranking + límites de tokens + seguridad granular**.
- Agentic retrieval (preview) muestra la dirección: **descomposición en subqueries + ejecución paralela + salida estructurada**.

**Referencias**:  
- https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview  
- https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview  
- https://developers.openai.com/api/docs/guides/retrieval

---

## 2) Retrieval avanzado: comparativa y decisiones por escenario

### 2.1 Estrategias

| Estrategia | Pros | Contras | Úsala cuando |
|---|---|---|---|
| Dense-only | buena semántica | falla en IDs/términos exactos | Q&A conceptual simple |
| Sparse/BM25-only | excelente exact match | pobre sinonimia/contexto | búsquedas tipo comando/ID |
| **Hybrid + RRF** | mejor recall global | más tuning | **default producción** |
| Hybrid + rerank | mejor precisión final | costo/latencia extra | respuestas críticas/policy |
| Multi-query | mejora cobertura en preguntas complejas | puede meter ruido + costo | consultas ambiguas/multi-intent |
| Hierarchical retrieval | balance recall/latencia | implementación más compleja | corpus grande heterogéneo |

### 2.2 Recomendaciones OTTO
- **Default**: hybrid + rerank topN (ej. 40→10).  
- **Activación condicional** de multi-query: solo si baja confianza inicial o query compuesta.  
- **Hard filters antes del rerank**: `channel_id`, `thread_id`, `audience`, `visibility`, `policy_tags`.

**Referencias**:  
- https://developers.openai.com/api/docs/guides/retrieval  
- https://www.anthropic.com/engineering/contextual-retrieval  
- https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview

---

## 3) Chunking y context packing (lo que más rompe o salva calidad)

### Hallazgos clave
- Mal chunking degrada retrieval aunque el índice/modelo sea bueno.
- Long context no elimina el problema: “lost in the middle” sigue vigente.
- Contextualización de chunks (Contextual Retrieval) mejora recall de forma significativa en casos reales.

### Política sugerida OTTO
- Chunking semántico-estructural primero; tamaño inicial **350-900 tokens**, overlap **10-20%**.
- Para políticas/procedimientos críticos: 200-500 tokens con citas más precisas.
- Context packing con:
  1) relevancia (score),
  2) diversidad (MMR),
  3) recency ponderada,
  4) dedupe fuerte por similitud.
- Regla anti-overread: el modelo no debe inferir hechos no citados.

**Referencias**:  
- https://weaviate.io/blog/chunking-strategies-for-rag  
- https://aclanthology.org/2024.tacl-1.9/  
- https://www.anthropic.com/engineering/contextual-retrieval

---

## 4) Evals y observabilidad (obligatorio, no opcional)

### 4.1 Offline eval
Dataset estratificado con:
- factual QA del repo,
- casos de abstención correcta,
- policy-sensitive,
- prompt injection indirecta,
- long-context retrieval.

Métricas mínimas:
- **Retrieval**: Recall@k, MRR, nDCG.
- **Generation**: groundedness/faithfulness, citation correctness, answer relevance.
- **Safety**: leakage rate, policy violation rate.
- **SLO**: p50/p95 latency, cost/query.

### 4.2 Online eval
- Muestreo de tráfico (5-20%).
- Monitorear unsupported-claim rate, user correction rate, abstention rate, drift.
- Feedback loop: fallos online -> dataset offline -> gate de release.

### 4.3 Herramientas/frameworks
- OpenAI Evals para programación de pruebas y regresión.
- LangSmith/Haystack para offline+online + trazas.

**Referencias**:  
- https://developers.openai.com/api/docs/guides/evals  
- https://docs.langchain.com/langsmith/evaluation  
- https://docs.haystack.deepset.ai/docs/evaluation

---

## 5) Seguridad y aislamiento

### Riesgo principal
RAG introduce **input no confiable** al contexto del modelo. OWASP 2025 confirma que RAG/fine-tuning **no** eliminan prompt injection.

### Controles recomendados OTTO
1. **Separar instrucciones vs datos** en toda la cadena.
2. Etiquetar contenido recuperado como untrusted; nunca ejecutar instrucciones embebidas.
3. Least privilege para tool access.
4. Human-in-the-loop para acciones de alto impacto.
5. Pruebas adversariales periódicas (direct/indirect injection, payload splitting, multimodal future-proof).
6. Aislamiento por `tenant/channel/thread` en retrieval y output.

**Referencias**:  
- https://genai.owasp.org/llmrisk/llm01-prompt-injection/  
- https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html

---

## 6) Costo/latencia: tradeoffs prácticos

- Hybrid + rerank mejora calidad pero sube latencia/costo → usar thresholds dinámicos y rerank condicional.
- Multi-query mejora recall pero puede inflar tokens → activar solo en queries complejas.
- Chunk pequeño mejora precisión de cita pero fragmenta contexto → compensar con retrieval jerárquico y packing.
- Prompt caching/document caching (si aplica por proveedor) puede recortar costo de forma fuerte en conocimiento recurrente.

**Referencias**:  
- https://developers.openai.com/api/docs/guides/retrieval  
- https://www.anthropic.com/engineering/contextual-retrieval

---

## 7) Rollout/canary y day-2 ops

### Estrategia de despliegue
- Shadow primero (medir sin impactar usuario).
- Canary por etapas (5% -> 25% -> 50% -> 100%) con verificaciones por fase.
- Rollback automático por umbrales de seguridad/calidad/SLO.

### Operación day-2
**Diario**: p95 latency, cost/query, groundedness, incidentes de seguridad.  
**Semanal**: retuning (top-k, thresholds), refresh dataset con fallos reales.  
**Mensual**: simulacro rollback de índice, benchmark embedding/reranker.

**Referencias**:  
- https://cloud.google.com/deploy/docs/deployment-strategies/canary  
- https://docs.langchain.com/langsmith/evaluation

---

## 8) Plan operativo OTTO

## Quick wins (1-2 semanas)
- [ ] Activar **hybrid retrieval + rerank** en ruta principal.
- [ ] Definir schema metadata obligatorio (`channel/thread/audience/visibility/policy_tags`).
- [ ] Forzar plantilla de salida con claim→cita y abstención explícita.
- [ ] Crear eval set inicial (100-300 casos) + gate básico en CI.
- [ ] Dashboard mínimo: groundedness, unsupported claims, p95 latency, cost/query.

## Medium (1-2 meses)
- [ ] Multi-query adaptativo por tipo de consulta/confianza.
- [ ] Retrieval jerárquico (doc->section->chunk).
- [ ] Caching por capas (query/retrieval/prompt-result).
- [ ] Canary formal + rollback automatizado + alertas de drift.
- [ ] Test suite de seguridad adversarial recurrente.

## Long-term (2+ meses)
- [ ] Policy engine declarativo para retrieval y output (ABAC/RBAC + contexto).
- [ ] Auto-tuning de pesos hybrid, top-k y umbrales por intent.
- [ ] Graph augmentation para entidades/relaciones críticas.
- [ ] Loop de active learning (incidentes reales -> eval set -> tuning/deploy).

---

## Decisiones recomendadas para OTTO (concretas)

1. **Default universal**: Hybrid + rerank + hard filters.  
2. **Contrato de respuesta**: ningún claim factual sin cita; sin evidencia -> abstenerse.  
3. **Seguridad por diseño**: documentos recuperados siempre no confiables.  
4. **Release governance**: eval gate y canary obligatorios en cambios de retrieval/chunking/prompt.  
5. **Operación continua**: observabilidad de extremo a extremo con trazas por etapa.

---

## Referencias URL por sección

- Arquitectura/retrieval:  
  - https://learn.microsoft.com/en-us/azure/search/retrieval-augmented-generation-overview  
  - https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview  
  - https://developers.openai.com/api/docs/guides/retrieval

- Chunking/context packing:  
  - https://weaviate.io/blog/chunking-strategies-for-rag  
  - https://aclanthology.org/2024.tacl-1.9/  
  - https://www.anthropic.com/engineering/contextual-retrieval

- Evals/observabilidad:  
  - https://developers.openai.com/api/docs/guides/evals  
  - https://docs.langchain.com/langsmith/evaluation  
  - https://docs.haystack.deepset.ai/docs/evaluation

- Seguridad/aislamiento:  
  - https://genai.owasp.org/llmrisk/llm01-prompt-injection/  
  - https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html

- Rollout/canary/day-2:  
  - https://cloud.google.com/deploy/docs/deployment-strategies/canary

- Surveys de apoyo (investigación):  
  - https://arxiv.org/abs/2410.12837  
  - https://arxiv.org/abs/2506.00054  
  - https://arxiv.org/abs/2504.14891

---

## (Opcional recomendado) institucionalización en brain

Propuesta de ramas canónicas:
- `brain/domains/openclaw_ops/16_RAG_ELITE_ARCHITECTURE.md`
- `brain/domains/openclaw_ops/17_RAG_EVAL_OBSERVABILITY.md`
- `brain/domains/openclaw_ops/18_RAG_SECURITY_ISOLATION.md`
- `brain/cards/openclaw_ops/card_rag_rollout_day2.md`

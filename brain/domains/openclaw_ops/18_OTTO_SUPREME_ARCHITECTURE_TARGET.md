# 18 — OTTO Supreme Architecture Target (Canon de evolución)

## Purpose
Definir el estado objetivo de OTTO para operar 100% NL-first con precisión frontier usando LLM + RAG + tooling + observabilidad, alineado al sistema actual del repo.

## Decision scope
Este documento guía diseño y priorización de mejoras en:
- routing por intención,
- skill/recipe lifecycle,
- retrieval quality,
- seguridad/ACL,
- estabilidad operativa (cooldown/loops),
- evaluación continua.

## North objective (adaptado al proyecto)
OTTO debe responder y ejecutar en lenguaje natural sin depender de comandos del owner, seleccionando internamente herramientas/skills/recipes con evidencia, citas y control de riesgo.

---

## Target requirements (MUST)

1. **NL-first end-to-end**
- Usuario escribe natural; OTTO decide si resolver con RAG, tools, o combinación.

2. **Evidence-first by default**
- Toda afirmación relevante debe estar soportada por fuente recuperada o evidencia de runtime.
- Si falta soporte: `GAP/NO_VERIFICADO` + siguiente acción verificable.

3. **RAG robusto**
- Pipeline: ingestión -> chunking -> embeddings/indexes -> retrieval híbrido -> rerank -> top-K con citas.
- Fuentes con trazabilidad: doc/path/section/offset/version/hash cuando aplique.

4. **ACL y seguridad de datos**
- Filtrado por permisos previo a contexto final.
- Zero-mix por sesión/canal/thread.

5. **Tooling seguro y auditado**
- Schemas, validación, idempotencia, timeouts, rate-limits, retries con backoff+jitter.

6. **Observabilidad obligatoria**
- Logs de retrieval, tool calls, latencia, costos y trazas por request.

7. **Evaluación continua**
- Golden questions + regresión de groundedness/faithfulness/retrieval quality.

8. **Skills/Recipes con criterio de creación**
- Repetición/impacto/riesgo/costo determinan creación.
- Tarea random/no recurrente: no crear skill.

9. **Delegación confiable**
- Subagente supervisor por fase -> coder -> handoff detectable -> reporte NL al owner.
- Sin handoff válido en trabajo efectivo: no cierre.

---

## Arquitectura mínima objetivo (compatible repo actual)

### A) Control plane
- Registry de skills/recipes/policies versionado en `state/*`.
- Contratos canónicos en `PROMPT_MANUAL.md` + `HEARTBEAT.md` + policy JSON.

### B) Data plane
- Source-of-truth: `vault/inbox_raw/*` + documentos del workspace.
- Curación canónica por destino:
  - profile -> `memory/profile/*`
  - vision -> `memory/vision/*`
  - business/pro -> `brain/domains/sg_acabados/*`
  - aprendizaje operativo OTTO -> `brain/domains/personal_ops/*`

### C) Retrieval plane
- Índices activos: memory + brain + repo_map.
- Query selectiva anti-overread + carga contextual por señales.

### D) Execution plane
- Router NL -> tool/skill/workflow/create-skill.
- Policy/risk engine -> permisos, approvals, circuit breakers.

---

## Skill/Recipe lifecycle target
1. Detectar tarea repetida o de alto impacto.
2. Draft de recipe declarativa (sin código nuevo) cuando sea posible.
3. Tests/checks + doc + límites de riesgo.
4. Enable con tracing.
5. Review/retire por uso y resultados.

Si recipe no alcanza, recién considerar skill de código con gating fuerte.

---

## Stability contract target

- No loops de cron/heartbeat.
- No death-spiral por cooldown.
- Circuit breaker global por provider:
  - cooldown detectado -> pausar jobs dependientes,
  - backlog modo degradado,
  - reintentos escalonados con jitter,
  - reanudación controlada.

---

## Grounded response contract
Toda respuesta crítica debe incluir:
- respuesta directa,
- evidencia/citas,
- confianza (alta/media/baja),
- gaps claros,
- acciones ejecutadas (si hubo tools).

---

## Phased roadmap (M1..M7)
- M1: RAG con citas + GAP correcto + ingest incremental confiable.
- M2: Hybrid retrieve + rerank + filtros metadata.
- M3: ACL/permisos en retrieval + auditoría.
- M4: Tool calling seguro con skills nucleares.
- M5: Recipe memory + autocreación gated.
- M6: Evaluación continua + dashboards.
- M7: Auto-skill (código) con CI/review/rollback (opcional, sólo si aporta).

---

## Done criteria of this target
- OTTO responde NL con evidencia de forma consistente.
- OTTO decide internamente herramienta/skill/recipe sin depender de comandos owner.
- Skill creation ocurre sólo cuando “vale la pena” por métricas.
- El sistema se mantiene estable bajo carga/cooldown, sin spam ni cierres falsos.

## Update trigger
Actualizar cuando cambie: arquitectura OpenClaw, política de skills/recipes, contrato de evidencias o metas estratégicas del sistema.

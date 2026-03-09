# Reingest v2 — Personal Insights (accionables, no ruido)

## Lo que sí es accionable
1. **NL-first como requisito duro**
   - Implicación: diseños y prompts deben evitar dependencia en comandos del owner.
2. **Un escritor principal (anti-colisión)**
   - Implicación: reforzar patrón "single-writer" para cambios de repo.
3. **Guardrails anti-destructivos explícitos**
   - Implicación: defaults conservadores (no vaciar/mover repo masivamente).
4. **Foco en capacidad acumulativa (cerebro/memoria)**
   - Implicación: priorizar mejoras de memoria estructurada y retrieval antes de features cosméticas.
5. **Sensibilidad a costo computacional**
   - Implicación: optimizar token/CPU en flujos recurrentes (heartbeat, ingest, indexado).

## No promover (ruido o ambigüedad)
- Preferencias puntuales de una herramienta/modelo en un momento específico, salvo que se repitan.
- Datos operativos sensibles (credenciales) no se trasladan a memoria estructurada.

## Estado
- Integrado en `memory/01_PROFILE_CURRENT.md` + NDJSON de preferencias/decisiones/timeline.

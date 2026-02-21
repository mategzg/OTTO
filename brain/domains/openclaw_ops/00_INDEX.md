# OpenClaw Ops Domain Index

## Purpose

Hub de ruteo para operacion diaria de OpenClaw/OTTO en el workspace canonico.

## Use when

- Necesitas ejecutar un run con gates y evidencia.
- Necesitas diagnosticar root drift, nested repos o quarantine.
- Necesitas aplicar hygiene o validar que indexers no lean tooling/raw.
- Necesitas decidir comando de hook `/repo` o `/home`.

## Avoid when

- La pregunta es de dominio negocio no-operativo.
- La tarea requiere runtime/UI fuera de scope de operaciones.

## Routing

- Pregunta: "como ejecuto un run completo" -> `brain/domains/openclaw_ops/02_RUN_PROTOCOL.md`
- Pregunta: "root pinning, ghost repos, quarantine" -> `brain/domains/openclaw_ops/03_REPO_REALITY.md`
- Pregunta: "hygiene del workspace/home" -> `brain/domains/openclaw_ops/04_WORKSPACE_HYGIENE.md`
- Pregunta: "que comando hook usar" -> `brain/domains/openclaw_ops/05_HOOKS_COMMANDS.md`
- Pregunta: "como redactar prompts/protocolos" -> `brain/domains/openclaw_ops/06_PROMPT_ENGINEERING_PATTERNS.md`
- Pregunta: "a quien delego (Codex/Claude/Cowork)" -> `brain/domains/openclaw_ops/07_DELEGATION_POLICY.md`
- Pregunta: "como auditar salvage/quarantine y recuperar docs por lotes" -> `brain/domains/openclaw_ops/08_LEGACY_RECOVERY.md`
- Pregunta: "como orquestar misiones complejas (sizing/roles/learning)" -> `brain/domains/openclaw_ops/14_MISSION_ORCHESTRATION.md`
- Pregunta: "cuando activar mision automaticamente y cuando escalar a owner" -> `brain/domains/openclaw_ops/15_MISSION_ACTIVATION.md`
- Pregunta: "como usar docs.openclaw.ai como biblia operativa" -> `brain/domains/openclaw_ops/17_OPENCLAW_DOCS_BIBLE_PROTOCOL.md`
- Pregunta: "cuál es la arquitectura objetivo suprema de OTTO (LLM+RAG+skills+estabilidad)" -> `brain/domains/openclaw_ops/18_OTTO_SUPREME_ARCHITECTURE_TARGET.md`

## Maintenance

- Actualizar cuando cambien scripts en `scripts/` o autoridad en `openclaw/CONTEXT_MAP.md`.
- Priorizar referencias a fuente canonica, no duplicar texto largo.

## Links

- `openclaw/CONTEXT_MAP.md`
- `brain/domains/openclaw_ops/01_ROUTER.md`
- `brain/cards/openclaw_ops/card_context_authority.md`
- `brain/cards/openclaw_ops/card_delegation_matrix.md`
- `repo_map/90_LEGACY_RECOVERY.md`
- `repo_map/95_MISSION_ORCHESTRATION.md`
- `repo_map/96_MISSION_ACTIVATION.md`

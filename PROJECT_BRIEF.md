# PROJECT_BRIEF

## Scope y Proposito

Repositorio canonico de OTTO/OpenClaw-MemoryOS en `/home/agente/otto-workspace`.  
Objetivo operativo: ejecutar runtime NL-first multi-canal con zero-mix de sesiones, ingest por bloques, MemoryOS estructurado y evidencia determinista.

## Invariantes Operativas

- Zero-mix por session_id (chat/canal/thread): `scripts/session_memory_manager.py`.
- Anti-overread: routing por indices/nodos/cards; no lectura masiva de crudo.
- No indexar crudo: `scripts/brain_index_build.py`, politicas en `state/workspace_hygiene_policy.json`.
- No delete destructivo; quarantine/salvage para casos de riesgo.
- Instruction surface reservada (`AGENTS*`, `CLAUDE*`) con doctor dedicado: `scripts/instruction_surface_doctor.py`.

## Arquitectura Real (Componentes + Source Files)

- Runtime ingress por canal: `scripts/channel_ingress_adapter.py`, `scripts/nl_intent_classifier.py`, `hooks/otto-runtime-bridge/handler.js`.
- Session memory + compact/distill: `scripts/session_memory_manager.py`.
- Ingest pipeline: `scripts/dropbox_intake.py` -> `scripts/chatgpt_export_normalize.py` -> `scripts/corpus_triage.py` -> `scripts/brain_ingest_router.py`.
- Write Router: `scripts/write_router.py` (categorias detectadas: brain_knowledge, ignore, inbox_only, memory_human, ops_system, templates).
- MemoryOS: `scripts/memory_capture.py`, `scripts/memory_compact.py`, `scripts/memory_index_build.py`, `scripts/memory_query.py` (tipos: decision, preference, principle, profile_fact, project, timeline).
- Outbox/approvals/SG: `scripts/outbox_queue.py`, `scripts/outbox_delivery.py`, `scripts/openclaw_cli.py`, `scripts/approval_manager.py`, `scripts/sg_promotion.py`, `scripts/sg_channel_policy.py`.
- Orquestacion: `scripts/heartbeat_worker.py`, `scripts/autonomy_tick.py`.
- Hardening prod: `scripts/hook_backlog.py`, `scripts/prod_doctor.py`, `scripts/safety_switch.py`.

## Workflows Canonicos (Auto)

1. Mensaje entrante -> ingress adapter -> append session -> intent routing -> posibles acciones (drop/memory/approval).
2. Heartbeat (30 min) ejecuta intake/normalize/runtime/outbox/autonomia.
3. Outbox queue autoridad: `docs/_inbox/outbox_queue.ndjson`; entrega por `outbox_delivery` via OpenClaw CLI.
4. Memory inbox (`docs/_inbox/memory_inbox.ndjson`) -> compact/index -> NDJSON canonicos en `memory/`.

## Operacion por Canal y Guardrails

- Tiers definidos en `state/channel_runtime_policy.json`: discord_domain, discord_thread, telegram_owner, whatsapp_client, whatsapp_worker.
- Telegram owner: aprobaciones/notificaciones.
- Discord: domain inference por `channel_name`, thread episodico.
- WhatsApp: dominio SG; no memoria personal.
- SG promotions: low=auto, medium=approval_required, high=approval_required.
- Worker auth mode: `password_plus_owner_approval`.

## Contribucion Segura (Do/Don't + Gates)

- Tocar preferentemente: `scripts/`, `state/`, `brain/`, `openclaw/`, `tests/`.
- No tocar como fuente operativa: `vault/_quarantine/**`, `vault/_salvage/**`, `vault/inbox_raw/**`.
- Respetar reserved instruction surface: AGENTS.md, AGENTS.override.md, CLAUDE.md, CLAUDE.local.md.
- Gates minimos:
  - `pytest -q`
  - `python3 scripts/heartbeat_worker.py --once --root . --force`
  - `python3 scripts/repo_reality_doctor.py --scan --json`
  - `python3 scripts/workspace_hygiene_doctor.py --scan`
  - `python3 scripts/instruction_surface_doctor.py --scan --root .`
  - `python3 scripts/brain_index_build.py`

## Operational Safety & Recovery

- Hook bridge fail-open: backlog en `state/hook_backlog/events.ndjson` + replay por heartbeat.
- Safety switch global: `state/safety_switch.json` detiene automatizaciones cuando hay degradacion.
- Prod doctor offline-first: `scripts/prod_doctor.py` reporta compatibilidad real y gaps verificables.
- Procedimiento de recovery: `repo_map/80_PROD_SAFETY.md`.
- Legacy recovery (coldstore): `scripts/capability_inventory.py` -> `scripts/legacy_coldstore_audit.py` -> `scripts/legacy_gap_detector.py` -> `scripts/legacy_capability_inventory.py` -> `scripts/legacy_recovery_worker.py`.
- Policy de recovery: `state/legacy_recovery_policy.json` (enabled=`False`, interval=720m, scan_interval=12h, allow_types=doc_value,brain_node).

## GAPS / NO VERIFICADO

- Ninguno detectado en esta corrida.

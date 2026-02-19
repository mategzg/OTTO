# CONTEXT_MAP

Autoridad operativa unica de contexto para OpenClaw MemoryOS.

## Inyeccion de contexto por actor

- Main agent: recibe el Project Context completo cuando existe.
- Sub-agents: normalmente reciben `AGENTS.md` y `TOOLS.md`.
- Wrappers de entrada:
  - OTTO: `SOUL.md`
  - Codex: `AGENTS.md`
  - Claude Code: `CLAUDE.md`

## Orden de lectura recomendado

### OTTO

`SOUL.md` -> `INDEX.md` -> `brain/00_INDEX.md` -> `brain/domains/openclaw_ops/00_INDEX.md` -> `openclaw/00_INDEX.md` -> `openclaw/CONTEXT_MAP.md`

### Codex

`AGENTS.md` -> `CEO.md` -> `INDEX.md` -> `brain/00_INDEX.md` -> `brain/domains/openclaw_ops/00_INDEX.md` -> `openclaw/CONTEXT_MAP.md`

### Claude

`CLAUDE.md` -> `CEO.md` -> `INDEX.md` -> `brain/00_INDEX.md` -> `brain/domains/openclaw_ops/00_INDEX.md` -> `openclaw/CONTEXT_MAP.md`

## Autoridad por capas

1. `CEO.md` manda sobre canon y reglas de autoridad.
2. `openclaw/CONTEXT_MAP.md` manda sobre navegacion e inyeccion de contexto.
3. `INDEX.md` es hub transversal humano.
4. `brain/00_INDEX.md` es hub del Brain Graph.
5. `AGENTS.md`, `CLAUDE.md`, `SOUL.md` son entrypoints/wrappers.
6. `TOOLS.md`, `USER.md`, `IDENTITY.md`, `HEARTBEAT.md` contienen contexto auxiliar operativo.

## Delegacion de agente

- Default: Codex.
- Claude Code cuando la tarea involucra `.claude/*`, reglas/imports o plugins de Claude Code.
- Claude Cowork permitido junto a Codex.
- Canon de delegacion: `brain/domains/openclaw_ops/07_DELEGATION_POLICY.md`.

## Raiz canonica del repo

- La raiz canonica se determina con `scripts/repo_root.py`.
- Autoridad primaria: marker pinneado `.openclaw/CANONICAL_ROOT.json`.
- Root canonico actual (SEQ 006): `/home/agente/otto-workspace`.
- Regla dura: la raiz canonica no puede contener componentes pathlike (`:` o `\`).
- Si no hay marker limpio, se propone root limpio por git/markers y se exige re-pin.
- Scripts criticos deben usar `get_canonical_root()` para evitar drift.
- Copias anidadas, salvage y quarantine (`vault/_salvage/`, `vault/_quarantine/`) quedan fuera de scans normales.

## Comandos Telegram de raiz y quarantine

- `/repo roots` lista candidatos de raiz con `id` estable.
- `/repo setroot <id>` pinnea la raiz oficial en `.openclaw/CANONICAL_ROOT.json`.
- `/repo doctor` genera reporte de nested copies y estado.
- `/repo salvage` construye staging de rescue y manifiestos sin overwrite.
- `/repo apply-salvage` promueve solo archivos safe/no-conflict.
- `/repo keep <candidate_id>` marca copia como intencional (allowlist).
- `/repo quarantine <candidate_id>` aprueba + cuarentena ese candidato (incluye nested con `.git`).
- `/repo fix` ejecuta salvage -> apply-salvage -> quarantine defaults (pathlike + backups + nested).

## Donde registrar cosas nuevas

- Evidencia de run y decisiones: `docs/_inbox/`
- Salidas deterministas de scripts: `logs/` y/o `state/` segun convencion vigente
- Trazabilidad del run: `ops/RUN_LEDGER.ndjson`

## Runtime Ingress (NL-first, sin comandos de usuario)

- Punto de ingreso canónico de mensajes entrantes: `scripts/channel_ingress_adapter.py`.
- Activación real en OpenClaw (workspace hook): `hooks/otto-runtime-bridge/handler.js`.
- El hook escucha `message:received` y `message:sent`, y aplica fail-open:
  1. append rápido a `state/hook_backlog/events.ndjson` + payload en `state/hook_backlog/payloads/`
  2. fast-path opcional a `channel_ingress_adapter` (timeout corto, no bloqueante)
  3. replay por bloques desde `scripts/heartbeat_worker.py` via `scripts/hook_backlog.py`
- Contrato de entrada soportado por el adapter:
  - formato interno (`channel`, `peer_id`, `thread_id?`, `message_id`, `text`, `attachments`, `auth`),
  - formato OpenClaw hook nativo (`type=message`, `action=received|sent`, `context.channelId`, `context.conversationId`, `context.metadata.threadId`, `context.content`).
- Normalización clave:
  - `channel <- context.channelId`
  - `peer_id <- context.conversationId` (fallback sender/to)
  - `thread_id <- context.metadata.threadId`
  - `text <- context.content`
- Flujo por evento:
  1. `session_memory_manager.append_event` (session-first, zero-mix).
  2. `nl_intent_classifier.classify_intent` (intenciones y señales).
  3. `chat_to_inbox_drop` para corpus/adjuntos (cuando aplica).
  4. `approval_manager` para aprobaciones NL owner (sin IDs) de SG promotions y worker pairing.
- WhatsApp queda restringido a SG: no promueve memoria personal.

## Prod Safety Runtime

- Backlog policy: `state/hook_backlog_policy.json`
- Safety switch global: `state/safety_switch.json` + `scripts/safety_switch.py`
- Prod doctor offline-first: `scripts/prod_doctor.py`
- Legacy coldstore audit/recovery v2: `scripts/capability_inventory.py` -> `scripts/legacy_coldstore_audit.py` -> `scripts/legacy_gap_detector.py` -> `scripts/legacy_capability_inventory.py` -> `scripts/legacy_recovery_worker.py`
- Policy de recovery: `state/legacy_recovery_policy.json` (`enabled=false` por defecto, `allow_types` y `scan_interval_hours` para control de costo)
- Reportes deterministas:
  - `docs/_inbox/hook_backlog_report_latest.json`
  - `docs/_inbox/prod_doctor_latest.json`
  - `docs/_inbox/legacy_coldstore_audit_latest.json`
  - `docs/_inbox/legacy_gap_report_latest.json`
  - `docs/_inbox/legacy_recovery_latest.json`

## Discord Domain Inference

- OTTO no crea ni administra estructura en Discord; solo interpreta lo que ya existe.
- Para eventos Discord, el runtime infiere `domain_slug` desde `channel_name`.
- Persistencia canonica: `state/discord_domains.json` (clave por `channel_id`).
- Si falta `channel_name`, se usa `domain_slug=unknown` sin romper pipeline.
- Para threads: la sesion sigue siendo episodica por `thread_id`, pero el dominio semantico se hereda del canal.
- El `recommended_domain` inferido se propaga a `EVENT_META` de drops y luego a triage/ingest.

## Aprobaciones y Notificaciones (Telegram-only)

- Todas las aprobaciones (SG medium/high, worker pairing) se notifican solo al owner por Telegram.
- Autoridad de mensajeria saliente: `docs/_inbox/outbox_queue.ndjson` (append-only).
- Entrega real: `scripts/outbox_delivery.py` usando `openclaw message send` cuando el CLI esta disponible.
- Si no se puede entregar (sin target o CLI faltante), el item queda en queue y snapshot en `docs/_inbox/outbox_latest.md`.
- Discord y WhatsApp nunca son canales de aprobacion; solo originan solicitudes que se encolan.
- Respuestas del owner se interpretan en lenguaje natural desde Telegram, sin exigir IDs.

## Pipeline de delivery real

1. Productor (`approval_manager`, alerts runtime) encola en `docs/_inbox/outbox_queue.ndjson`.
2. `scripts/heartbeat_worker.py` ejecuta `scripts/outbox_delivery.py --deliver` antes de autonomia.
3. `scripts/outbox_delivery.py` archiva entregados en `docs/_inbox/outbox_queue/_delivered/<ts>_<batch>.ndjson` + `MANIFEST`.
4. `outbox_latest.md` se regenera como snapshot legible, pero no es autoridad.

## Guardrails de contexto

- No inventar rutas, contratos ni policies inexistentes.
- No borrar ni hacer reorg masivo para corregir drift.
- Resolver conflictos de autoridad con redirects/banners, no con duplicacion de canon.

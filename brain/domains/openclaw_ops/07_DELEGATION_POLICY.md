# Delegation Policy

## Purpose

Definir a que agente delegar cada tipo de trabajo manteniendo autoridad unica y evidencia.

## Use when

- Debes decidir entre Codex, Claude Code o Claude Cowork.
- El run involucra `.claude/*`, rules/imports o plugins de Claude Code.

## Avoid when

- Se intenta mezclar canones paralelos en AGENTS/CLAUDE anidados.
- Se delega sin justificar evidencia y razon tecnica.

## Routing

- Default: **Codex** para desarrollo general y operaciones del repo.
- **Claude Code** cuando involucra plugins de Claude Code, `.claude/CLAUDE.md`, `.claude/rules/**`, imports `@...` o comandos de memoria asociados a ese stack.
- **Claude Cowork** permitido en paralelo con Codex para contraste o doble validacion.
- Fallback: si Codex falla por reglas/imports del stack Claude, reintentar con Claude Code.

## Criticality Matrix (autonomia vs control)

- **P0 - Critico / alta precision / alto riesgo / primera vez**
  - No usar coder autonomo end-to-end.
  - Ejecutar en modo supervisado por etapas (plan -> implementacion parcial -> validacion) con checkpoints humanos.
  - Requiere evidencia dura por fase (diff, tests, riesgos, rollback) antes de cerrar.
- **P1 - Importante / clave de calidad**
  - Sin coder autonomo.
  - Resolver directo (manual/asistido) con control de contexto completo y checkpoints de precision.
- **P2 - Repetitivo, bajo riesgo, receta conocida**
  - Delegacion directa a coder permitida para ahorrar cuota/contexto.
  - No requiere vigilancia en vivo: basta handoff verificable al cierre (archivos, pruebas, estado final).

## Delegation Record

Cada run delegado debe registrar:

- `delegate_to`
- `reason`
- `evidence_paths`

## Runtime automation note

- Aprobaciones y notificaciones operativas son automaticas (NL-first) y se enrutan por `docs/_inbox/outbox_queue.ndjson`.
- El usuario no necesita comandos para aprobar; owner responde en Telegram y `approval_manager` resuelve sin IDs.

## Maintenance

- Mantener wrappers root (`AGENTS.md`, `CLAUDE.md`) delgados y apuntando a este canon.
- No crear `AGENTS*`/`CLAUDE*` fuera de allowlist.

## Links

- `brain/cards/openclaw_ops/card_delegation_matrix.md`
- `.claude/CLAUDE.md`
- `state/instruction_surface_policy.json`

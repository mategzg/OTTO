# REPO_MAP

Portal de navegacion minima para OTTO/subagentes.

## Zonas del Repo

- `brain/`: nodos/router/cards de conocimiento.
- `memory/`: memoria canonica estructurada.
- `scripts/`: runtime, ingest, memory, approvals, doctors.
- `state/`: politicas y estado persistente.
- `openclaw/`: mapa de contexto y compatibilidad OpenClaw.
- `hooks/`: bridge/event wiring.
- `docs/_inbox/`: reportes latest deterministas.
- `logs/`: logs latest deterministas.
- `vault/`: crudo/pending/quarantine (no indexar como conocimiento).
- `tests/`: cobertura de flujos criticos y gates.

## Si Necesitas X -> Lee A -> B -> C

- Ejecutar runtime diario: `repo_map/00_INDEX.md` -> `repo_map/10_RUNTIME_INGRESS.md` -> `scripts/heartbeat_worker.py`.
- Entender ingest por bloques: `repo_map/20_INGEST_PIPELINE.md` -> `scripts/dropbox_intake.py` -> `scripts/brain_ingest_router.py`.
- Consultar MemoryOS: `repo_map/30_MEMORYOS.md` -> `scripts/memory_query.py` -> `memory/00_INDEX.md`.
- Resolver approvals/outbox: `repo_map/40_OUTBOX_APPROVALS.md` -> `scripts/approval_manager.py` -> `scripts/outbox_delivery.py`.
- Revisar politicas/estado: `repo_map/60_POLICIES_STATE.md` -> `state/*.json`.
- Validar calidad antes de cerrar: `repo_map/70_TESTS_GATES.md` -> `tests/`.
- Hardening/recovery productivo: `repo_map/80_PROD_SAFETY.md` -> `scripts/hook_backlog.py` -> `scripts/safety_switch.py`.
- Auditar coldstore y recuperar por lotes: `repo_map/90_LEGACY_RECOVERY.md` -> `scripts/legacy_gap_detector.py` -> `scripts/legacy_capability_inventory.py` -> `scripts/legacy_recovery_worker.py`.

## Router

- `repo_map/00_INDEX.md`
- `openclaw/CONTEXT_MAP.md`

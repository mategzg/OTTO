# Legacy Scripts — Learnings Extraídos

> Fuente: Scripts del workspace anterior (Windows, SG Acabados/AGENTE OTTO)
> Fecha de extracción: 2026-02-19
> Estado: Los scripts NO se copiaron al workspace activo (excepto odoo_bulk_import.py y coder_cli.py). Este card captura los patrones y decisiones útiles.

## 1. autonomy_tick.py — Patrón de Autonomía Periódica

**Qué hacía:** Corría el repo_reality_doctor periódicamente y alertaba por Telegram si detectaba drift.

**Patrones valiosos:**
- **Intervalo + dedup:** No solo tiene `interval_hours` para no correr seguido, sino `dedupe_hours` para no re-alertar el mismo problema. Doble protección contra spam.
- **Fingerprint de estado:** Genera un SHA256 del estado pendiente (candidatos + root drift). Solo alerta si el fingerprint cambió O si pasó el dedupe interval. Inteligente.
- **State file separado:** `state/autonomy_repo_doctor_state.json` con `last_run_utc`, `last_fingerprint`, `last_alert_utc`. Patrón reutilizable para cualquier job periódico.
- **Log siempre:** Escribe log incluso cuando hace skip por intervalo. Buen patrón de auditabilidad.

**Aplicación actual:** El heartbeat_worker.py ya absorbe esto, pero el patrón de fingerprint+dedup es más sofisticado que lo que tenemos. Considerar adoptar para alertas futuras.

## 2. repo_reality_doctor.py — Sistema de Higiene de Repo

**Qué hacía:** Detectaba "ghost roots" (copias duplicadas del workspace), las salvaba (archivos únicos) y cuarentenaba las copias.

**Patrones valiosos:**
- **Clasificación de candidatos:** `pathlike_folder`, `old_backup_root`, `nested_repo_git`, `nested_repo_copy_high_score`. Taxonomía clara.
- **Score por markers:** Busca CEO.md, INDEX.md, openclaw/, scripts/, brain/, AGENTS.md, SOUL.md. Score ≥5 = alta confianza de que es una copia del workspace.
- **Salvage antes de quarantine:** SIEMPRE copia archivos únicos/valiosos antes de mover. `trash > rm` aplicado a nivel sistema.
- **Conflict detection:** Si un archivo existe en el destino con hash diferente, lo marca como conflicto y NO lo sobreescribe. Seguro.
- **Guardrail pathlike (v2):** La versión mejorada agrega un guardrail que NUNCA recrea paths con componentes tipo `C:\Users\...` en el root canónico. Lección aprendida de la migración Windows→Linux.
- **Allowlist + State:** Permite marcar candidatos como "kept" (no tocar) o "approved" (cuarentenar). Workflow de aprobación.

**Lección clave:** El problema de paths Windows (`C:\Users\sgaca\SG Acabados\...`) creando directorios literales en Linux fue un bug real. El guardrail pathlike es esencial.

## 3. test_openclaw_hook_repo_commands.py — Tests del Sistema

**Patrones:**
- Tests crean marcadores completos (CEO.md, INDEX.md, openclaw/, etc.) para simular workspace.
- Tests de `/repo roots`, `/repo setroot`, `/repo salvage`, `/repo fix` — comandos que el sistema anterior exponía.
- El workflow era: roots → setroot → salvage → apply-salvage → fix.
- `/repo fix` requiere pinned root primero (safety check).

## 4. Decisiones de Diseño Importantes

1. **Nunca borrar, siempre mover:** Todo va a `vault/_quarantine/` con buckets por tipo.
2. **README en cada quarantine:** Cada item cuarentenado tiene un README.md con metadata.
3. **Determinismo:** `_candidate_id` es SHA1 del path absoluto, truncado a 10 chars. Mismo path = mismo ID siempre.
4. **Scan depth configurable:** Default 6 niveles. Suficiente para atrapar copias anidadas.
5. **Extensiones de valor:** `.md, .txt, .json, .py, .js, .sh, .sql, .csv` — lo que vale la pena salvar.
6. **Dirs canónicos:** `docs, openclaw, scripts, tests, ops, brain, plugins, templates` — la estructura esperada.

## 5. Aplicación al Workspace Actual

- El heartbeat_worker.py + legacy_recovery ya implementa una versión simplificada de esto.
- Los patrones de fingerprint+dedup deberían adoptarse para alertas.
- El guardrail de pathlike paths ya está parcialmente implementado en el sistema de ingestión.
- Los scripts originales dependían de `scripts/repo_root.py` y `scripts/openclaw_hook.py` que no están en el workspace actual.

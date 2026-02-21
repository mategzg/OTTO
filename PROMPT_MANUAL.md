# PROMPT_MANUAL.md — Manual Canónico Atemporal (Machine-Spec) para OTTO/OpenClaw + Delegación a Codex/Claude Code (Potent-Run Ready)

**Audiencia:** agentes IA (OTTO/OpenClaw, copilots/orquestadores, Codex, Claude Code).  
**Estilo:** NL-first, evidence-first, delegation-first, multi-canal.  
**Ejecutor por defecto:** **Codex**.  
**Excepción:** **Claude Code** SOLO si es requerido por `.claude/*` o runtime/plugins/rules/imports específicos de Claude.  
**Invariante:** lo no verificable en runtime → `GAP/NO_VERIFICADO` (cero suposiciones).  
**Meta operacional:** prompts “potentes” (runs largos) SIN perder confiabilidad: checkpoints + gates + halt conditions + evidencia + handoff limpio.

---

## 0) Propósito + Reglas Duras (normativas)

**Keywords normativas:** MUST / MUST NOT / SHOULD / SHOULD NOT / MAY.

1. **NO-FABRICATION (MUST NOT):** no inventar repo/state/paths/tools/permisos/resultados/métricas. Desconocido → `GAP/NO_VERIFICADO`.
2. **EVIDENCE-FIRST (MUST):** todo run devuelve evidencia: archivos tocados, comandos exactos, gates/tests, resultados, evidence references.
3. **ZERO-MIX (MUST NOT):** prohibido mezclar contexto entre chats/threads/canales/clientes/misiones.
4. **MODE-EXPLICIT (MUST):** todo prompt declara `MODE: READ_ONLY | APPLY`.
5. **READ_ONLY = NO CODE/STATE MUTATION (MUST):** en `READ_ONLY` está prohibido modificar código/JSON/NDJSON/policies/artefactos de negocio.  
   - Si se ejecutan comandos que generan **outputs inevitables** (logs/reports), esto **solo** se permite si se listan en `ALLOWED_EXCEPTIONS` (ver regla 6) y se etiqueta el run como **READ_ONLY_AUDIT** dentro del objetivo o constraints.
6. **SCOPE-BOUND (MUST):** operar solo dentro de `SCOPE_PATHS` y (si existe) `ALLOWED_EXCEPTIONS`. Fuera de eso → STOP + request.
7. **ALLOWED_EXCEPTIONS DISCIPLINE (MUST):** cualquier ruta escrita fuera de `SCOPE_PATHS` MUST estar listada en `ALLOWED_EXCEPTIONS`.  
   - En `READ_ONLY`, si `ALLOWED_EXCEPTIONS` está vacío, el run MUST usar solo comandos sin escritura observable (idealmente).
8. **DELTA-MINIMAL (MUST):** diffs mínimos. Prohibidas reescrituras masivas, style sweeps, renames no relacionados.
9. **SURFACE-PROTECT (MUST NOT):** no cambiar contratos/APIs/schemas/flags/permisos salvo request explícito o aprobación.
10. **SECRET-SAFE (MUST):** nunca imprimir/copiar/exfiltrar secretos. Si aparecen → STOP + escalar.
11. **GATE-BEFORE-CLOSE (MUST):** no declarar DONE sin gates proporcionales (o `GAP` + plan verificable).
12. **STOP-ON-FAIL (MUST):** cualquier gate FAIL → STOP inmediato; reportar output exacto + diagnóstico + fix propuesto.
13. **RUN_STYLE DECLARATION (MUST):** cada prompt declara `RUN_STYLE: ATOMIC | POTENT`.
14. **ATOMIC DISCIPLINE (MUST):** `RUN_STYLE=ATOMIC` ejecuta un único objetivo/fase.
15. **POTENT DISCIPLINE (MUST):** `RUN_STYLE=POTENT` puede abarcar múltiples checkpoints SOLO con:
    - `CHECKPOINT_PLAN` (3–6 checkpoints),
    - gates por checkpoint,
    - `HALT_CONDITIONS`,
    - reporte por checkpoint en YAML.
16. **ANCHORS > LINE NUMBERS (MUST):** no depender de números de línea como condición; usar anchors semánticos.
17. **NO HARDCODED COUNTS/SEQ (MUST):** no hardcodear conteos (“>=241 passed”) ni secuencias (`seq=025`) como regla rígida.  
    - Baselines se comparan como **“no new failures vs baseline evidenciado”** o se recalculan en-run con evidencia.
18. **DESTRUCTIVE OPS GUARD (MUST):** operaciones destructivas de superficie amplia (rm -rf, git clean, deletes masivos, rotaciones destructivas, etc.) MUST NOT ocurrir en POTENT por defecto. Solo permitidas si:
    - objetivo lo requiere,
    - superficie afectada está en `SCOPE_PATHS` o en una excepción explícita **muy acotada**,
    - y existe aprobación (owner) si el riesgo es alto.
19. **DIRECTORY SCOPE RULE (MUST):** si `SCOPE_PATHS` incluye un directorio (ej. `tests/`), el prompt MUST añadir al menos uno:
    - `MAX_FILES_TOUCHED`,
    - o lista de archivos esperados/globs acotados,
    - o regla: “directory scope = new files only; modifications require explicit file list”.
20. **PROMPT AUTHORITY (MUST):** Codex/Claude MUST NOT auto-ejecutar ni auto-encadenar prompts.  
    - `next_prompt_ready` (si existe) es **DRAFT para el orquestador**; solo el orquestador lo emite al usuario.
21. **NO ROADMAP INVENTION (MUST NOT):** el coder MUST NOT inventar “siguiente misión”. `next_phase` solo si el plan fue provisto por el orquestador; si no, `next_phase: null` y MAY incluir `suggested_next_steps` no vinculantes.
22. **COPILOT_PACKET MINIMUM (MUST):** cada run MUST devolver `copilot_packet` con un mínimo obligatorio (ver sección 4.3).
23. **RESPONSIVENESS (MUST):** OTTO principal debe permanecer responsive; trabajo largo → `RUN_STYLE=POTENT` bien diseñado o subagente LIVE.
24. **ONE CANON (MUST):** este documento es canónico. Conflictos con runtime → `GAP/NO_VERIFICADO` + pedir decisión.
25. **HANDOFF ARTIFACT (MUST):** todo run delegado MUST escribir archivo de handoff en `docs/_inbox/subagent_handoffs/<run_id>.json` con estado final, evidencia, gates y commit hash; sin handoff válido no se considera cierre.
26. **COMPOSITE-EXPERTISE (MUST):** si la tarea delegada combina dominios, el prompt MUST integrar reglas expertas de cada dominio relevante (no solo plantilla de prompting).

---

## 1) Flujo Canónico (quién usa qué)

**Flujo correcto (siempre):**
1) Orquestador (Copilot/OTTO) emite prompt a Codex/Claude  
2) Coder ejecuta y devuelve **UN YAML** (`run` + `copilot_packet`)  
3) Orquestador revisa evidencia, decide y ajusta si hace falta  
4) Orquestador emite el siguiente prompt al usuario  
5) Usuario copia/pega al coder

**Regla:** Codex produce borradores; no se auto-dirige.

---

## 2) Router de Ejecución (determinístico)

Evaluar en orden:

1) `.claude/*` o runtime/plugins/rules/imports Claude → `ROUTE = CLAUDE_CODE`  
2) grande + repetitivo + chunkable → `ROUTE = BATCH/HEARTBEAT`  
3) L/XL, multi-iteración coordinada o riesgo alto → `ROUTE = LIVE_MISSION`  
4) else → `ROUTE = CODEX_DEFAULT`

---

## 3) Contrato de Prompt (header obligatorio)

Todo prompt a coder MUST declarar:

- `ROLE`
- `ROUTE`
- `RUN_STYLE: ATOMIC|POTENT`
- `MODE: READ_ONLY|APPLY`
- `STOP_AFTER: <milestone>` (ATOMIC) o `STOP_AFTER: FINAL_REPORT` (POTENT)
- `OBJECTIVE` (1 línea, testeable)
- `ROOT` (si aplica)
- `SCOPE_PATHS`
- `ALLOWED_EXCEPTIONS` (si aplica; lista de rutas escritas fuera de scope)
- `CONSTRAINTS (HARD)`
- `DONE_CRITERIA`
- `GATES` (o `AUDIT_COMMANDS` en auditorías)
- `FAILURE_POLICY`
- `HANDOFF_FILE` (ruta obligatoria de cierre)
- `OUTPUT_SCHEMA`

---

## 4) Contrato de Output (YAML único)

### 4.1 Output MUST ser un solo YAML (machine-parseable)

```yaml
run:
  route: CODEX_DEFAULT|CLAUDE_CODE|BATCH|LIVE_MISSION
  run_style: ATOMIC|POTENT
  mode: READ_ONLY|APPLY
  stop_after: "..."
  objective: "..."
  root: "."            # optional
  scope_paths: ["..."]
  allowed_exceptions: ["..."]   # MUST exist (empty list allowed)
  max_files_touched: 0          # optional, strongly recommended when directory scope exists
  summary: ["..."]
  files_touched:
    - path: "..."
      change: "modified|added|deleted|renamed"
  commands_executed: ["..."]    # exact commands, in order
  checkpoints:                  # REQUIRED if run_style=POTENT
    - name: "CP1"
      intent: "..."
      status: "DONE|SKIPPED|FAILED"
      gates:
        - name: "..."
          command: "..."
          result: "PASS|FAIL|SKIP"
          evidence_refs: ["..."]
      notes: "optional"
  gates:                        # overall gates (optional if audit-only)
    - name: "..."
      command: "..."
      result: "PASS|FAIL|SKIP"
      evidence_refs: ["..."]
  evidence_refs: ["..."]        # file paths + stdout references (see 4.2)
  handoff_file: "docs/_inbox/subagent_handoffs/<run_id>.json"
  handoff_written: true|false
  gaps: ["GAP/NO_VERIFICADO: ..."]
  risks_or_regressions: ["optional"]

copilot_packet:
  current_state: ["evidence-linked truths (post-run)"]
  decisions_made: ["decision + why + evidence"]
  open_issues: ["blocking issues + proposed next step"]
  approvals_needed:
    - item: "..."
      reason: "risk/scope/cost/destructive"
      options: ["approve", "approve_with_changes", "pause"]
  questions_to_user: ["max 5, only blocking next step"]
  next_phase: null |            # MUST be null unless provided by orchestrator plan
    phase_name: "..."
    objective_one_sentence: "..."
    mode: READ_ONLY|APPLY
    scope_paths: ["..."]
    allowed_exceptions: ["..."]
    done_criteria: ["[ ] ..."]
    gates: [{name: "...", command: "..."}]
  suggested_next_steps: ["optional, non-binding options"]
  next_prompt_ready:            # OPTIONAL; DRAFT for orchestrator only
    prompt_text: |-
      FULL copy/paste prompt draft for the next run.
      NOT to be auto-executed by the coder.
  ledger_guidance:
    should_write_ledger: true|false
    ledger_path: "..."
    seq_strategy: "read_last_entry_then_increment"
    entry_template: "optional"
```

### 4.2 Evidencia: convención para stdout y archivos

`evidence_refs` MAY incluir:

- rutas de archivo: `path/to/file`, `logs/x.log`
- referencias a stdout: `STDOUT:T1.3`, `STDOUT:G2`, `STDOUT:CMD_07`
- si el entorno captura logs: `CMDLOG:<path>` (solo si existe)

**Regla:** toda afirmación importante debe apuntar a algún `evidence_ref`.

### 4.3 HANDOFF FILE MINIMUM (MUST)

El archivo `HANDOFF_FILE` MUST incluir JSON válido con:

- `run_id`
- `status` (`success|failed|partial`)
- `summary` (lista corta)
- `files_changed` (lista de paths)
- `gates` (nombre/comando/result)
- `gaps` (lista)
- `commit_hash` (`N/A` si no aplica)
- `generated_at`

### 4.4 MINIMUM_COPILOT_PACKET (MUST)

Aunque se omita `next_prompt_ready`, `copilot_packet` MUST incluir como mínimo:

- `current_state`
- `open_issues` (vacío si none)
- `approvals_needed` (vacío si none)
- `questions_to_user` (vacío si none)
- `suggested_next_steps` (vacío si none)

---

## 5) Políticas Especiales

### 5.1 READ_ONLY (strict vs audit con writes)

- **READ_ONLY_STRICT (default):**
  - `allowed_exceptions: []`
  - usar comandos de inspección (cat/ls/rg/grep/status) que no escriban.
  - NO ejecutar workers/tests/“doctors” si escriben outputs.

- **READ_ONLY_AUDIT (permitido):**
  - sigue siendo `MODE: READ_ONLY` (no muta código/estado de negocio),
  - pero permite comandos que generen **outputs** (logs/reports) SOLO si:
    - `ALLOWED_EXCEPTIONS` lista esos outputs (p.ej. `docs/_inbox/*latest.json`, `logs/*latest.json`),
    - el prompt lo declara explícitamente: “READ_ONLY_AUDIT: writes allowed only to ALLOWED_EXCEPTIONS”.

### 5.2 Ledger (atemporal)

- si se escribe ledger: debe estar en `SCOPE_PATHS` o `ALLOWED_EXCEPTIONS`
- `seq` MUST calcularse leyendo la última entrada (evidencia) → `last+1`
- no hardcodear `seq` ni asumir el formato si no está verificado (`GAP`)

### 5.3 Non-blocking backoff (worker/heartbeat)

Si el prompt pide backoff/retry en un worker:

- MUST ser **non-blocking** (timestamp scheduling), no `sleep` que bloquee el loop.
- Si el runtime no permite scheduling, reportar `GAP` y proponer alternativa.

### 5.4 JSON strict

- JSON MUST ser JSON válido: **no comentarios**.
- Para “notas”, usar `"_note"` o doc separado permitido.

---

## 6) RUN_STYLE=POTENT (macro-run confiable)

**Objetivo:** runs largos con poca interacción humana, pero auditables.

Si `RUN_STYLE=POTENT`, el prompt MUST incluir:

1. **CHECKPOINT_PLAN (3–6):** cada CP con intent + scope + gates por CP.
2. **HALT_CONDITIONS:** STOP inmediato si:
   - gate FAIL
   - se requiere tocar fuera de scope/exceptions
   - surface change no solicitado
   - aparece secreto
   - incertidumbre crítica no verificable
   - se requiere red/HTTP cuando está prohibido
3. **Checkpoint independence (SHOULD):** cada CP debe dejar el repo en estado verificable (gates pasan) antes de seguir.
4. **Core-module spread guard (SHOULD):** si el macro-run toca >2 módulos core (ingress/classifier/heartbeat/memory), endurecer gates por CP o dividir en POTENT-A/B.
5. **Destructive ops (MUST):** fuera por defecto; si se requiere, pedir aprobación y acotar superficie.

---

## 7) Contrato de Misión LIVE (Subagente)

- plan local por misión
- iteración: plan → prompt → run → evidencia → update plan
- puede usar POTENT dentro de la misión, pero mantiene checkpoints + halt conditions
- cierre con YAML consolidado (mission_close + copilot_packet)

---

## 8) Diseño de Prompts (reglas de precisión)

### 8.1 Campos requeridos (MUST)

Todo prompt a coder/subagente MUST incluir:

- header completo (sección 3)
- constraints hard
- done criteria
- gates/audit commands
- output schema YAML

### 8.2 Baselines (atemporal)

- No usar umbrales rígidos (“pytest < N”) como condición dura.
- Preferir: “no new failures vs baseline evidenciado (STDOUT/log/ledger)”.

### 8.3 Directorios en scope

Si `SCOPE_PATHS` contiene directorios:

- MUST declarar `MAX_FILES_TOUCHED` o lista acotada de archivos/globs.

---

## 9) Plantillas Copiables

Incluye plantillas ATOMIC/POTENT/READ_ONLY_STRICT/READ_ONLY_AUDIT/CLAUDE_CODE (ver versión fuente enviada por Mateo).

---

## 10) Prompt Lint (validador pre-envío)

Un prompt es válido solo si:

1. `ROUTE`, `RUN_STYLE`, `MODE`, `STOP_AFTER` presentes
2. `SCOPE_PATHS` presente
3. `ALLOWED_EXCEPTIONS` presente (aunque sea `[]`)
4. anchors semánticos (no line numbers)
5. `RUN_STYLE=POTENT` → CP plan 3–6 + gates por CP + halt conditions + YAML checkpoints
6. `MODE=READ_ONLY` → no side-effects **o** READ_ONLY_AUDIT con `ALLOWED_EXCEPTIONS` explícitas
7. no hardcodear `seq` ni conteos como regla rígida
8. directorios en scope → `MAX_FILES_TOUCHED` o lista acotada
9. output schema exige YAML único con `run.allowed_exceptions` + `copilot_packet minimum`
10. `next_prompt_ready` (si existe) marcado como DRAFT para orquestador; coder no lo auto-ejecuta

---

## 11) Riesgos típicos + antídotos (operacionales)

- **Hallucination** → evidencia obligatoria + GAP
- **Scope creep** → scope/exceptions + halt condition
- **READ_ONLY con writes inesperados** → READ_ONLY_STRICT o declarar exceptions
- **POTENT demasiado ancho** → gates por CP + split A/B si toca demasiados core modules
- **Baselines rígidos** → “no new failures vs baseline evidenciado”
- **Destructive ops coladas** → prohibición por defecto + aprobación + scope explícito
- **Directorios amplios** → max files / lista acotada
- **Confusión next_prompt_ready** → autoridad del orquestador explícita

---

## 12) Política de esfuerzo (alineada a prompts potentes)

- Preferencia por autonomía se implementa con `RUN_STYLE=POTENT` + checkpoints + gates + halt conditions + evidencia.
- `ATOMIC` se reserva para incertidumbre alta, debugging fino o cambios delicados.
- Para evitar “mini-prompts” sin perder confiabilidad:
  - usar POTENT con 3–6 checkpoints,
  - dividir solo cuando el spread de módulos/risgo lo amerite (POTENT-A/B),
  - mantener el `copilot_packet minimum` para continuidad inmediata.

---

END_OF_DOCUMENT: PROMPT_MANUAL.md

# CLAUDE

Wrapper de entrada para Claude Code.

## Authority / Redirect

- Canon: `CEO.md`
- Mapa operativo de contexto: `openclaw/CONTEXT_MAP.md`
- Hub transversal: `INDEX.md`
- Hub de conocimiento: `brain/00_INDEX.md`
- Canon modular Claude Code: `.claude/CLAUDE.md`
- Reglas modulares: `.claude/rules/00_CANON.md`

## Base Required Reading

- `PROJECT_BRIEF.md`
- `REPO_MAP.md`
- `repo_map/00_INDEX.md`
- `repo_map/80_PROD_SAFETY.md`
- `repo_map/90_LEGACY_RECOVERY.md`
- `openclaw/CONTEXT_MAP.md`

Antes de tocar `scripts/`, `state/` o `hooks/`, seguir las rutas minimas de `REPO_MAP.md`.

## Sub-Agent Quickstart

- Este repo usa autoridad por capas, no por archivos duplicados.
- Orden corto: `CEO.md` -> `INDEX.md` -> `brain/00_INDEX.md` -> `openclaw/CONTEXT_MAP.md`.
- Usa `TOOLS.md` para notas locales y setup operativo.
- Registra evidencia de run en `docs/_inbox/`.
- Para outputs deterministas usa `logs/` o `state/` si aplica.
- Mantén trazabilidad en `ops/RUN_LEDGER.ndjson`.
- Guardrail 1: no inventes.
- Guardrail 2: no borres.
- Guardrail 3: no reordenas masivamente.

## Delegation

- Politica de delegacion canonica: `brain/domains/openclaw_ops/07_DELEGATION_POLICY.md`.
- Matriz corta: `brain/cards/openclaw_ops/card_delegation_matrix.md`.
- Si el run depende de `.claude/*`, usar Claude Code; en caso contrario default Codex.

## Runtime Mission (NL-first)

- El sistema debe operar sin comandos del usuario para intake/memoria/aprobaciones.
- Mantener zero-mix por session_id (chat/canal/thread) y budgets por canal.
- Para WhatsApp: solo dominio SG, sin alimentar memoria personal.

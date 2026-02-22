# Card: Delegation Matrix

id: card-openclaw-delegation-matrix-001
type: principle
tags: delegation,codex,claude,policy
source_ref: brain/domains/openclaw_ops/07_DELEGATION_POLICY.md; .claude/CLAUDE.md; openclaw/CONTEXT_MAP.md
status: active
confidence: 0.95
last_confirmed_at: 2026-02-18

## Summary

Matriz corta de delegacion operativa:

- default -> Codex
- plugins/rules/imports `.claude/*` -> Claude Code
- cowork permitido -> Codex + Claude Cowork
- P0 critico/primera vez/alto riesgo -> NO coder autonomo (modo supervisado por etapas)
- P1 importante/alta calidad -> sin coder autonomo (control directo)
- P2 repetitivo/bajo riesgo -> coder directo con handoff minimo verificable (sin vigilancia en vivo)

## How to apply

En cada run deja `delegate_to`, `reason` y `evidence_paths` en el reporte persistente.

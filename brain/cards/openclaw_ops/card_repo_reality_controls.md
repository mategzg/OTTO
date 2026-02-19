# Card: Repo Reality Controls

id: card-openclaw-repo-reality-001
type: playbook
tags: root,quarantine,salvage
source_ref: scripts/repo_root.py; scripts/repo_reality_doctor.py; state/repo_reality_state.json; state/repo_reality_allowlist.json
status: active
confidence: 0.92
last_confirmed_at: 2026-02-18

## Summary

La raiz canonica se pinnea con marker y el doctor gestiona nested/pathlike con quarantine no-destructiva.

## How to apply

Usar `--scan --json` para diagnostico, y comandos `/repo` para fijar root y aplicar quarantine controlada.

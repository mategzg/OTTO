# Workspace Hygiene

## Purpose

Definir politica y operaciones para mantener `otto-workspace` limpio, ruteable y seguro.

## Use when

- Debes clasificar root entries (canon/tooling/junk/sensitive).
- Debes mover junk/sensitive a quarantine sin borrar.
- Debes escanear `/home/agente` sin tocar dot-dirs.

## Avoid when

- Se pretende limpiar con delete permanente.
- Se pretende tocar `~/.openclaw/**`.

## Routing

- Scan workspace: `python3 scripts/workspace_hygiene_doctor.py --scan`
- Clean workspace: `python3 scripts/workspace_hygiene_doctor.py --clean`
- Scan home: `python3 scripts/home_hygiene_doctor.py --scan --root /home/agente`
- Clean home obvious: `python3 scripts/home_hygiene_doctor.py --clean-obvious --root /home/agente`

## Maintenance

- Politica fuente: `state/workspace_hygiene_policy.json`.
- Mantener `vault/_quarantine/**`, `vault/_salvage/**`, `vault/inbox_raw/**` fuera de indexers.

## Links

- `state/workspace_hygiene_policy.json`
- `scripts/workspace_hygiene_doctor.py`
- `scripts/home_hygiene_doctor.py`
- `brain/cards/openclaw_ops/card_hygiene_policy.md`

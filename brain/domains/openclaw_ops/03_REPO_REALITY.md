# Repo Reality Controls

## Purpose

Concentrar reglas de raiz canonica, deteccion de repos fantasma y cuarentena segura.

## Use when

- Aparece path sospechoso (`C:\`, `:\`, `\\Users\\`) o nested repo.
- Debes aplicar salvage/quarantine no-destructivo.

## Avoid when

- El problema no involucra estructura de repo ni walkers.
- La accion implicaria borrar contenido.

## Routing

- Diagnostico: `python3 scripts/repo_reality_doctor.py --scan --json`
- Fix controlado: `/repo fix` o flujo `/repo salvage` -> `/repo apply-salvage` -> `/repo quarantine <id>`.
- Root pinning: `/repo roots` -> `/repo setroot <id>`.

## Maintenance

- Mantener alineado con `scripts/repo_root.py` y `scripts/repo_reality_doctor.py`.
- Tratar conflictos de alto impacto como bloqueo plan-only.

## Links

- `scripts/repo_root.py`
- `scripts/repo_reality_doctor.py`
- `brain/cards/openclaw_ops/card_repo_reality_controls.md`

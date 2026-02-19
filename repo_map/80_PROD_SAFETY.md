# 80 Prod Safety

Rutas minimas:

1. Hook backlog: `scripts/hook_backlog.py` + `state/hook_backlog_policy.json`.
2. Safety switch: `scripts/safety_switch.py` + `state/safety_switch.json`.
3. Prod doctor: `scripts/prod_doctor.py` + `docs/_inbox/prod_doctor_latest.json`.
4. Orquestacion: `scripts/heartbeat_worker.py` (replay/backoff/autopause).

Checklist de recuperacion:

- Ver estado global: `python3 scripts/safety_switch.py --status`.
- Ver backlog pending/fallos: `python3 scripts/hook_backlog.py --scan --root .`.
- Forzar replay controlado: `python3 scripts/hook_backlog.py --replay --root .`.
- Si procede, reanudar: `python3 scripts/safety_switch.py --resume --reason "manual_recovery"`.
- Ejecutar heartbeat forzado: `python3 scripts/heartbeat_worker.py --once --root . --force`.
- Audit/packaging de coldstore: `repo_map/90_LEGACY_RECOVERY.md`.

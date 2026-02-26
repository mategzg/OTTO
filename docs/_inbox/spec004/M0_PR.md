# SPEC-004 M0: Guardrails + no-leak boundaries

Status: READY_FOR_PR
Milestone: M0
Spec contract: docs/_inbox/SPEC004_PR_PLAN.md

## Scope
- [x] dmScope seguro WhatsApp por peer real (`session_memory_manager.build_session_id`).
- [x] sendPolicy bloquea delivery `cron:`/`hook:` hacia clientes (`outbox_delivery._should_block_send`).
- [x] tool allow/deny por agente con fallback seguro (`nl_skill_router` + `runtime_guardrails`).
- [x] No-leak aplicado en path de redacción + archive sin stdout/stderr.

## Required tests/gates
- `pytest -q tests/test_spec004_m0_guardrails.py tests/test_session_memory_manager.py tests/test_outbox_queue_and_delivery_mock_cli.py tests/test_nl_skill_router.py tests/test_acl_no_leak_candidates.py tests/test_acl_no_leak_citations.py`
  - Resultado: `20 passed`
  - Evidencia: `audit/M0/pytest_spec004_m0.txt`

## Evidence artifacts
- `audit/M0/no_leak_report.json` (requerido)
- `audit/M0/security_audit_deep.json` (reporte security audit --deep)
- `audit/M0/commands.ndjson` (comandos exactos)
- `audit/M0/hashes.sha256` (hash manifest reproducible)

## Security audit
- Comando: `openclaw security audit --fix` seguido de `openclaw security audit --deep --json`
- Resultado: `critical=0, warn=2, info=1`
- Warnings remanentes: `gateway.trusted_proxies_missing`, `config.secrets.gateway_password_in_config`

## Rollback
- Revert commit(s) de branch `spec004/m0`.
- Restaurar guardrails previos eliminando `scripts/runtime_guardrails.py` y su wiring en router/session/outbox.

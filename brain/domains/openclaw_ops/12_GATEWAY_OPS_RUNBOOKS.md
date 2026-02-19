# OpenClaw: Gateway Ops y Runbooks

> Source: Operator's Manual Win11+WSL2 (manual ingest 2026-02-19)
> Raw: vault/inbox_raw/processed/2026-02-19_openclaw_operators_manual_win11_wsl2.md

## Day-1: Arranque Mínimo

```bash
openclaw gateway --port 18789
openclaw gateway status
openclaw status
openclaw logs --follow
openclaw channels status --probe
```

Gateway corre hasta que lo detienes. Fatal → exit non-zero para supervisor restart. Hot reload de config con `gateway.reload.mode` (default hybrid) y SIGUSR1.

## Day-2: Operación Continua

- `openclaw gateway status --deep` / `openclaw status --deep`: probes
- `openclaw health --json`: snapshot via WS
- `openclaw doctor`: runbook guiado que valida y repara estado/config
- Logs: `openclaw logs --follow` (JSON mode: objetos type-tagged)

## Canales de Actualización

| Canal | npm dist-tag | Nota |
|---|---|---|
| stable | `latest` | Producción |
| beta | `beta` | Puede coincidir con stable |
| dev | `dev` | Head de main |

Fijar canal y automatizar verificación post-update.

## Diagnóstico "Primeros 60 Segundos"

```bash
openclaw status
openclaw status --all
openclaw gateway status
openclaw status --deep
openclaw logs --follow
openclaw doctor
openclaw health --json
openclaw health --verbose
```

## Runbook: Gateway No Responde

1. `openclaw gateway status` → si no running: `openclaw gateway --force`
2. Si running pero probe no OK: revisar auth/bind/config, `health --verbose`
3. Port precedence: `--port` → env → config → 18789
4. Bind loopback por defecto; no-loopback requiere auth

## Runbook: Unauthorized / Pairing Required

- Remote connections requieren device approval
- `openclaw devices list` + `openclaw devices approve <id>`

## Runbook: Config Inválida

- `openclaw doctor` + `openclaw plugins doctor`
- Manifests inválidos bloquean validación

## Top 10 Fallos Comunes

| # | Fallo | Fix Rápido |
|---|---|---|
| 1 | Gateway unreachable | `gateway --force`, restart service |
| 2 | Unauthorized/pairing | `devices approve <id>` |
| 3 | Config inválida | `doctor` + `plugins doctor` |
| 4 | Browser disabled | `browser.enabled=true` + restart |
| 5 | Badge `!` | Node host en Windows o portproxy |
| 6 | No tab connected | Attach manual (badge ON) + `--browser-profile chrome` |
| 7 | No click/type | Instalar Playwright |
| 8 | Refs flaky | Re-snapshot |
| 9 | Webhooks 401 | Header `Authorization: Bearer`, no query param |
| 10 | Skill/plugin sospechoso | Deshabilitar, cortar egress, rotar tokens, revisar logs |

## Hooks, Plugins y Skills (Operacional)

### Hooks
- Discovery: workspace → managed → bundled
- Gestión: `openclaw hooks enable/list/check/info`
- Bundled útiles: command-logger, session-memory, boot-md

### Plugins
- Requiere `openclaw.plugin.json` con id + configSchema
- Gestión: `openclaw plugins list/install/enable/disable/update/doctor`

### Webhooks
- Endpoint: `/hooks/*` con token obligatorio
- Preferir header; query param deprecado

## Quick Start Operador (15 min)

**0-5 min**: Gateway arriba + baseline status
**5-10 min**: Extension install + attach (badge ON)
**10-15 min**: tabs + snapshot + click con refs

## Test Matrix

| ID | Test | Comando | Expected |
|---|---|---|---|
| T01 | Health baseline | `openclaw gateway status` | running + probe ok |
| T02 | Deep status | `openclaw status --deep` | sin errores |
| T03 | Logs | `openclaw logs --follow` | stream JSON |
| T04 | Extension | `browser extension install` | carga + attach |
| T05 | Badge | Attach tab | ON (no !) |
| T06 | Tabs | `browser --browser-profile chrome tabs` | targetId(s) |
| T07 | Snapshot | `snapshot --interactive` | refs visibles |
| T08 | Click/type | `click/type <ref>` | acción ejecuta |
| T09 | Webhooks | POST /hooks/wake con auth | 200/202 |
| T10 | Exec safety | `openclaw approvals get --gateway` | policy visible |

## Dual-Host: WSL2 Gateway + Chrome Windows

Decisión clave: **node host en Windows** (preferida) vs **portproxy**.
- Node host: relay vive en mismo host que Chrome, elimina loopback mismatch.
- Portproxy: `netsh interface portproxy` para 18789/18792.

Node host como service: `openclaw node install` / `status` / `restart`.

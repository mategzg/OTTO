# OpenClaw: Seguridad y Hardening

> Source: Operator's Manual Win11+WSL2 (manual ingest 2026-02-19)
> Raw: vault/inbox_raw/processed/2026-02-19_openclaw_operators_manual_win11_wsl2.md

## Threat Model

OpenClaw es un agente local con acceso a FS/commands/browser. Comprometer Gateway o token = comprometer host + credenciales accesibles. Hay CVEs publicados en 2026.

## CVEs Relevantes (con fix versions)

| CVE | Descripción | Fix Version |
|---|---|---|
| CVE-2026-25253 | 1-click RCE via token exfiltration en Control UI | ≥2026.1.29 |
| CVE-2026-24763 | Command injection en Docker sandbox exec vía PATH | ≥2026.1.29 |
| CVE-2026-25593 | Unauthenticated local RCE via WS config.apply | ≥2026.1.20 |
| /cdp origin validation | Origin Validation Error en relay /cdp (Snyk) | ≥2026.2.1 |

## Hardening por Capas

### P0 (Crítico)
- **Patching**: versión ≥2026.2.1 para cubrir todos los CVEs conocidos
- **Network**: Gateway bind loopback por defecto. Binds no-loopback requieren auth. No exponer 18789/18791/18792 a LAN/Internet.
- **Auth**: configurar `gateway.auth.*` (token/password). Webhooks: usar header `Authorization: Bearer`, no query param (deprecado).
- **Supply-chain**: skills/plugins = código ejecutable. Revisar contenido, pin versions, no instalar de ClawHub sin auditoría.
- **Exec safety**: sandbox con approvals/allowlists, default deny cuando UI no disponible.

### P1 (Importante)
- **Browser**: preferir perfil `openclaw` (aislado). Deshabilitar `browser.evaluateEnabled=false` si no necesitas JS eval. No usar `chrome` contra daily-driver si threat model incluye navegación por sitios no confiables.
- **Pairing**: DM pairing para entradas no confiables. Aprobar senders/devices explícitamente.

### P2 (Deseable)
- **Provenance**: verificación npm provenance cuando exista.
- **Logs**: automatizar `openclaw status --all` como reporte de soporte.

## Do / Don't

### Do
- Gateway y nodes en red privada (e.g. tailnet)
- Usar `tools.allow/deny` para minimizar tools expuestos
- Usar approvals/allowlists para host exec en sandbox

### Don't
- No usar profile `chrome` contra daily-driver sin guardrails
- No exponer 18792 (relay) fuera de loopback (vector CSWSH rompe "localhost-only")
- No instalar skills/plugins no auditados

## Supply-Chain Risk (Hechos Reportados)

- Campañas de skills maliciosas en ClawHub que instruyen ejecutar comandos ofuscados para descargar malware.
- Análisis de Snyk describe dificultad de escanear instrucciones en SKILL.md.
- Implicación: "instalar skill" = "instalar software con acceso local". Requiere revisión + pinning + sandbox.

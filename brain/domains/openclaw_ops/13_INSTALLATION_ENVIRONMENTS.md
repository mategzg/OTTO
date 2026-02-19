# OpenClaw: Instalación y Entornos

> Source: Operator's Manual Win11+WSL2 (manual ingest 2026-02-19)
> Raw: vault/inbox_raw/processed/2026-02-19_openclaw_operators_manual_win11_wsl2.md

## Instalación

Camino recomendado: installer (`install.sh`) + onboarding. Windows: usar WSL2.

Updates como shipping infra: update → checks → restart → verify. Installer re-ejecutado es camino preferido.

## Workspace Recomendado

```
<workspace>/
  AGENTS.md
  IDENTITY.md
  skills/          # máxima precedencia
  hooks/           # máxima precedencia
  memory/
  data/            # outputs
~/.openclaw/
  openclaw.json    # config principal (JSON5)
  .env             # env fallback
  skills/          # compartidos (managed)
  hooks/           # compartidos (managed)
  extensions/      # plugins
  logs/
```

## Multi-Agent

`openclaw agents` para crear agentes con workspaces separados. Cada agente tiene workspace y sesiones aisladas.

## Nuestro Entorno

- **Host OS**: Windows 11
- **Linux runtime**: WSL2 Ubuntu (Gateway corre aquí)
- **Browser**: Chrome en Windows (tabs reales + sesiones logueadas)
- **Browser control**: Chrome extension relay + CLI

## Gaps del Manual Original

1. GitHub connector no accesible para citas internas
2. Repo oficial no usado como fuente primaria (restricción de entorno)
3. Versión latest stable no verificada de forma primaria → usar `openclaw status`
4. CLI `openclaw cron` y `openclaw update status` sin documentación exhaustiva
5. Strings exactos de errores no verificados → mapeados por síntomas equivalentes

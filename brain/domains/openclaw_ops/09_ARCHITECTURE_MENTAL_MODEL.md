# OpenClaw: Modelo Mental y Arquitectura

> Source: Operator's Manual Win11+WSL2 (manual ingest 2026-02-19)
> Raw: vault/inbox_raw/processed/2026-02-19_openclaw_operators_manual_win11_wsl2.md

## Resumen

OpenClaw es un Gateway (control/event plane) siempre encendido que centraliza estado (sesiones, routing, presence), integra canales y ejecuta el loop del agente con herramientas tipadas y superficies de control (CLI/TUI/Control UI).

## Componentes Clave

- **Gateway**: proceso always-on, mantiene conexiones de canales, expone WS+HTTP en puerto multiplexado, coordina agentes/sesiones/hooks/nodes.
- **Operator client**: CLI/TUI/Control UI conecta por WS con rol y scopes (operator.read/write).
- **Node**: dispositivo/host conectado por WS con rol node, expone capacidades (system.run, canvas, camera, browser proxy).
- **Channel**: integración de mensajería (Telegram, WhatsApp, Slack, etc.).
- **Tool**: interfaz tipada expuesta al LLM (browser, exec, cron, etc.).
- **Skill**: paquete AgentSkills-compatible (SKILL.md + frontmatter).
- **Plugin**: extensión in-process con openclaw.plugin.json.
- **Hook**: script en eventos internos (command:new, agent:bootstrap, gateway start).
- **Webhook**: endpoint HTTP del Gateway para triggers externos (/hooks/*).

## Diagrama de Alto Nivel

```
OPERATORS (CLI/TUI/Control UI/Hooks/Webhooks)
        │ (WS + HTTP) 18789 (default)
        v
┌─────────────────────────────────────────────────┐
│ GATEWAY                                         │
│ - Control plane + event plane                   │
│ - Sessions + routing + presence                 │
│ - Channels (WhatsApp/Telegram/Slack/...)        │
│ - Tool policy (allow/deny, profiles)            │
│ - Plugins (in-process) + Hooks                  │
│                                                 │
│ Derived loopback services:                      │
│   Browser control: 18791 (gateway+2)            │
│   Browser relay:   18792 (control+1)            │
│   Canvas host:     18793 (gateway+4)            │
└────────────┬──────────────────┬─────────────────┘
             │                  │
             v                  v
        TOOLS              NODES
   browser/exec/cron    system.run, browser
                        proxy, canvas
```

## Port Family (derivado de gateway.port)

| Service | Default Port | Derivation |
|---|---|---|
| Gateway (WS+HTTP) | 18789 | base |
| Browser control | 18791 | gateway+2 |
| Browser relay (extension) | 18792 | control+1 |
| Canvas host | 18793 | gateway+4 |

## Control Plane vs Execution Plane

- **Control plane**: handshake WS, métodos health/status/agent, events y presence.
- **Execution plane**: herramientas (browser/exec/process) y canales concretos. Aquí viven la mayoría de incidentes operacionales.

## Estado y Datos

- State dir: `$OPENCLAW_STATE_DIR` (default `~/.openclaw`)
- Workspace: `~/.openclaw/workspace` (configurable por agente)
- Config: `~/.openclaw/openclaw.json` (JSON5)

## WS Protocol (Operador)

```
Client                          Gateway
  WS connect ──────────────────>
  <──── connect.challenge (nonce, ts)
  req connect (first frame) ───>  validate (AJV schema)
  <──── res hello-ok OR error+close
```

# OpenClaw: Browser Relay y Automatización Web

> Source: Operator's Manual Win11+WSL2 (manual ingest 2026-02-19)
> Raw: vault/inbox_raw/processed/2026-02-19_openclaw_operators_manual_win11_wsl2.md

## Modelos de Browser

| Modo | Sesiones logueadas | Aislamiento | WSL2→Windows | Blast radius |
|---|---|---|---|---|
| `chrome` (extension relay) | Sí | Bajo | Medio/alto | Alto |
| `openclaw` (managed) | No (perfil aislado) | Alto | Bajo | Menor |
| Remote CDP | Depende | Depende | Alto | Muy alto |

## Puertos

- Browser control service: loopback 18791 (gateway+2)
- Relay extension: 18792 (control+1)

## Badge Semántica (Chrome Extension)

- **ON**: attached, OpenClaw puede conducir ese tab.
- **…**: conectando al relay local.
- **!**: relay no reachable (relay server no corriendo en esa máquina).

Attach es **manual**: click en toolbar por cada tab.

## WSL2 + Chrome Windows: Dos Estrategias

1. **Node host en Windows** (preferida): correr node host en Windows, conectar al Gateway en WSL. Gateway proxy-route browser hacia el node. Elimina clase de fallos "WSL loopback mismatch".
2. **Portproxy**: `netsh interface portproxy` para publicar puertos WSL hacia Windows.

**Test rápido**: si en Windows la extensión muestra `!`, Chrome no alcanza `127.0.0.1:18792`.

## CLI Browser (Comandos Verificados)

```bash
# Estado y perfiles
openclaw browser --browser-profile chrome tabs
openclaw browser --browser-profile openclaw status/start
openclaw browser profiles
openclaw browser create-profile --name work --color "#FF5A36"

# Tabs
openclaw browser tabs
openclaw browser open <url>
openclaw browser focus <targetId>
openclaw browser close <targetId>

# Snapshots y acciones (ref-based)
openclaw browser snapshot --interactive --compact --depth 6
openclaw browser snapshot --labels
openclaw browser click <ref>
openclaw browser type <ref> "hello" --submit
openclaw browser navigate <url>
openclaw browser evaluate --fn '(el) => el.textContent' --ref <ref>
```

## Refs

- AI snapshot (numéricos) y role snapshot (tipo `e12`).
- **No estables** entre navegaciones → re-snapshot antes de cada acción si hubo DOM shift.
- CSS selectors intencionalmente no soportados.

## Playwright: Requerimiento Crítico

Muchas features (navigate/act/snapshots AI/role, pdf) requieren Playwright. Sin Playwright → endpoints retornan 501. Para extension relay, incluso ARIA snapshots y screenshots lo requieren.

## Árbol de Fallas

### "No tab connected"
1. ¿Extensión attached? → No → Click icon toolbar, badge debe quedar ON
2. ¿Badge muestra `!`? → Sí → Relay no reachable, verificar loopback 18792
3. ¿CLI usa `--browser-profile chrome`? → No → Reintentar con chrome
4. Sí → Re-listar tabs y focus

### "Abre URLs pero no click/type"
- Causa: Playwright no disponible → reinstalar con browser support

### "Refs flaky"
- Re-snapshot; usar `--labels` para overlay diagnóstico

### "Can't reach browser control service"
- Verificar `browser.enabled=true`, reiniciar Gateway

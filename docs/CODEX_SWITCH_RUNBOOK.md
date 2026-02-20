# CODEX Switch Runbook (2 cuentas)

Objetivo: cambiar rápido entre cuentas Codex sin fricción.

## Estado actual (hoy)
- OpenClaw detecta **1 perfil OAuth activo**: `openai-codex:default`.
- Para usar la otra cuenta, se debe correr login OAuth y completar en navegador.

## Comandos rápidos

### 1) Ver estado actual
```bash
cd /home/agente/otto-workspace
./scripts/codex_switch_helper.sh . status
```

### 2) (Opcional) snapshot pre-cambio
```bash
cd /home/agente/otto-workspace
./scripts/codex_switch_helper.sh . snapshot
```

### 3) Cambiar a la otra cuenta (login OAuth)
```bash
cd /home/agente/otto-workspace
./scripts/codex_switch_helper.sh . switch-login
```
Esto abre/lanza flujo de auth. Loguéate con la **otra** cuenta.

### 4) Confirmar que quedó bien
```bash
cd /home/agente/otto-workspace
./scripts/codex_switch_helper.sh . status
```

## Nota operativa
- OTTO puede detectar cuándo conviene cambiar y avisarte.
- El cambio de cuenta OAuth requiere acción humana (consent/browser).
- Después del cambio, OTTO sigue operando normal con la sesión nueva.

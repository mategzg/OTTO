# Deploy + conexión real (Vercel)

## Variables de entorno
Configura estas variables en Vercel Project Settings -> Environment Variables.

### Seguridad dashboard (recomendado)
- `DASHBOARD_AUTH_USER` = usuario basic auth
- `DASHBOARD_AUTH_PASS` = password basic auth

Si no defines estas dos, el dashboard queda sin auth.

### Fuente de datos en vivo (opcional, recomendado)
- `OTTO_DASHBOARD_URL` = endpoint GET con payload dashboard-v1
- `OTTO_DASHBOARD_TOKEN` = bearer token opcional para ese endpoint

### Acciones reales (opcional, recomendado)
- `OTTO_ACTIONS_BASE_URL` = base URL del runtime OTTO
- `OTTO_ACTIONS_TOKEN` = bearer token opcional para acciones POST

El dashboard llamará:
- `POST {OTTO_ACTIONS_BASE_URL}/api/actions/refresh`
- `POST {OTTO_ACTIONS_BASE_URL}/api/actions/pause-delegation`
- `POST {OTTO_ACTIONS_BASE_URL}/api/actions/execute-sg`
- `POST {OTTO_ACTIONS_BASE_URL}/api/actions/sg-alternative`
- `POST {OTTO_ACTIONS_BASE_URL}/api/actions/execute-personal`

## Deploy
```bash
vercel --cwd dashboard --prod --yes
```

## Verificación rápida
1. Abre la URL productiva.
2. Debe pedir credenciales (si auth está activa).
3. `Actualizar` debe responder 200.
4. CTAs deben responder 200 (o 502 si base URL/tokens no están configurados todavía).

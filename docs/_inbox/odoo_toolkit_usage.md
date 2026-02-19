# Odoo Toolkit OTTO (Expert Track #2)

Toolkit interno para ejecutar acciones Odoo por lenguaje natural, con foco en seguridad y auditoría.

## Estructura

- `scripts/odoo/odoo_client.py`
  - `OdooConfig.from_env()` para credenciales/config
  - `OdooClient.authenticate()` (auth robusta)
  - `OdooClient.execute_kw()` (llamadas Odoo con retries/timeout/auditoría)
- `scripts/odoo/odoo_actions.py`
  - Acciones atómicas: contacto, lead, actividad, oportunidades
- `scripts/odoo/odoo_cli.py`
  - CLI interno OTTO (no UX final)

## Variables de entorno

- `ODOO_URL`
- `ODOO_DB`
- `ODOO_USERNAME`
- `ODOO_PASSWORD`
- `ODOO_TIMEOUT` (opcional, default `15`)
- `ODOO_RETRIES` (opcional, default `3`)
- `ODOO_RETRY_BACKOFF` (opcional, default `0.5`)

## Uso rápido (interno)

```bash
python -m scripts.odoo.odoo_cli ping-auth
python -m scripts.odoo.odoo_cli create-contact --name "Juan Pérez" --email juan@acme.com
python -m scripts.odoo.odoo_cli create-lead --name "Interés en porcelanato" --contact-name "Juan" --email juan@acme.com
python -m scripts.odoo.odoo_cli schedule-activity --model crm.lead --res-id 123 --summary "Llamar" --activity-type-id 4
```

## Seguridad y auditoría

- Masking automático de secretos en logs (`password` nunca en claro)
- `timeout` de socket configurable
- Retries con backoff exponencial para errores transitorios
- Eventos auditables JSON (`auth_start`, `auth_ok`, `execute_start`, `execute_ok`, `retry`)

## Testing

```bash
pytest -q tests/test_odoo_client.py tests/test_odoo_actions.py
```

Cobertura enfocada a:
- Auth/errores/retries en cliente
- Estructura de payloads en acciones atómicas

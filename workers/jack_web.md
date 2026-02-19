# JACK Web Adapter (V2 - Manual/Semi-automatizado)

JACK se usa solo para conocimiento y criterio interno SG.
No usar JACK para temas personales o fuera de SG.

## Precondiciones

1. URL real de JACK guardada en `docs/empresa/JACK_URL.txt`.
2. Sesion de ChatGPT Web activa en browser relay.
3. Prompt en formato SG-only (ver template).

## Flujo operacional (Browser Relay)

1. Preparar prompt con `docs/empresa/templates/JACK_PROMPT_TEMPLATE.md`.
2. Abrir ChatGPT Web en relay/browser.
3. Navegar a la URL de JACK (`docs/empresa/JACK_URL.txt`).
4. Pegar prompt SG-only y enviar.
5. Esperar respuesta y revisar consistencia.
6. Guardar salida en:
   - `docs/empresa/cotizaciones/` (si aplica a precios/cotizaciones)
   - o documento SG correspondiente.
7. Ejecutar `python index_docs.py` para actualizar indices.

## Trazabilidad recomendada

- Crear request con `workers/jack_stub.py` (estado `needs_browser`).
- Mantener evidencia en `docs/_inbox/jack_requests/`.
- Registrar hitos en `logs/activity.ndjson` sin secretos.

## Nota

No implementar Playwright en V2 por estabilidad de selectores/sesion.
Se deja para V3.

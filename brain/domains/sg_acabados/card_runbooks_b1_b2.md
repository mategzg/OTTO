# Card: Runbooks B1 (Licitaciones) y B2 (Leads)

> Fuente: B1_LICITACIONES.md, B2_LEADS.md, ledger.md, JACK_PROMPT_TEMPLATE.md (legacy)
> Dominio: sg_acabados / operaciones

## B1 — Licitaciones (On-demand)
1. **Plan obligatorio** en `plans/` antes de ejecutar
2. Buscar/analizar según criterios definidos
3. Output: `docs/empresa/licitaciones/licitaciones_YYYY-MM-DD.md`
4. Cierre: actualizar ledger + índice

## B2 — Leads (On-demand)
1. **Plan obligatorio** en `plans/` antes de ejecutar
2. Prospectar por sector/geografía
3. Output: `docs/empresa/leads/leads_YYYY-MM-DD.md`
4. Cierre: actualizar ledger + índice

## Ledger SG
Tabla markdown con campos:
- Licitaciones: fecha, fuente, keyword, monto, deadline, riesgo, archivo_doc
- Leads: fecha, empresa, contacto, canal, ciudad, proyecto, archivo_doc

## Template JACK (solo SG)
```
Contexto SG: [unidad/área, cliente/proyecto, objetivo]
Consulta (SG-only): [precios, proveedores, criterios, cotizaciones]
Formato: 1) Resumen ejecutivo 2) Recomendación 3) Riesgos 4) Datos faltantes
```
JACK NO se usa para temas personales.

## Principio
Ambos runbooks son **on-demand** por Telegram. No hay cron automático. Siempre plan-first.

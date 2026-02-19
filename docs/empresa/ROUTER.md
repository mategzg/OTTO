# ROUTER - Delegated Execution Rules (V1)

## Objetivo

Definir cuando ejecuta OTTO directo, cuando delega a Coder CLI y cuando consulta a JACK.

## Plan-first (obligatorio)

Antes de cualquier mision grande, crear archivo en `plans/` con:

- objetivo
- alcance
- criterios de salida
- riesgos
- entregables

Sin plan previo, no iniciar ejecucion pesada.

## OTTO directo

OTTO ejecuta directo cuando la tarea es:

- coordinacion operativa
- lectura/escritura de estado, kanban, logs, indices
- acciones ligeras de dashboard o housekeeping
- interaccion de control con Telegram/OpenClaw

## Delegar a Coder CLI

Delegar a Coder cuando la tarea requiere:

- codigo nuevo o refactor grande
- organizacion masiva de archivos
- analisis tecnico pesado
- generacion de reportes largos reproducibles

Canal V1: `workers/coder_cli.py` + `dropzone/prompts` / `dropzone/results`.

## Delegar a JACK (solo SG)

JACK se usa solo para:

- precios SG
- proveedores SG
- politicas SG
- criterios de cotizacion SG

Canal V1: manual/semi-automatizado con URL en `docs/empresa/JACK_URL.txt`.

## No delegar a JACK

No usar JACK para:

- temas personales
- depas/vivienda
- vuelos/turismo
- consultas fuera del dominio SG

## B1 y B2

- B1 (licitaciones) y B2 (leads) son on-demand por Telegram.
- No hay ejecucion automatica diaria.
- Cada corrida debe actualizar artefactos en `docs/empresa/` y luego correr `python index_docs.py`.

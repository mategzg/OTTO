# Dropzone Contract (V2)

## Objetivo

Establecer handoff por archivos entre OTTO y ejecutores delegados.

## Prompt File

Ruta: `dropzone/prompts/<task_id>.md`

Formato:

```yaml
---
task_id: <id>
created_at: <ISO8601Z>
kind: coder
status: ok|error|needs_input
---
```

Body: instruccion completa y contexto minimo.

## Result File

Ruta: `dropzone/results/<task_id>.md`

Formato:

```yaml
---
task_id: <id>
created_at: <ISO8601Z>
kind: coder
status: ok|error|needs_input
---
```

Body sugerido:

- resumen de ejecucion
- output principal
- `files_changed:` lista de archivos tocados (si aplica)

## Reglas

- No incluir secretos ni tokens.
- Mantener `task_id` consistente entre prompt/result.
- Si no hay resultado a tiempo: estado `needs_input`.

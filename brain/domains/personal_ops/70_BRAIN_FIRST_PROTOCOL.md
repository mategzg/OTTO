# 70 — Brain-First Protocol

## Objetivo
Garantizar que cada respuesta/acción se apoye en conocimiento experto persistido, no en memoria conversacional efímera.

## Protocolo
1. Identificar tipo de tarea (operativa, técnica, legal, redacción, seguridad, etc.).
2. Abrir primero índice relevante (`brain/00_INDEX.md` + dominio específico).
3. Cargar solo nodos/ramas necesarios (anti-overread).
4. Si la tarea es compuesta, combinar explícitamente múltiples ramas expertas antes de actuar.
5. Aplicar reglas del dominio en la respuesta/ejecución (incluye acciones y prompts de delegación).
6. Si falta conocimiento especializado, crear/actualizar rama antes o durante el cierre.
7. Dejar evidencia: rutas consultadas, cambios, gates.

## Regla de composición de conocimiento
- Prompt de delegación = (manual de prompts) + (dominio de la tarea delegada) + (restricciones runtime/scope).
- No emitir prompt “genérico” si existe rama experta aplicable.
- Si una tarea toca dos o más dominios, documentar mini-síntesis de criterios usados en el handoff/report.

## Regla de autonomía
- No pedir permiso para crecer ramas cuando mejore desempeño/confiabilidad.
- Sí escalar al owner solo para riesgos altos, irreversibles o decisiones estratégicas.

## Anti-fallo
- Si no hay certeza: `GAP/NO_VERIFICADO`.
- No cerrar tarea crítica sin anclaje en sistema.

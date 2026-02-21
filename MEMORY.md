# MEMORY.md

Memoria curada de largo plazo (main session).

## Decision scope
Controla el enrutamiento de memoria estable (qué rama consultar), no el detalle episódico completo.

## Propósito
Este archivo es la puerta de entrada de memoria estable para decisiones y continuidad.
No reemplaza los mapas detallados; los orquesta.

## Dónde está la memoria real

### Núcleo MemoryOS
- `memory/00_INDEX.md`
- `memory/01_PROFILE_CURRENT.md`
- `memory/02_PRINCIPLES_CURRENT.md`
- `memory/03_PREFERENCES.ndjson`
- `memory/04_PROJECTS.ndjson`
- `memory/05_DECISIONS.ndjson`
- `memory/06_TIMELINE.ndjson`

### Perfil (quién es Mateo)
- `memory/profile/00_INDEX.md`
- `memory/profile/*`

### Visión compartida (brújula canónica)
- `memory/vision/00_INDEX.md`
- `memory/vision/*`

### Aprendizaje operativo OTTO
- `brain/domains/personal_ops/00_INDEX.md`
- `brain/domains/personal_ops/*`

### Conocimiento profesional fase actual (SG)
- `brain/domains/sg_acabados/00_INDEX.md`
- `brain/domains/sg_acabados/*`

## Regla de uso
1. Consultar primero índices (`00_INDEX.md`).
2. Leer solo ramas necesarias para la tarea (anti-overread).
3. Toda directriz crítica aceptada debe quedar persistida en artefactos del sistema (docs/policy/code), no solo en conversación.
4. Evitar duplicación: `MEMORY.md` resume y enruta; el detalle vive en ramas canónicas.

## Inputs/Outputs runtime
- Inputs: consultas sobre continuidad, decisiones, perfil, visión, aprendizajes operativos.
- Outputs: rutas canónicas precisas a ramas de memoria/brain para respuesta y ejecución.

## Nota de seguridad
Cargar `MEMORY.md` solo en sesión principal con owner (no en contextos compartidos/grupos).

## Update trigger
Actualizar cuando cambie la topología de memoria (nuevas ramas canónicas, cambios de fase o de dominio prioritario).

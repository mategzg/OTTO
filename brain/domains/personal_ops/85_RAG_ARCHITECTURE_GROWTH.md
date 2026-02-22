# 85 — RAG Architecture Growth Responsibility

## Mandato operativo continuo
La optimización de RAG es responsabilidad permanente del sistema, no trabajo puntual.

## Reglas
1. Integrar conocimiento nuevo en ramas canónicas por dominio.
2. Evitar sinks aislados tipo `*_CAPABILITY_EXTRACT_*` como destino primario.
3. Mantener límites PROFILE vs BRAIN estrictos.
4. Aplicar **raw-first bucketization** antes de cualquier síntesis.
5. Actualizar índices/mapas de navegación en el mismo ciclo de promoción.
6. Ejecutar checks de routing/retrieval tras cambios estructurales.
7. Operar proactivamente ante nuevos exports (sin esperar comandos), con reporte de evidencia.

## Routing canónico mínimo
- Profesional/empresa -> `brain/domains/sg_acabados/*`
- Personal development / psychology / philosophy / neuroscience / health -> `brain/domains/personal_ops/35_*` y ramas relacionadas
- Perfil del owner -> `memory/profile/*` y `memory/*.ndjson`

## Definición de done para cambios de arquitectura
- Conocimiento redistribuido en ramas canónicas.
- Índices actualizados (`00_INDEX` relevantes + mapa central si aplica).
- Pruebas/checks de retrieval/routing en verde.
- Evidencia y commit hash reportados.

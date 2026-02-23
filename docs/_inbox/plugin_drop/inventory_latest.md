# Plugin Drop Inventory (latest)

Encontrados en `docs/_inbox/plugin_drop`:

- customer-support (1.0.0)
- data (1.0.0)
- enterprise-search (1.0.0)
- finance (1.0.0)
- legal (1.0.0)
- marketing (1.0.0)
- product-management (1.0.0)
- productivity (1.0.0)
- sales (1.0.0)

Resumen técnico:
- Total plugins: **9**
- MCP servers únicos detectados: **28**
- Cada plugin incluye: `README.md`, `CONNECTORS.md`, `.mcp.json`
- Se detectaron archivos `:Zone.Identifier` (metadata Windows), no funcionales.

## Siguiente paso de implementación (OTTO)
1. Normalizar paquete (limpiar `:Zone.Identifier`).
2. Construir matriz plugin -> capacidades SG/OTTO.
3. Definir política de uso por criticidad (P0/P1 sin coder autónomo, P2 delegable).
4. Activar conectores que tengan credenciales disponibles.
5. Ejecutar smoke tests NL-first por plugin clave (sales, customer-support, finance, legal).
6. Dejar reporte final de operatividad (OK / GAP / requiere credenciales).

# Cowork Plugins Activation Plan (adaptado OTTO/SG)

Actualizado: 2026-02-23T00:06:08Z

## Estado global
- Plugins importados: **9**
- Modo actual: **playbook listo + conectores pendientes**
- Política: NL-first, P0/P1 sin coder autónomo, P2 delegable con handoff.

## Priorización de activación
- **customer-support** (high) -> sg_ops | estado: GAP_REQUIRES_CONNECTORS
- **data** (medium) -> knowledge_retrieval | estado: GAP_REQUIRES_CONNECTORS
- **enterprise-search** (medium) -> knowledge_retrieval | estado: GAP_REQUIRES_CONNECTORS
- **finance** (high) -> sg_governance | estado: GAP_REQUIRES_CONNECTORS
- **legal** (high) -> sg_governance | estado: GAP_REQUIRES_CONNECTORS
- **marketing** (high) -> sg_ops | estado: GAP_REQUIRES_CONNECTORS
- **product-management** (medium) -> execution_system | estado: GAP_REQUIRES_CONNECTORS
- **productivity** (medium) -> execution_system | estado: GAP_REQUIRES_CONNECTORS
- **sales** (high) -> sg_ops | estado: GAP_REQUIRES_CONNECTORS

## Qué queda operativo ya (sin credenciales)
- Uso de marcos/plantillas de comandos y skills desde README/CONNECTORS.
- Routing conceptual por dominio (sales/support/finance/legal/etc).
- Preparado para activación NL: usuario habla normal, OTTO selecciona playbook.

## Qué falta para modo supercharged
- Autenticación de MCP connectors por plugin (tokens/OAuth).
- Pruebas por conector crítico (al menos 1 caso real por plugin high).
- Matriz final OK/GAP por conector y canal.

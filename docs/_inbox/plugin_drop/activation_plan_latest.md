# Cowork Plugins Activation Plan (adaptado OTTO/SG)

Actualizado: 2026-02-23T00:07:54Z

## Estado global
- Plugins importados: **9**
- MCP servers únicos detectados: **28**
- Modo actual: **playbook listo + conectores pendientes**
- Política: NL-first, P0/P1 sin coder autónomo, P2 delegable con handoff.

## Priorización
- **customer-support** (high) -> sg_ops | estado: GAP_REQUIRES_CONNECTORS
- **data** (medium) -> knowledge_retrieval | estado: GAP_REQUIRES_CONNECTORS
- **enterprise-search** (medium) -> knowledge_retrieval | estado: GAP_REQUIRES_CONNECTORS
- **finance** (high) -> sg_governance | estado: GAP_REQUIRES_CONNECTORS
- **legal** (high) -> sg_governance | estado: GAP_REQUIRES_CONNECTORS
- **marketing** (high) -> sg_ops | estado: GAP_REQUIRES_CONNECTORS
- **product-management** (medium) -> execution_system | estado: GAP_REQUIRES_CONNECTORS
- **productivity** (medium) -> execution_system | estado: GAP_REQUIRES_CONNECTORS
- **sales** (high) -> sg_ops | estado: GAP_REQUIRES_CONNECTORS

## Próximo paso
- Activar conectores por prioridad: sales -> customer-support -> finance/legal.
- Correr smoke test NL por plugin y registrar OK/GAP.

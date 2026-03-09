# Plugin Connector Activation Matrix (Fase 4)

Actualizado: 2026-02-23T18:13:24Z

## Prioridad de activación (credenciales)
- Ordenado por prioridad de negocio + deuda de autenticación.

- sales [high] | connectors=9 | auth_needed=7 | missing_url=0 | ok200=0
- customer-support [high] | connectors=7 | auth_needed=6 | missing_url=0 | ok200=0
- marketing [high] | connectors=9 | auth_needed=6 | missing_url=0 | ok200=1
- legal [high] | connectors=5 | auth_needed=4 | missing_url=0 | ok200=0
- finance [high] | connectors=5 | auth_needed=1 | missing_url=2 | ok200=0
- product-management [medium] | connectors=12 | auth_needed=11 | missing_url=0 | ok200=0
- productivity [medium] | connectors=8 | auth_needed=7 | missing_url=0 | ok200=0
- enterprise-search [medium] | connectors=6 | auth_needed=5 | missing_url=0 | ok200=0
- data [medium] | connectors=6 | auth_needed=3 | missing_url=2 | ok200=0

## Lote 1 recomendado (inmediato)
- sales
- customer-support
- finance

## Lote 2 recomendado
- legal
- marketing
- productivity

## Lote 3 recomendado
- product-management
- data
- enterprise-search

## Criterio PASS/FAIL por plugin
- PASS: auth_needed=0 y missing_url=0
- FAIL: auth_needed>0 o missing_url>0 (queda OK_PARTIAL en runtime)

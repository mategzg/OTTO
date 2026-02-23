# Dashboard OTTO v1 — Data Contracts

## Endpoint principal
`GET /api/dashboard-v1`

```json
{
  "topbar": {
    "otto_status": "available|busy|blocked",
    "active_delegations_total": 3,
    "active_subagents": 2,
    "active_coders": 1,
    "delegations": [
      {
        "label": "Ingest SG lote 3",
        "type": "subagent|coder",
        "progress": 65,
        "status": "running|blocked|done"
      }
    ]
  },
  "sg": {
    "cash_receivable_7d": 24500,
    "overdue_count": 4,
    "cash_status": "green|amber|red",

    "hot_pipeline_value": 198000,
    "hot_opportunities_count": 6,
    "pipeline_status": "green|amber|red",

    "ops_risk_count": 3,
    "top_risk_label": "Instalación Norte",
    "risk_status": "green|amber|red",

    "next_best_decision": "Prioriza cobranza de 2 cuentas para proteger caja esta semana.",
    "next_best_decision_impact": "Alto"
  },
  "personal": {
    "top3": ["Llamar cuenta A", "Cerrar propuesta B", "Revisar agenda"],

    "critical_count": 5,
    "due_today_count": 2,
    "critical_status": "green|amber|red",

    "next_decision": "Definir proveedor para módulo de reportes",
    "next_decision_eta": "Hoy 17:30",

    "next_action": "Bloquear 45 min para cierre de propuestas",
    "next_action_impact": "Alto"
  },
  "activity": [
    {
      "time": "09:41",
      "label": "Normalizando backlog SG",
      "status": "running|done|blocked",
      "type": "subagent|coder|system"
    }
  ]
}
```

## Reglas de contrato
- `progress` en rango 0–100.
- `activity` debe devolver máx. 5 eventos para UI v1.
- Si falta un bloque, backend entrega fallback válido (no nulls rotos).
- Impacto permitido: `Alto|Medio|Bajo`.
- Semáforos permitidos: `green|amber|red`.

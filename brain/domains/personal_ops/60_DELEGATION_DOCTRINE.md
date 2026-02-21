# 60 — Delegation Doctrine

- Delegar por defecto tareas largas/complejas para preservar disponibilidad del agente principal.
- Toda delegación debe tener: scope, gates, output schema y HANDOFF_FILE obligatorio.
- Criterio de cierre: sin handoff válido no hay DONE.
- Diagnóstico de fallos de delegación: pairing/auth -> prompt contract -> state lock -> fallback plan.
- Patrón E2E: emitir -> ejecutar -> handoff -> verificar -> responder al owner con evidencia.
- Post-mortem rápido: cada incidente de delegación se convierte en regla o playbook para evitar recaídas.

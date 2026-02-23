export default function handler(req, res) {
  if (req.method !== 'GET') {
    res.status(405).json({ error: 'method_not_allowed' });
    return;
  }

  res.setHeader('Cache-Control', 'no-store');
  res.status(200).json({
    topbar: {
      otto_status: 'available',
      active_delegations_total: 1,
      active_subagents: 1,
      active_coders: 0,
      delegations: [
        { label: 'Dashboard v1 rollout', type: 'subagent', progress: 72, status: 'running' },
      ],
    },
    sg: {
      cash_receivable_7d: 24500,
      overdue_count: 4,
      cash_status: 'amber',
      hot_pipeline_value: 198000,
      hot_opportunities_count: 6,
      pipeline_status: 'green',
      ops_risk_count: 2,
      top_risk_label: 'Instalación Norte',
      risk_status: 'amber',
      next_best_decision: 'Prioriza cobranza de 2 cuentas para proteger caja esta semana.',
      next_best_decision_impact: 'Alto',
    },
    personal: {
      top3: ['Llamar cuenta A', 'Cerrar propuesta B', 'Revisar agenda de mañana'],
      critical_count: 3,
      due_today_count: 1,
      critical_status: 'amber',
      next_decision: 'Definir proveedor para módulo de reportes',
      next_decision_eta: 'Hoy 17:30',
      next_action: 'Bloquear 45 min para cierre de propuestas',
      next_action_impact: 'Alto',
    },
    activity: [
      { time: '09:41', label: 'Normalizando backlog SG', status: 'running', type: 'subagent' },
      { time: '09:37', label: 'Cargado spec v1 dashboard', status: 'done', type: 'system' },
      { time: '09:30', label: 'Ajuste de semáforos y CTAs', status: 'done', type: 'coder' },
    ],
  });
}

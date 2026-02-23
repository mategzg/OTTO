const FALLBACK = {
  topbar: {
    otto_status: 'available',
    active_delegations_total: 0,
    active_subagents: 0,
    active_coders: 0,
    delegations: [],
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
    { time: '-', label: 'Sin actividad live conectada aún', status: 'done', type: 'system' },
  ],
};

export async function getDashboardPayload() {
  const sourceUrl = process.env.OTTO_DASHBOARD_URL;
  if (!sourceUrl) return FALLBACK;

  try {
    const headers = {};
    if (process.env.OTTO_DASHBOARD_TOKEN) {
      headers.Authorization = `Bearer ${process.env.OTTO_DASHBOARD_TOKEN}`;
    }

    const response = await fetch(sourceUrl, {
      method: 'GET',
      headers,
      cache: 'no-store',
    });

    if (!response.ok) return FALLBACK;
    const data = await response.json();
    if (!data || typeof data !== 'object') return FALLBACK;
    return data;
  } catch {
    return FALLBACK;
  }
}

export async function forwardAction(action) {
  const base = process.env.OTTO_ACTIONS_BASE_URL;
  if (!base) return { ok: true, mode: 'local_stub', action };

  const url = `${base.replace(/\/$/, '')}/api/actions/${action}`;
  try {
    const headers = { 'Content-Type': 'application/json' };
    if (process.env.OTTO_ACTIONS_TOKEN) {
      headers.Authorization = `Bearer ${process.env.OTTO_ACTIONS_TOKEN}`;
    }

    const response = await fetch(url, { method: 'POST', headers, body: '{}' });
    if (!response.ok) return { ok: false, mode: 'forward_failed', status: response.status, action };
    return { ok: true, mode: 'forwarded', action };
  } catch {
    return { ok: false, mode: 'forward_error', action };
  }
}

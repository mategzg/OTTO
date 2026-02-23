const POLL_MS = 8000;

const el = {
  ottoPill: document.getElementById('otto-pill'),
  delegationTotal: document.getElementById('delegation-total'),
  chipSubagent: document.getElementById('chip-subagent'),
  chipCoder: document.getElementById('chip-coder'),

  sgCash: document.getElementById('sg-cash'),
  sgOverdue: document.getElementById('sg-overdue'),
  sgPipeline: document.getElementById('sg-pipeline'),
  sgHotCount: document.getElementById('sg-hot-count'),
  sgRisk: document.getElementById('sg-risk'),
  sgTopRisk: document.getElementById('sg-top-risk'),
  sgNextDecision: document.getElementById('sg-next-decision'),
  sgNextImpact: document.getElementById('sg-next-impact'),

  personalTop3: document.getElementById('personal-top3'),
  personalCritical: document.getElementById('personal-critical'),
  personalDue: document.getElementById('personal-due'),
  personalNextDecision: document.getElementById('personal-next-decision'),
  personalNextAction: document.getElementById('personal-next-action'),
  personalNextImpact: document.getElementById('personal-next-impact'),

  activityDrawer: document.getElementById('activity-drawer'),
  activityList: document.getElementById('activity-list'),

  btnRefresh: document.getElementById('btn-refresh'),
  btnActivity: document.getElementById('btn-activity'),
  btnCloseActivity: document.getElementById('btn-close-activity'),
};

function setPill(status) {
  const map = {
    available: { text: '🟢 Disponible', color: '#10b981' },
    busy: { text: '🟡 Ocupado', color: '#f59e0b' },
    blocked: { text: '🔴 Bloqueado', color: '#ef4444' },
  };
  const cfg = map[String(status || '').toLowerCase()] || map.available;
  el.ottoPill.textContent = cfg.text;
  el.ottoPill.style.background = cfg.color;
}

function money(n) {
  const v = Number(n || 0);
  return `S/ ${v.toLocaleString('es-PE')}`;
}

function render(data) {
  const d = data || {};
  const top = d.topbar || {};
  const sg = d.sg || {};
  const personal = d.personal || {};

  setPill(top.otto_status);
  el.delegationTotal.textContent = `${top.active_delegations_total || 0} activas`;
  el.chipSubagent.textContent = `Subagente x${top.active_subagents || 0}`;
  el.chipCoder.textContent = `Coder x${top.active_coders || 0}`;

  el.sgCash.textContent = money(sg.cash_receivable_7d);
  el.sgOverdue.textContent = `${sg.overdue_count || 0} vencidas`;
  el.sgPipeline.textContent = money(sg.hot_pipeline_value);
  el.sgHotCount.textContent = `${sg.hot_opportunities_count || 0} oportunidades calientes`;
  el.sgRisk.textContent = `${sg.ops_risk_count || 0} frentes`;
  el.sgTopRisk.textContent = sg.top_risk_label || 'Sin riesgo crítico';
  el.sgNextDecision.textContent = sg.next_best_decision || 'Sin recomendación';
  el.sgNextImpact.textContent = `Impacto: ${sg.next_best_decision_impact || '-'}`;

  el.personalTop3.innerHTML = '';
  const top3 = Array.isArray(personal.top3) && personal.top3.length ? personal.top3 : ['Sin prioridades cargadas'];
  top3.slice(0, 3).forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    el.personalTop3.appendChild(li);
  });

  el.personalCritical.textContent = `${personal.critical_count || 0}`;
  el.personalDue.textContent = `${personal.due_today_count || 0} vencen hoy`;
  el.personalNextDecision.textContent = personal.next_decision || 'Sin decisión pendiente';
  el.personalNextAction.textContent = personal.next_action || 'Sin recomendación';
  el.personalNextImpact.textContent = `Impacto: ${personal.next_action_impact || '-'}`;

  el.activityList.innerHTML = '';
  const items = Array.isArray(d.activity) ? d.activity : [];
  if (!items.length) {
    const li = document.createElement('li');
    li.textContent = 'Sin actividad reciente';
    el.activityList.appendChild(li);
  } else {
    items.forEach((item) => {
      const li = document.createElement('li');
      li.textContent = `${item.time || '-'} · ${item.label || '-'} (${item.status || '-'})`;
      el.activityList.appendChild(li);
    });
  }
}

async function refresh() {
  const response = await fetch('/api/dashboard-v1', { cache: 'no-store' });
  if (!response.ok) throw new Error('No se pudo cargar dashboard');
  const data = await response.json();
  render(data);
}

document.querySelectorAll('.tab').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

el.btnActivity.addEventListener('click', () => el.activityDrawer.classList.remove('hidden'));
el.btnCloseActivity.addEventListener('click', () => el.activityDrawer.classList.add('hidden'));
el.btnRefresh.addEventListener('click', () => refresh().catch(console.error));

refresh().catch(console.error);
setInterval(() => refresh().catch(console.error), POLL_MS);

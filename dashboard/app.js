const POLL_MS = 8000;

const el = {
  ottoPill: document.getElementById('otto-pill'),
  delegationTotal: document.getElementById('delegation-total'),
  chipSubagent: document.getElementById('chip-subagent'),
  chipCoder: document.getElementById('chip-coder'),
  delegationList: document.getElementById('delegation-list'),

  sgCash: document.getElementById('sg-cash'),
  sgOverdue: document.getElementById('sg-overdue'),
  sgPipeline: document.getElementById('sg-pipeline'),
  sgHotCount: document.getElementById('sg-hot-count'),
  sgRisk: document.getElementById('sg-risk'),
  sgTopRisk: document.getElementById('sg-top-risk'),
  sgNextDecision: document.getElementById('sg-next-decision'),
  sgNextImpact: document.getElementById('sg-next-impact'),
  sgCashLight: document.getElementById('sg-cash-light'),
  sgPipelineLight: document.getElementById('sg-pipeline-light'),
  sgRiskLight: document.getElementById('sg-risk-light'),

  personalTop3: document.getElementById('personal-top3'),
  personalCritical: document.getElementById('personal-critical'),
  personalDue: document.getElementById('personal-due'),
  personalNextDecision: document.getElementById('personal-next-decision'),
  personalNextEta: document.getElementById('personal-next-eta'),
  personalNextAction: document.getElementById('personal-next-action'),
  personalNextImpact: document.getElementById('personal-next-impact'),
  personalCriticalLight: document.getElementById('personal-critical-light'),

  activityDrawer: document.getElementById('activity-drawer'),
  activityList: document.getElementById('activity-list'),

  btnRefresh: document.getElementById('btn-refresh'),
  btnActivity: document.getElementById('btn-activity'),
  btnPause: document.getElementById('btn-pause'),
  btnCloseActivity: document.getElementById('btn-close-activity'),
  btnSgExec: document.getElementById('btn-sg-exec'),
  btnSgAlt: document.getElementById('btn-sg-alt'),
  btnPersonalExec: document.getElementById('btn-personal-exec'),

  sgCashTrend: document.getElementById('sg-cash-trend'),
  sgPipelineTrend: document.getElementById('sg-pipeline-trend'),

  syncBadge: document.getElementById('sync-badge'),
  dataMode: document.getElementById('data-mode'),
  lastUpdated: document.getElementById('last-updated'),
  toast: document.getElementById('toast'),
};

let toastTimer = null;

function showToast(text, kind = 'info') {
  if (!el.toast) return;
  el.toast.textContent = text;
  el.toast.classList.remove('hidden');
  el.toast.style.borderColor = kind === 'error' ? 'rgba(239,68,68,.7)' : 'rgba(59,130,246,.55)';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.toast.classList.add('hidden'), 2200);
}

function setPill(status, mode = 'live') {
  if (mode !== 'live') {
    el.ottoPill.textContent = '🟠 Demo (sin live bridge)';
    el.ottoPill.style.background = '#f59e0b';
    return;
  }
  const map = {
    available: { text: '🟢 Disponible', color: '#10b981' },
    busy: { text: '🟡 Ejecutando...', color: '#f59e0b' },
    blocked: { text: '🔴 Bloqueado', color: '#ef4444' },
  };
  const cfg = map[String(status || '').toLowerCase()] || map.available;
  el.ottoPill.textContent = cfg.text;
  el.ottoPill.style.background = cfg.color;
}

function setLight(node, status) {
  node.classList.remove('green', 'amber', 'red');
  const s = String(status || '').toLowerCase();
  if (s === 'amber') node.classList.add('amber');
  else if (s === 'red') node.classList.add('red');
  else node.classList.add('green');
}

function money(n) {
  return `S/ ${Number(n || 0).toLocaleString('es-PE')}`;
}

function pct(v) {
  const n = Number(v);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function renderDelegations(items) {
  el.delegationList.innerHTML = '';
  const list = Array.isArray(items) ? items.slice(0, 3) : [];
  if (!list.length) {
    el.delegationList.innerHTML = '<p class="sub">Sin delegaciones activas</p>';
    return;
  }

  list.forEach((d) => {
    const row = document.createElement('div');
    row.className = 'd-row';

    const label = document.createElement('div');
    label.className = 'd-label';
    label.textContent = `${d.type === 'coder' ? 'Coder' : 'Subagente'} · ${d.label || 'Tarea'}`;

    const barWrap = document.createElement('div');
    barWrap.className = 'bar-wrap';
    const bar = document.createElement('div');
    bar.className = 'bar';
    bar.style.width = `${pct(d.progress)}%`;
    barWrap.appendChild(bar);

    row.appendChild(label);
    row.appendChild(barWrap);
    el.delegationList.appendChild(row);
  });
}

function renderActivity(items) {
  el.activityList.innerHTML = '';
  const list = Array.isArray(items) ? items.slice(0, 5) : [];

  if (!list.length) {
    el.activityList.innerHTML = '<li class="event"><span class="sub">Sin actividad reciente</span></li>';
    return;
  }

  list.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'event';

    const status = String(item.status || 'done').toLowerCase();
    const badgeClass = status === 'blocked' ? 'red' : status === 'running' ? 'amber' : 'green';

    li.innerHTML = `
      <div class="event-top">
        <strong>${item.time || '-'}</strong>
        <span class="chip ${badgeClass}">${status}</span>
        <span class="chip">${item.type || 'system'}</span>
      </div>
      <p>${item.label || '-'}</p>
    `;
    el.activityList.appendChild(li);
  });
}

function setSync(status, text) {
  el.syncBadge.classList.remove('ok', 'warn', 'err');
  if (status === 'ok') el.syncBadge.classList.add('ok');
  if (status === 'warn') el.syncBadge.classList.add('warn');
  if (status === 'err') el.syncBadge.classList.add('err');
  el.syncBadge.textContent = text;
}

function renderTrend(node, level = 0.5) {
  if (!node) return;
  const v = Math.max(0.05, Math.min(0.95, Number(level) || 0.5));
  const line = document.createElement('div');
  line.className = 'trend-line';
  line.style.opacity = String(0.55 + (v * 0.45));
  node.innerHTML = '';
  node.appendChild(line);
}

function render(data) {
  const d = data || {};
  const top = d.topbar || {};
  const sg = d.sg || {};
  const personal = d.personal || {};

  const meta = d.meta || {};
  setPill(top.otto_status, meta.mode);
  el.delegationTotal.textContent = `${top.active_delegations_total || 0} activas`;
  el.chipSubagent.textContent = `Subagente x${top.active_subagents || 0}`;
  el.chipCoder.textContent = `Coder x${top.active_coders || 0}`;
  renderDelegations(top.delegations || []);

  setLight(el.sgCashLight, sg.cash_status);
  setLight(el.sgPipelineLight, sg.pipeline_status);
  setLight(el.sgRiskLight, sg.risk_status);

  el.sgCash.textContent = `${money(sg.cash_receivable_7d)} por cobrar (7 días)`;
  renderTrend(el.sgCashTrend, (Number(sg.cash_receivable_7d || 0) % 100) / 100);
  el.sgOverdue.textContent = `${sg.overdue_count || 0} vencidas`;
  el.sgPipeline.textContent = `${money(sg.hot_pipeline_value)} en pipeline caliente`;
  renderTrend(el.sgPipelineTrend, (Number(sg.hot_pipeline_value || 0) % 100) / 100);
  el.sgHotCount.textContent = `${sg.hot_opportunities_count || 0} oportunidades esta semana`;
  el.sgRisk.textContent = `${sg.ops_risk_count || 0} frentes en ámbar/rojo`;
  el.sgTopRisk.textContent = `Top riesgo: ${sg.top_risk_label || 'sin riesgo crítico'}`;
  el.sgNextDecision.textContent = sg.next_best_decision || 'Sin recomendación';
  el.sgNextImpact.textContent = `Impacto: ${sg.next_best_decision_impact || '-'}`;

  setLight(el.personalCriticalLight, personal.critical_status);
  el.personalTop3.innerHTML = '';
  const top3 = Array.isArray(personal.top3) && personal.top3.length ? personal.top3.slice(0, 3) : ['Sin prioridades cargadas'];
  top3.forEach((item) => {
    const li = document.createElement('li');
    li.innerHTML = `<label><input type="checkbox" /> <span>${item}</span></label>`;
    el.personalTop3.appendChild(li);
  });

  el.personalCritical.textContent = `${personal.critical_count || 0} críticos`;
  el.personalDue.textContent = `${personal.due_today_count || 0} vencen hoy`;
  el.personalNextDecision.textContent = personal.next_decision || 'Sin decisión pendiente';
  el.personalNextEta.textContent = `Sugerido: ${personal.next_decision_eta || '-'}`;
  el.personalNextAction.textContent = personal.next_action || 'Sin recomendación';
  el.personalNextImpact.textContent = `Impacto: ${personal.next_action_impact || '-'}`;

  renderActivity(d.activity || []);

  const channels = meta.channels || {};
  const tg = Number(channels.telegram || 0);
  const dc = Number(channels.discord || 0);
  const wa = Number(channels.whatsapp || 0);
  el.dataMode.textContent = `Modo: ${meta.mode || 'unknown'} · TG:${tg} DC:${dc} WA:${wa}`;
  el.lastUpdated.textContent = `Actualizado: ${meta.last_updated || '-'}`;
  setSync(meta.mode === 'live' ? 'ok' : 'warn', meta.mode === 'live' ? 'LIVE' : 'DEMO');
}

async function refresh(showFeedback = false) {
  setSync('warn', 'sync...');
  const response = await fetch('/api/dashboard-v1', { cache: 'no-store' });
  if (!response.ok) {
    setSync('err', 'offline');
    if (showFeedback) showToast('No se pudo sincronizar', 'error');
    throw new Error('No se pudo cargar dashboard');
  }
  render(await response.json());
  if (showFeedback) showToast('Dashboard al día');
}

async function runAction(path, successText, trigger) {
  if (trigger) trigger.disabled = true;
  setPill('busy', 'live');
  const response = await fetch(path, { method: 'POST' });
  if (!response.ok) {
    showToast('No se pudo ejecutar la acción', 'error');
    if (trigger) trigger.disabled = false;
    return;
  }
  showToast(successText);
  await refresh();
  if (trigger) trigger.disabled = false;
}

function getActiveTab() {
  const active = document.querySelector('.tab.active');
  return active ? active.dataset.tab : 'sg';
}

document.querySelectorAll('.tab').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    if (el.mBtnPrimary) el.mBtnPrimary.textContent = btn.dataset.tab === 'personal' ? 'Resolver Personal' : 'Ejecutar SG';
  });
});

el.btnActivity?.addEventListener('click', () => el.activityDrawer.classList.remove('hidden'));
el.btnCloseActivity?.addEventListener('click', () => el.activityDrawer.classList.add('hidden'));
el.btnRefresh?.addEventListener('click', () => runAction('/api/actions/refresh', 'Dashboard actualizado.', el.btnRefresh).catch(console.error));
el.btnPause?.addEventListener('click', () => {
  if (window.confirm('¿Pausar delegación ahora?')) {
    runAction('/api/actions/pause-delegation', 'Delegación pausada.', el.btnPause).catch(console.error);
  }
});
el.btnSgExec?.addEventListener('click', () => runAction('/api/actions/execute-sg', 'Decisión SG enviada a ejecución.', el.btnSgExec).catch(console.error));
el.btnSgAlt?.addEventListener('click', () => runAction('/api/actions/sg-alternative', 'Alternativa SG cargada.', el.btnSgAlt).catch(console.error));
el.btnPersonalExec?.addEventListener('click', () => runAction('/api/actions/execute-personal', 'Acción personal enviada a ejecución.', el.btnPersonalExec).catch(console.error));


refresh().catch(console.error);
setInterval(() => refresh().catch(console.error), POLL_MS);

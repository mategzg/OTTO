'use strict';

const POLL_MS = 5000;
const DOCS_LIMIT = 120;

const statusPill = document.getElementById('status-pill');
const statusTask = document.getElementById('status-task');
const statusRaw = document.getElementById('status-raw');
const kanbanRaw = document.getElementById('kanban-raw');
const activityList = document.getElementById('activity-list');
const docsList = document.getElementById('docs-list');
const docsHint = document.getElementById('docs-hint');
const ledgerList = document.getElementById('ledger-list');
const ledgerHint = document.getElementById('ledger-hint');

const statusColors = {
  idle: 'var(--idle)',
  thinking: 'var(--thinking)',
  working: 'var(--working)',
  offline: 'var(--offline)'
};

async function fetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function renderStatus(status) {
  const normalized = String(status.status || 'idle').toLowerCase();
  statusPill.textContent = normalized;
  statusPill.style.background = statusColors[normalized] || 'var(--offline)';
  statusTask.textContent = status.task ? `Tarea actual: ${status.task}` : 'sin tarea activa';
  statusRaw.textContent = pretty(status);
}

function renderKanban(kanban) {
  kanbanRaw.textContent = pretty(kanban);
}

function humanActivity(entry) {
  const ts = entry.ts || 'n/a';
  const event = entry.event || 'event';
  let payload = entry.payload || {};
  if (!entry.payload && entry.detail) {
    try {
      payload = JSON.parse(entry.detail);
    } catch {
      payload = {};
    }
  }

  if (event === 'set_status') {
    return `${ts} -> status=${payload.status || ''} task=${payload.task || ''}`;
  }
  if (event === 'add_task') {
    return `${ts} -> add ${payload.id || ''} [${payload.priority || ''}] ${payload.title || ''}`;
  }
  if (event === 'move_task') {
    return `${ts} -> move ${payload.task_id || ''}: ${payload.from || '?'} -> ${payload.to || '?'}`;
  }
  if (event === 'move_task_missing') {
    return `${ts} -> move missing ${payload.task_id || ''} -> ${payload.to || ''}`;
  }
  if (entry.detail) {
    return `${ts} -> ${event}: ${entry.detail}`;
  }
  return `${ts} -> ${event}`;
}

function renderActivity(items) {
  activityList.innerHTML = '';
  if (!items.length) {
    const li = document.createElement('li');
    li.textContent = '(sin actividad)';
    activityList.appendChild(li);
    return;
  }

  const ordered = [...items].reverse();
  for (const item of ordered) {
    const li = document.createElement('li');
    li.textContent = humanActivity(item);
    activityList.appendChild(li);
  }
}

function renderDocs(files) {
  docsList.innerHTML = '';
  const limited = files.slice(0, DOCS_LIMIT);

  for (const file of limited) {
    const li = document.createElement('li');
    li.textContent = `${file.path} (${file.size} bytes)`;
    docsList.appendChild(li);
  }

  docsHint.textContent = files.length > DOCS_LIMIT
    ? `Mostrando ${DOCS_LIMIT} de ${files.length} archivos`
    : `Mostrando ${files.length} archivos`;

  if (!files.length) {
    const li = document.createElement('li');
    li.textContent = '(sin archivos en docs/empresa)';
    docsList.appendChild(li);
  }
}

function renderLedger(items) {
  ledgerList.innerHTML = '';
  if (!items.length) {
    const li = document.createElement('li');
    li.textContent = '(sin items en ledger)';
    ledgerList.appendChild(li);
    ledgerHint.textContent = 'Agrega filas con scripts/append_ledger.py';
    return;
  }

  for (const item of items) {
    const li = document.createElement('li');
    if (item.table === 'licitaciones') {
      li.textContent = `[Licitaciones] ${item.fecha || ''} | ${item.fuente || ''} | ${item.keyword || ''} | ${item.archivo_doc || ''}`;
    } else {
      li.textContent = `[Leads] ${item.fecha || ''} | ${item.empresa || ''} | ${item.contacto || ''} | ${item.archivo_doc || ''}`;
    }
    ledgerList.appendChild(li);
  }
  ledgerHint.textContent = `Mostrando ${items.length} items`;
}

async function refresh() {
  try {
    const [status, kanban, activity, docs, ledger] = await Promise.all([
      fetchJson('/api/status'),
      fetchJson('/api/kanban'),
      fetchJson('/api/activity?tail=80'),
      fetchJson('/api/docs?path=docs/empresa'),
      fetchJson('/api/ledger?limit=20')
    ]);

    renderStatus(status);
    renderKanban(kanban);
    renderActivity(activity);
    renderDocs(docs);
    renderLedger(ledger);
  } catch (error) {
    statusTask.textContent = `Error: ${error.message}`;
  }
}

refresh();
setInterval(refresh, POLL_MS);

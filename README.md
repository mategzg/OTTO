# OTTO HQ v2 - Workspace real OpenClaw + HQ Klaus-style

Repositorio operativo para trazabilidad completa de misiones:

- status/kanban/logs integrados
- dashboard local
- delegacion inteligente (Coder CLI + Jack Web)
- B1/B2 bajo demanda (no automaticos)
- compatibilidad WSL + Windows

## Principios V2

1. **PLAN FIRST**: mision no trivial => plan en `plans/` antes de ejecutar.
2. **Fail-soft**: si falta integracion externa, devolver `needs_input`, registrar y continuar.
3. **Seguridad**: secretos solo por env vars/.env, nunca en logs.
4. **Determinismo**: JSON estable y listas ordenadas.

## Estructura clave

- `state/` estado y kanban
- `logs/activity.ndjson` actividad append-only
- `docs/empresa/` artefactos SG, ledger, runbooks, indices
- `dropzone/` handoff manual para delegacion
- `workers/` adaptadores de Coder y Jack
- `scripts/` utilitarios cross-platform

## Config OpenClaw (ejemplo)

Archivo ejemplo: `.openclaw/openclaw.json.example`

1. Copiar a `~/.openclaw/openclaw.json`
2. Ajustar `allowFrom` manualmente en tu entorno real.
3. Mantener `heartbeat.every: "0m"` en V2 (desactivado).

## Instalacion y pruebas

### WSL / Bash

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

O con script:

```bash
./scripts/bootstrap.sh
```

### Windows / PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

O con script:

```powershell
.\scripts\bootstrap.ps1
```

## Dashboard

### WSL / Bash

```bash
./scripts/run_dashboard.sh
```

### Windows / PowerShell

```powershell
.\scripts\run_dashboard.ps1
```

URL: `http://127.0.0.1:18999`

## Endpoints de verificacion rapida

```bash
curl -s http://127.0.0.1:18999/api/status
curl -s http://127.0.0.1:18999/api/kanban
curl -s 'http://127.0.0.1:18999/api/activity?tail=20'
curl -s 'http://127.0.0.1:18999/api/docs?path=docs/empresa'
curl -s 'http://127.0.0.1:18999/api/ledger?limit=10'
```

## Simular 1 mision (manual)

### WSL / Bash

```bash
.venv/bin/python otto_state.py set-status working --task "Mision B2 on-demand"
TASK_ID=$(.venv/bin/python - <<'PY'
import json,subprocess
out = subprocess.check_output([
    '.venv/bin/python','otto_state.py','add-task','--title','B2 on-demand','--detail','Prospeccion activa','--priority','high'
], text=True)
print(json.loads(out)['id'])
PY
)
.venv/bin/python otto_state.py move-task "$TASK_ID" --to in_progress
.venv/bin/python scripts/append_ledger.py leads --fecha 2026-02-11 --empresa "Empresa X" --contacto "contacto@x.com" --canal telegram --ciudad Lima --proyecto "Acabados" --archivo-doc "docs/empresa/leads/leads_2026-02-11.md"
.venv/bin/python index_docs.py
.venv/bin/python otto_state.py move-task "$TASK_ID" --to done
.venv/bin/python otto_state.py set-status idle --task "Online, listo"
```

### Windows / PowerShell

```powershell
.\.venv\Scripts\python.exe .\otto_state.py set-status working --task "Mision B2 on-demand"
$task = .\.venv\Scripts\python.exe .\otto_state.py add-task --title "B2 on-demand" --detail "Prospeccion activa" --priority high | ConvertFrom-Json
.\.venv\Scripts\python.exe .\otto_state.py move-task $task.id --to in_progress
.\.venv\Scripts\python.exe .\scripts\append_ledger.py leads --fecha 2026-02-11 --empresa "Empresa X" --contacto "contacto@x.com" --canal telegram --ciudad Lima --proyecto "Acabados" --archivo-doc "docs/empresa/leads/leads_2026-02-11.md"
.\.venv\Scripts\python.exe .\index_docs.py
.\.venv\Scripts\python.exe .\otto_state.py move-task $task.id --to done
.\.venv\Scripts\python.exe .\otto_state.py set-status idle --task "Online, listo"
```

## Delegacion Coder

- Config en `workers/coder_profiles.json`.
- Overrides opcionales: `CODER_PROFILE`, `CODER_CMD`, `CODER_ARGS`.
- Si no hay comando valido => fallback a `dropzone/prompts/` y espera resultado en `dropzone/results/`.
- Sin resultado en timeout => `needs_input`.

## Delegacion Jack (SG-only)

- Flujo manual/semi-automatizado documentado en `workers/jack_web.md`.
- Plantilla: `docs/empresa/templates/JACK_PROMPT_TEMPLATE.md`.
- Stub trazable: `workers/jack_stub.py` (genera request en `docs/_inbox/jack_requests/`).

## B1/B2 on-demand

- Runbooks:
  - `docs/empresa/runbooks/B1_LICITACIONES.md`
  - `docs/empresa/runbooks/B2_LEADS.md`
- Cierre obligatorio: actualizar `docs/empresa/ledger.md` + ejecutar `index_docs.py`.

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "[OTTO HQ] python3 no encontrado. Ejecuta scripts/bootstrap.sh" >&2
  exit 1
fi

"$PYTHON_BIN" otto_state.py set-status working --task "Demo mision V2"
TASK_JSON="$($PYTHON_BIN otto_state.py add-task --title "Mision demo V2" --detail "Task demo con ledger" --priority high)"
TASK_ID="$($PYTHON_BIN -c 'import json,sys; print(json.loads(sys.stdin.read())["id"])' <<< "$TASK_JSON")"

"$PYTHON_BIN" otto_state.py move-task "$TASK_ID" --to in_progress
"$PYTHON_BIN" scripts/append_ledger.py leads \
  --fecha "2026-02-11" \
  --empresa "Empresa Demo" \
  --contacto "operaciones@demo.com" \
  --canal "whatsapp" \
  --ciudad "Lima" \
  --proyecto "Acabados interior" \
  --archivo-doc "docs/empresa/leads/leads_2026-02-11.md"
"$PYTHON_BIN" index_docs.py
"$PYTHON_BIN" otto_state.py move-task "$TASK_ID" --to done
"$PYTHON_BIN" otto_state.py set-status idle --task "Online, listo"

echo "[OTTO HQ] Demo completada"

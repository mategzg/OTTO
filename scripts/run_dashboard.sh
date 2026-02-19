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

"$PYTHON_BIN" dashboard_server.py --host 127.0.0.1 --port 18999 --root "$ROOT"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[OTTO HQ] python3 no encontrado. Instala Python 3.10+" >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[OTTO HQ] Creando .venv"
  python3 -m venv .venv
fi

PYTHON_BIN="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  echo "[OTTO HQ] No se encontro $PYTHON_BIN" >&2
  exit 1
fi

echo "[OTTO HQ] Instalando dependencias"
"$PYTHON_BIN" -m pip install -r requirements.txt

echo "[OTTO HQ] Ejecutando tests"
"$PYTHON_BIN" -m pytest -q

echo "[OTTO HQ] Bootstrap completado"

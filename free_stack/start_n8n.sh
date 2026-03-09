#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$ROOT/state/n8n.log"
mkdir -p "$ROOT/state/n8n"
if ss -ltn | grep -q ':5678 '; then
  echo "n8n ya está corriendo"
  exit 0
fi
N8N_HOST=0.0.0.0 \
N8N_PORT=5678 \
N8N_EDITOR_BASE_URL=http://127.0.0.1:5678 \
N8N_USER_FOLDER="$ROOT/state/n8n" \
nohup n8n start > "$LOG" 2>&1 &
sleep 4
curl -fsS http://127.0.0.1:5678 >/dev/null
echo "n8n OK en http://127.0.0.1:5678"

#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QDRANT_BIN="$ROOT/tools/qdrant/qdrant"
LOG="$ROOT/state/qdrant.log"
mkdir -p "$ROOT/state/qdrant_storage"
if [[ ! -x "$QDRANT_BIN" ]]; then
  bash "$ROOT/free_stack/install_qdrant.sh"
fi
if pgrep -f "$QDRANT_BIN" >/dev/null 2>&1; then
  echo "Qdrant ya está corriendo"
  exit 0
fi
QDRANT__STORAGE__STORAGE_PATH="$ROOT/state/qdrant_storage" \
QDRANT__SERVICE__HTTP_PORT=6333 \
QDRANT__SERVICE__GRPC_PORT=6334 \
nohup "$QDRANT_BIN" > "$LOG" 2>&1 &
sleep 2
curl -fsS http://127.0.0.1:6333/healthz >/dev/null
echo "Qdrant OK en http://127.0.0.1:6333"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${DASHBOARD_BRIDGE_PORT:-18999}"
TOKEN="${DASHBOARD_BRIDGE_TOKEN:-}"

if [[ -z "$TOKEN" ]]; then
  echo "[bridge] ERROR: set DASHBOARD_BRIDGE_TOKEN"
  exit 1
fi

CLOUDFLARED_BIN="$ROOT/tools/bin/cloudflared"
if [[ ! -x "$CLOUDFLARED_BIN" ]]; then
  echo "[bridge] cloudflared not found at $CLOUDFLARED_BIN"
  exit 1
fi

echo "[bridge] starting dashboard_server on 127.0.0.1:$PORT"
DASHBOARD_BRIDGE_TOKEN="$TOKEN" python3 "$ROOT/dashboard_server.py" --host 127.0.0.1 --port "$PORT" > "$ROOT/state/dashboard_bridge_server.log" 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" >/dev/null 2>&1 || true
  kill "$TUNNEL_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "[bridge] starting cloudflared tunnel"
"$CLOUDFLARED_BIN" tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate > "$ROOT/state/dashboard_bridge_tunnel.log" 2>&1 &
TUNNEL_PID=$!

sleep 4
URL=$(grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' "$ROOT/state/dashboard_bridge_tunnel.log" | head -n 1 || true)
if [[ -n "$URL" ]]; then
  echo "[bridge] tunnel_url=$URL"
  echo "[bridge] set in Vercel:"
  echo "  OTTO_DASHBOARD_URL=$URL/api/dashboard-v1"
  echo "  OTTO_ACTIONS_BASE_URL=$URL"
  echo "  OTTO_DASHBOARD_TOKEN=<same token>"
  echo "  OTTO_ACTIONS_TOKEN=<same token>"
else
  echo "[bridge] tunnel URL not found yet; check state/dashboard_bridge_tunnel.log"
fi

wait "$TUNNEL_PID"

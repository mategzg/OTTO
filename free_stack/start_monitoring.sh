#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OBS="$ROOT/tools/observability"
CONF="$ROOT/free_stack/monitoring"
mkdir -p "$ROOT/state/monitoring"

if ! pgrep -f "$OBS/loki/loki" >/dev/null 2>&1; then
  nohup "$OBS/loki/loki" -config.file="$CONF/loki-config.yml" > "$ROOT/state/loki.log" 2>&1 &
fi
if ! pgrep -f "$OBS/promtail/promtail" >/dev/null 2>&1; then
  nohup "$OBS/promtail/promtail" -config.file="$CONF/promtail-config.yml" > "$ROOT/state/promtail.log" 2>&1 &
fi
if ! pgrep -f "$OBS/prometheus/prometheus" >/dev/null 2>&1; then
  nohup "$OBS/prometheus/prometheus" --config.file="$CONF/prometheus.yml" --storage.tsdb.path="$ROOT/state/monitoring/prometheus" > "$ROOT/state/prometheus.log" 2>&1 &
fi
if ! pgrep -f "$OBS/grafana/bin/grafana-server" >/dev/null 2>&1; then
  nohup "$OBS/grafana/bin/grafana-server" --homepath "$OBS/grafana" --config "$OBS/grafana/conf/defaults.ini" > "$ROOT/state/grafana.log" 2>&1 &
fi

sleep 5
curl -fsS http://127.0.0.1:9090/-/healthy >/dev/null
curl -fsS http://127.0.0.1:3100/ready >/dev/null
curl -fsS http://127.0.0.1:3000/api/health >/dev/null

echo "Monitoring OK: Prometheus 9090, Loki 3100, Grafana 3000"

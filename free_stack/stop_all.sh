#!/usr/bin/env bash
set -euo pipefail
pkill -f '/home/agente/otto-workspace/tools/qdrant/qdrant' || true
pkill -f 'n8n start' || true
pkill -f '/home/agente/otto-workspace/tools/observability/prometheus/prometheus' || true
pkill -f '/home/agente/otto-workspace/tools/observability/loki/loki' || true
pkill -f '/home/agente/otto-workspace/tools/observability/promtail/promtail' || true
pkill -f '/home/agente/otto-workspace/tools/observability/grafana/bin/grafana-server' || true
echo 'Servicios detenidos (si estaban corriendo).'

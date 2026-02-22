#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT/tools/observability"
mkdir -p "$BIN_DIR" "$ROOT/state/monitoring" "$ROOT/state/loki"

fetch_tar_gz() {
  local url="$1" outdir="$2"
  local tmp
  tmp=$(mktemp -d)
  curl -fsSL "$url" -o "$tmp/pkg.tar.gz"
  tar -xzf "$tmp/pkg.tar.gz" -C "$tmp"
  local first
  first=$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  mkdir -p "$outdir"
  cp -R "$first"/* "$outdir"/
  rm -rf "$tmp"
}

# Prometheus
if [[ ! -x "$BIN_DIR/prometheus/prometheus" ]]; then
  fetch_tar_gz "https://github.com/prometheus/prometheus/releases/download/v3.7.2/prometheus-3.7.2.linux-amd64.tar.gz" "$BIN_DIR/prometheus"
fi

# Loki
if [[ ! -x "$BIN_DIR/loki/loki" ]]; then
  mkdir -p "$BIN_DIR/loki"
  curl -fsSL "https://github.com/grafana/loki/releases/download/v3.5.4/loki-linux-amd64.zip" -o /tmp/loki.zip
  python3 - <<'PY'
import zipfile
z=zipfile.ZipFile('/tmp/loki.zip')
z.extractall('/tmp/loki')
PY
  mv /tmp/loki/loki-linux-amd64 "$BIN_DIR/loki/loki"
  chmod +x "$BIN_DIR/loki/loki"
  rm -rf /tmp/loki /tmp/loki.zip
fi

# Promtail
if [[ ! -x "$BIN_DIR/promtail/promtail" ]]; then
  mkdir -p "$BIN_DIR/promtail"
  curl -fsSL "https://github.com/grafana/loki/releases/download/v3.5.4/promtail-linux-amd64.zip" -o /tmp/promtail.zip
  python3 - <<'PY'
import zipfile
z=zipfile.ZipFile('/tmp/promtail.zip')
z.extractall('/tmp/promtail')
PY
  mv /tmp/promtail/promtail-linux-amd64 "$BIN_DIR/promtail/promtail"
  chmod +x "$BIN_DIR/promtail/promtail"
  rm -rf /tmp/promtail /tmp/promtail.zip
fi

# Grafana OSS
if [[ ! -x "$BIN_DIR/grafana/bin/grafana-server" ]]; then
  fetch_tar_gz "https://dl.grafana.com/oss/release/grafana-12.2.0.linux-amd64.tar.gz" "$BIN_DIR/grafana"
fi

echo "Phase 2 binaries installed"

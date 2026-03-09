#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/tools/qdrant"
cd "$ROOT/tools/qdrant"
URL="https://github.com/qdrant/qdrant/releases/download/v1.7.4/qdrant-x86_64-unknown-linux-gnu.tar.gz"
echo "Descargando Qdrant 1.7.4..."
curl -fsSL -o qdrant.tar.gz "$URL"
tar -xzf qdrant.tar.gz
chmod +x qdrant
echo "Qdrant instalado en $ROOT/tools/qdrant/qdrant"

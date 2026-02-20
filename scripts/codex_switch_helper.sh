#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/home/agente/otto-workspace}"
cd "$ROOT"

cmd="${2:-status}"

status() {
  echo "== OpenClaw model/auth status =="
  raw="$(openclaw --no-color models status --json)"
  RAW="$raw" python3 - <<'PY'
import json,os,re
raw=os.environ.get('RAW','')
m=re.search(r'\{[\s\S]*\}\s*$', raw)
if not m:
    raise SystemExit('Could not parse models status JSON')
j=json.loads(m.group(0))
print(f"defaultModel: {j.get('defaultModel')}")
oauth=j.get('auth',{}).get('oauth',{}).get('profiles',[])
if not oauth:
    print('oauthProfiles: none')
else:
    print('oauthProfiles:')
    for p in oauth:
        print(f"- {p.get('profileId')} | status={p.get('status')} | remainingMs={p.get('remainingMs')}")
PY
}

switch_login() {
  echo "Starting OpenAI Codex OAuth login flow..."
  echo "Complete browser auth with the OTHER account, then return here."
  openclaw models auth login --provider openai-codex
  echo "Done. New auth state:" 
  status
}

snapshot() {
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  mkdir -p state
  {
    echo "{"
    echo "  \"ts\": \"$ts\"," 
    echo "  \"note\": \"manual snapshot before/after account switch\""
    echo "}"
  } > state/codex_switch_snapshot.json
  echo "Wrote state/codex_switch_snapshot.json"
}

case "$cmd" in
  status) status ;;
  switch-login) switch_login ;;
  snapshot) snapshot ;;
  *)
    echo "Usage: $0 [root] {status|switch-login|snapshot}"
    exit 1
    ;;
esac

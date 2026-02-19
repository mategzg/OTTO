# otto-runtime-bridge

- `id`: `otto-runtime-bridge`
- `type`: `workspace-hook`
- `listens`: `message:received`, `message:sent`
- `entrypoint`: `handler.js`
- `status`: `experimental`

## Purpose

Forward OpenClaw message events into `scripts/channel_ingress_adapter.py` so runtime memory, domain inference, SG policies, and approvals run automatically.
This bridge is experimental; canonical runtime behavior is still defined by the adapter and workspace policies.
Primary safety behavior: append every message event to `state/hook_backlog/events.ndjson` before optional fast-path processing.

## Safety

- Runs only inside canonical workspace root (`.openclaw/CANONICAL_ROOT.json` required).
- Uses local python execution only (`python3 scripts/channel_ingress_adapter.py`).
- No external file scanning outside workspace.
- Ignores non-message events.
- Fail-open: hook never throws to gateway; heavy replay is deferred to `scripts/hook_backlog.py` via heartbeat.

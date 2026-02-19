# Card Schema (NDJSON)

## Supported Types

- `decision`
- `preference`
- `project_thread`
- `principle`
- `procedure`
- `playbook`
- `concept`
- `capability`

## Required Fields

- `id`
- `type`
- `tags`
- `summary`
- `source_ref`
- `status`
- `confidence`
- `supersedes`
- `last_confirmed_at`

## Example Records

```json
{"id":"decision-odoo-auth-001","type":"decision","tags":["odoo","auth"],"summary":"Use XML-RPC with explicit retries.","source_ref":"scripts/odoo/odoo_client.py","status":"active","confidence":0.92,"supersedes":null,"last_confirmed_at":"2026-02-18"}
{"id":"playbook-brain-index-001","type":"playbook","tags":["memoryos","index"],"summary":"Build deterministic Brain registry from markdown nodes.","source_ref":"scripts/brain_index_build.py","status":"draft","confidence":0.8,"supersedes":null,"last_confirmed_at":"2026-02-18"}
```

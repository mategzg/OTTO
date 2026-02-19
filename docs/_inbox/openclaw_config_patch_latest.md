# OpenClaw Config Patch (Report Only)

- Config path: `/home/agente/.openclaw/openclaw.json`
- Exists: `True`
- Current sessions.dmScope: `(missing)`
- Recommended sessions.dmScope: `per-account-channel-peer`
- Needs change: `True`

## Recommended patch
```json
{
  "sessions": {
    "dmScope": "per-account-channel-peer"
  }
}
```

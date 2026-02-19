# OpenClaw Skills System

> Source: manual ingest via Telegram (Topo), 2026-02-19
> Domain: openclaw_ops

## Overview

OpenClaw uses AgentSkills-compatible skill folders to teach the agent how to use tools. Each skill is a directory containing a `SKILL.md` with YAML frontmatter and instructions. OpenClaw loads bundled skills plus optional local overrides, and filters them at load time based on environment, config, and binary presence.

## Locations and Precedence

Skills are loaded from three places (highest → lowest):

1. **Workspace skills:** `<workspace>/skills`
2. **Managed/local skills:** `~/.openclaw/skills`
3. **Bundled skills:** shipped with the install (npm package or OpenClaw.app)

Additional folders can be configured via `skills.load.extraDirs` in `~/.openclaw/openclaw.json` (lowest precedence).

### Per-agent vs Shared Skills

In multi-agent setups, each agent has its own workspace:
- **Per-agent:** `<workspace>/skills` for that agent only.
- **Shared:** `~/.openclaw/skills` (managed/local), visible to all agents on the same machine.

## SKILL.md Format (AgentSkills + Pi-compatible)

Minimum required:

```yaml
---
name: nano-banana-pro
description: Generate or edit images via Gemini 3 Pro Image
---
```

### Optional Frontmatter Keys

- `homepage` — URL surfaced as "Website" in the macOS Skills UI.
- `user-invocable` — `true|false` (default: true). Exposes skill as user slash command.
- `disable-model-invocation` — `true|false` (default: false). Excludes from model prompt.
- `command-dispatch` — `tool` (optional). Bypasses model, dispatches directly to a tool.
- `command-tool` — tool name to invoke when `command-dispatch: tool`.
- `command-arg-mode` — `raw` (default). Forwards raw args string to the tool. Tool invoked with: `{ command: "<raw args>", commandName: "<slash command>", skillName: "<skill name>" }`.

## Metadata (Gating / Load-time Filters)

`metadata` must be a single-line JSON object in frontmatter:

```yaml
metadata: { "openclaw": { "requires": { "bins": ["uv"], "env": ["GEMINI_API_KEY"], "config": ["browser.enabled"] }, "primaryEnv": "GEMINI_API_KEY" } }
```

### Fields under `metadata.openclaw`

| Field | Description |
|---|---|
| `always: true` | Always include the skill (skip other gates) |
| `emoji` | Optional emoji for macOS Skills UI |
| `homepage` | Optional URL shown as "Website" in macOS Skills UI |
| `os` | Optional platform list (`darwin`, `linux`, `win32`). Skill only eligible on those OSes |
| `requires.bins` | List; each must exist on PATH |
| `requires.anyBins` | List; at least one must exist on PATH |
| `requires.env` | List; env var must exist or be provided in config |
| `requires.config` | List of `openclaw.json` paths that must be truthy |
| `primaryEnv` | Env var name associated with `skills.entries.<name>.apiKey` |
| `install` | Optional array of installer specs (brew/node/go/uv/download) |
| `skillKey` | Override key used under `skills.entries` in config |

### Sandboxing Note

`requires.bins` is checked on the host at skill load time. If an agent is sandboxed, the binary must also exist inside the container. Install via `agents.defaults.sandbox.docker.setupCommand` (or custom image). `setupCommand` runs once after container creation. Package installs require network egress, writable root FS, and root user.

## Installer Specs

Example:

```yaml
metadata: { "openclaw": { "emoji": "♊️", "requires": { "bins": ["gemini"] }, "install": [{ "id": "brew", "kind": "brew", "formula": "gemini-cli", "bins": ["gemini"], "label": "Install Gemini CLI (brew)" }] } }
```

Rules:
- Multiple installers → gateway picks single preferred option (brew when available, otherwise node).
- If all installers are `download`, OpenClaw lists each entry.
- Installer specs can include `os` to filter by platform.
- Node installs honor `skills.install.nodeManager` in `openclaw.json` (default: npm; options: npm/pnpm/yarn/bun).
- Go installs: if `go` is missing and brew is available, gateway installs Go via Homebrew first.
- Download installs: `url` (required), `archive` (tar.gz|tar.bz2|zip), `extract` (default: auto), `stripComponents`, `targetDir` (default: `~/.openclaw/tools/<skillKey>`).

If no `metadata.openclaw` is present, the skill is always eligible (unless disabled in config or blocked by `skills.allowBundled`).

## Config Overrides (`~/.openclaw/openclaw.json`)

```json
{
  "skills": {
    "entries": {
      "nano-banana-pro": {
        "enabled": true,
        "apiKey": "GEMINI_KEY_HERE",
        "env": { "GEMINI_API_KEY": "GEMINI_KEY_HERE" },
        "config": { "endpoint": "https://example.invalid", "model": "nano-pro" }
      },
      "peekaboo": { "enabled": true },
      "sag": { "enabled": false }
    }
  }
}
```

Rules:
- `enabled: false` disables the skill even if bundled/installed.
- `env`: injected only if variable isn't already set in process.
- `apiKey`: convenience for skills declaring `metadata.openclaw.primaryEnv`.
- `config`: optional bag for custom per-skill fields.
- `allowBundled`: optional allowlist for bundled skills only.

## Environment Injection (Per Agent Run)

When an agent run starts, OpenClaw:
1. Reads skill metadata.
2. Applies `skills.entries.<key>.env` or `skills.entries.<key>.apiKey` to `process.env`.
3. Builds system prompt with eligible skills.
4. Restores original environment after run ends.

Scoped to agent run, not global shell.

## Session Snapshot (Performance)

OpenClaw snapshots eligible skills when a session starts and reuses for subsequent turns. Changes take effect on next new session. Skills can refresh mid-session when watcher is enabled or new eligible remote node appears (hot reload on next agent turn).

## Skills Watcher (Auto-refresh)

```json
{
  "skills": {
    "load": {
      "watch": true,
      "watchDebounceMs": 250
    }
  }
}
```

## Remote macOS Nodes (Linux Gateway)

If Gateway runs on Linux but a macOS node is connected with `system.run` allowed, OpenClaw can treat macOS-only skills as eligible when required binaries are present on that node. Agent executes via `nodes` tool (`nodes.run`). If node goes offline, skills remain visible but invocations may fail.

## Token Impact

When ≥1 skill eligible, OpenClaw injects compact XML list into system prompt.

Formula (characters):
```
total = 195 + Σ (97 + len(name_escaped) + len(description_escaped) + len(location_escaped))
```

XML escaping expands `& < > " '` into entities. Rough estimate: ~4 chars/token, so ~24 tokens per skill plus field lengths.

## Plugins + Skills

Plugins ship their own skills via `openclaw.plugin.json` (paths relative to plugin root). Plugin skills load when plugin is enabled and participate in normal precedence. Gate via `metadata.openclaw.requires.config` on plugin's config entry.

## ClawHub (Install + Sync)

Registry: https://clawhub.com

```bash
clawhub install <skill-slug>      # Install to workspace
clawhub update --all               # Update all installed
clawhub sync --all                 # Scan + publish updates
```

Default install path: `./skills` under CWD (or configured workspace). Picked up as `<workspace>/skills` on next session.

## Security Notes

- Treat third-party skills as untrusted code. Read before enabling.
- Prefer sandboxed runs for untrusted inputs.
- `skills.entries.*.env` and `apiKey` inject secrets into host process (not sandbox).
- Keep secrets out of prompts and logs.

# OpenClaw Core Docs Research (focused on core control files)

## Findings
1. OpenClaw docs primarily define runtime capabilities (gateway/browser/models/channels/security), not a strict universal schema for custom core files like `SOUL.md` or `USER.md`.
2. In this workspace, those core files operate as a **control surface convention** (high-value and valid), so quality depends on clear contracts and anti-drift coherence.
3. To make them more operational, they should be concise, non-overlapping, and explicit about scope/rules/update triggers.

## Applied improvement
- Added `Core File Design Standard` to `AGENTS.md` to enforce operability-first structure for core files.

## Recommended ongoing pattern
- Keep strategy in `SOUL.md` and vision in `memory/vision/*` (no duplication).
- Keep owner collaboration contract in `USER.md`.
- Keep periodic execution contract in `HEARTBEAT.md`.
- Keep memory routing in `MEMORY.md`.
- Run coherence checks after every core-file change.

## GAP/NO_VERIFICADO
- No official OpenClaw page found that mandates these exact file names as universal product-level defaults; this remains workspace-specific architecture.

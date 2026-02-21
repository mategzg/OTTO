# 17 — OpenClaw Docs Bible Protocol

## Purpose
Use `https://docs.openclaw.ai/` as canonical external reference for precise OpenClaw behavior, commands, and architecture.

## Source map (from llms index)
Primary high-density sections:
- `cli/*`
- `gateway/*`
- `concepts/*`
- `channels/*`
- `platforms/*`
- `tools/*`
- `reference/*`
- `providers/*`

## Protocol
1. Start local: check `/docs` mirror + repo maps/context docs.
2. If detail is missing/ambiguous: open exact section in docs.openclaw.ai.
3. Extract only what is needed for current task (anti-overread).
4. Apply result in action/response.
5. Persist reusable learning in this domain or corresponding branch.

## Trigger routing
- Command/flag uncertainty -> `cli/*`
- Runtime/gateway issues -> `gateway/*`
- Browser/tools/nodes behavior -> `tools/*` and `nodes/*`
- Channel-specific issues -> `channels/*`
- Model/provider/auth limits -> `providers/*`
- Template/control file guidance -> `reference/*`
- Install/platform environment -> `install/*` + `platforms/*`

## Quality gate
- Never invent OpenClaw behavior.
- If uncertain after lookup: `GAP/NO_VERIFICADO` + next verification step.

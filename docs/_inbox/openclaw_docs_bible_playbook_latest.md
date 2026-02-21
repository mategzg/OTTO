# OpenClaw Docs Bible Playbook (Deep Map)

Base URL (canon): https://docs.openclaw.ai/

## Coverage scan
- Source scanned: `https://docs.openclaw.ai/llms.txt`
- Indexed URLs detected: **265**

## Major sections by density (what to consult first)
1. `cli/*` (36) — comandos, flags, comportamiento CLI
2. `gateway/*` (30) — daemon, runtime control, networking
3. `concepts/*` (28) — arquitectura mental (cómo piensa OpenClaw)
4. `channels/*` (24) — comportamiento por canal/proveedor
5. `platforms/*` (24) — entorno y despliegue por plataforma
6. `tools/*` (21) — browser, nodes, exec y tool surfaces
7. `install/*` (20) — setup y prerequisites
8. `reference/*` (17) — templates, specs y contratos
9. `providers/*` (15) — modelos/proveedores, auth y límites
10. `start/*` (11) — rutas de inicio y quickstarts

## When to use docs.openclaw.ai (trigger matrix)
- Si duda sobre **comando/flag exacto** -> `cli/*`
- Si falla runtime/relay/socket/control UI -> `gateway/*` + `tools/*`
- Si duda de **comportamiento conceptual** -> `concepts/*`
- Si problema de canal (Telegram/WhatsApp/Discord/...) -> `channels/*`
- Si ajuste de entorno/host/deploy -> `platforms/*` + `install/*`
- Si diseño de core/docs/templates/policies -> `reference/*`
- Si auth/model/limits/provider -> `providers/*`
- Si automatización programada -> `automation/*`
- Si paired devices / phone / node -> `nodes/*`
- Si seguridad de superficie -> `security/*` + `gateway/*`

## Operational rule adopted
1. Local docs first (`/home/agente/otto-workspace/docs`).
2. If ambiguity or missing detail: consult `https://docs.openclaw.ai/` in the relevant section above.
3. Persist operational learning into the correct branch (openclaw_ops / personal_ops / sg_acabados / vision/profile as applicable).

## Non-negotiable
No inventar comandos ni capacidades: si no está verificado en docs/runtime -> `GAP/NO_VERIFICADO`.

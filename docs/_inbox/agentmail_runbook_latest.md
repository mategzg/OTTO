# AgentMail Runbook (OTTO)

## Inbox operativo
- `sgacabados@agentmail.to`

## Ejecución manual (sin auto reply)
```bash
export AGENTMAIL_API_KEY='***'
python3 /home/agente/otto-workspace/scripts/agentmail_autonomy_worker.py --inbox sgacabados@agentmail.to
```

## Ejecución con auto reply
```bash
export AGENTMAIL_API_KEY='***'
python3 /home/agente/otto-workspace/scripts/agentmail_autonomy_worker.py --inbox sgacabados@agentmail.to --auto-reply
```

## Reportes
- `docs/_inbox/agentmail_autonomy_latest.md`
- `docs/_inbox/agentmail_autonomy_latest.json`
- Estado de dedupe: `state/agentmail_autonomy_state.json`

## Regla operativa
- Por defecto: `draft_only` (sin respuesta automática).
- Activar `--auto-reply` solo cuando lo pidas explícitamente.

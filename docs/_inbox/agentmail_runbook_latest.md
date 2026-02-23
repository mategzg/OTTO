# AgentMail Runbook (OTTO)

## Inbox operativo
- `sgacabados@agentmail.to`

## Ejecución manual (default = auto reply activo)
```bash
export AGENTMAIL_API_KEY='***'
python3 /home/agente/otto-workspace/scripts/agentmail_autonomy_worker.py --inbox sgacabados@agentmail.to
```

## Ejecución en modo draft-only (sin enviar)
```bash
export AGENTMAIL_API_KEY='***'
python3 /home/agente/otto-workspace/scripts/agentmail_autonomy_worker.py --inbox sgacabados@agentmail.to --draft-only
```

## Reportes
- `docs/_inbox/agentmail_autonomy_latest.md`
- `docs/_inbox/agentmail_autonomy_latest.json`
- Estado de dedupe: `state/agentmail_autonomy_state.json`

## Regla operativa
- Por defecto: `auto-reply` activo.
- Usar `--draft-only` cuando quieras correr en modo seguro/sin envío.

# 40 Outbox + Approvals

Lectura minima:

1. `scripts/outbox_queue.py`
2. `scripts/outbox_delivery.py`
3. `scripts/approval_manager.py`
4. `scripts/sg_promotion.py`
5. `scripts/openclaw_cli.py`

Autoridad:

- Cola saliente: `docs/_inbox/outbox_queue.ndjson`
- Snapshot legible: `docs/_inbox/outbox_latest.md`

Reglas:

- Aprobaciones del owner por Telegram (NL sin IDs).
- SG promotions: low auto; medium/high con approval.
- Delivery intenta OpenClaw CLI; si falla, item queda pending con reason.

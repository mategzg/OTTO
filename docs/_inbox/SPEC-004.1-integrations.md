# SPEC-004.1 Integrations Backlog

Status: planned (post SPEC-004 core GO)
Date: 2026-02-22

## Scope A — SharePoint E2E
- Connector auth + incremental sync (delta token / modified_at / etag)
- Conversion pipeline docx/pdf/html/xlsx -> markdown
- Audience tagging (`public|staff|internal`) + domain tagging
- Retrieval validation with citations
- Failure modes: retries, dead-letter, breaker

## Scope B — Odoo E2E
- Typed tools: `odoo.read`, `odoo.write`, `odoo.quote_draft`, `odoo.order_draft`
- Deterministic lead -> quote -> handoff flow
- Critical gate: order confirmation requires Mateo handoff
- Side effects: idempotency keys, retries, audit logs
- Failure modes + rollback playbook

## Scope C — Client-facing output hardening
- Audience/internal redaction middleware hardening
- Output contract enforcement for WhatsApp client-facing channels
- Negative tests for forbidden citations and path leaks

## Scope D — Live fixtures
- Telegram/Discord/WhatsApp live fixture tests
- Ingest large attachment fixtures + idempotent re-ingest
- End-to-end evidence packs by trace id

## Exit criteria
- New audit target: `spec004_integrations`
- GO/NO-GO with reproducible bundle and thresholds

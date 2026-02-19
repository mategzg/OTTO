# Brain Protocol

## Where New Knowledge Goes

- Reusable operating knowledge -> create/update a Brain node.
- Temporary execution notes -> `docs/_inbox/`.
- Operational run evidence -> `ops/RUN_LEDGER.ndjson` and copilot report.

## How To Answer Without Reading Everything

1. Query index artifacts first.
2. Select minimum relevant nodes.
3. Answer from canonical node sections.
4. Deep-link only when more detail is needed.

## When To Ask User Confirmation

Ask confirmation before:

- External side effects.
- Irreversible actions.
- Conflicts between two active canonical nodes.

## Contradiction Handling

When two facts conflict:

- Mark old item as superseded using `supersedes` and `status`.
- Keep both records for traceability.
- Update `last_confirmed_at` on the active record.
- Prefer highest-confidence, latest-confirmed active record.

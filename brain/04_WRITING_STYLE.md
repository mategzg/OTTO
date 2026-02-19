# Writing Style for Brain Nodes

## Structure Principles

Derived from the Claude inverse-engineering source corpus snapshot in
`vault/inbox_raw/claude_inverse_engineering/`.

- Use stable heading hierarchy (`#`, `##`, `###`) with predictable sections.
- Prefer paired sections like "When to use" and "When not to use" when needed.
- Keep each node modular: one purpose, one scope.
- Put navigation hints in plain language: "If you need X, go to Y".
- Keep parameters, rules, and examples in explicit sections.
- Prefer explicit control blocks for operations:
  - `Objective`
  - `Scope (permitido/prohibido)`
  - `Gates`
  - `Stop conditions`
  - `Evidence paths`

## Ops Routing Pattern

- Every operational node should include `Use when` and `Avoid when`.
- Include at least 3 direct route rules: "si preguntas X -> ve a Y".
- Keep canonical answer short and push depth into cards with `source_ref`.

## Authoring Rules

- Start with purpose and read order.
- Keep canonical answers short and link out for depth.
- Use explicit file paths for every deep link.
- Avoid long prose dumps; split into atomic sections.
- Mark status clearly (`active`, `draft`, `superseded`).

## Navigation Pattern

If you are searching:

- for process rules -> `brain/01_BRAIN_PROTOCOL.md`
- for node format -> `brain/02_NODE_TEMPLATE.md`
- for card format -> `brain/03_CARD_SCHEMA.md`
- for top-level orientation -> `brain/00_INDEX.md`

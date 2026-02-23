# Corpus Assimilation Plan

- Plan ID: `PLAN-20260223T035737Z-ee8e7418`
- Status: `ok`
- Stop reasons: ``
- Pending sources(selected): 2
- Pending sources(total): 2
- Operations: 2
- Routing summary: `{"brain_knowledge": 1, "inbox_only": 1}`
- Plan path: `state/ingest_plans/PLAN-20260223T035737Z-ee8e7418.json`
- JSON report: `docs/_inbox/corpus_assimilation_plan_latest.json`
- Log report: `logs/corpus_assimilation_plan_latest.json`

## Sources

- `20260223T035737Z_2fe07e03cf` id=109263f75f category=brain_knowledge domain=external_ingest cards=1
- `20260223T035737Z_8418855593` id=8a918da6a9 category=inbox_only domain=external_ingest cards=0

## Routing Decisions

- id=109263f75f category=brain_knowledge domain=external_ingest rule=default_brain_knowledge
- id=8a918da6a9 category=inbox_only domain=external_ingest rule=inbox_only_large_binary

## Operations

- `brain/cards/external_ingest/card_109263f75f_01.md` | op_id=d683c5cee3a1 | source=109263f75f | type=write | category=brain_knowledge
- `brain/domains/external_ingest/sources/109263f75f_index.md` | op_id=3669fa59d537 | source=109263f75f | type=write | category=brain_knowledge

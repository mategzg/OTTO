# Export Assimilation Contract (Quality-First)

## Purpose
Guarantee that large ChatGPT exports are transformed into useful, correctly-routed, indexed knowledge — not dumped.

## Mandatory phases
1. **Ingest Raw**: complete intake/normalize/triage without loss.
2. **Raw Bucketization**: classify all content into canonical raw buckets before synthesis (professional_sg, personal_development, profile_owner, vision_owner, biography_history, strategy_business, philosophy, psychology, neuroscience_health, persuasion_communication, habits_execution, misc_knowledge).
3. **Reduce Noise**: dedupe + filter low-value content.
4. **Curate & Write**: write to correct branch with strict boundaries:
   - profile -> `memory/profile/*`
   - vision -> `memory/vision/*`
   - business/professional -> `brain/domains/sg_acabados/*`
   - OTTO operational learning -> `brain/domains/personal_ops/*`
4. **Index & Verify**: rebuild indexes + run query smoke checks.

## Completion criteria
- No pending raw drop for the processed package.
- Curated artifacts exist in correct destinations.
- Indexes rebuilt and query checks return relevant nodes.
- Evidence report generated with gaps explicitly tagged (`GAP/NO_VERIFICADO`).

## Non-negotiables
- No false DONE.
- No branch mixing.
- No blind copying raw corpus into canonical branches.
- New branches/subbranches are allowed and expected when needed for quality.

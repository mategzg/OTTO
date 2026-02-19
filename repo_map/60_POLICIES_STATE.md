# 60 Policies + State

Politicas clave:

- `state/channel_runtime_policy.json`: tiers, budgets, triggers.
- `state/heartbeat_policy.json`: cadencia y limites heartbeat.
- `state/write_router_policy.json`: routing de ingestion/escritura.
- `state/memory_policy.json`: schema de MemoryOS.
- `state/sg_policy.json`: auth worker + promotion rules.
- `state/instruction_surface_policy.json`: reserved filenames/allowlist.
- `state/workspace_hygiene_policy.json`: exclusiones y clasificacion hygiene.
- `state/project_docs_policy.json`: mantenimiento de PROJECT_BRIEF/REPO_MAP.

Estado operativo:

- `state/autonomy_state.json`
- `state/project_docs_state.json`
- `state/sg_worker_pairings.json`

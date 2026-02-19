# HEARTBEAT.md

Run exactly this command from the workspace root:

`python3 scripts/heartbeat_worker.py --once --root .`

If the run finishes with no pending work or blocking errors, respond:

`HEARTBEAT_OK`

Rules:
- Do not infer old tasks from prior chats.
- Process only what current policies and queues indicate.
- Keep execution bounded by `state/heartbeat_policy.json`.

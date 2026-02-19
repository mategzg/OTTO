# 70 Tests + Gates

Comandos recomendados:

- `pytest -q`
- `python3 scripts/heartbeat_worker.py --once --root . --force`
- `python3 scripts/repo_reality_doctor.py --scan --json`
- `python3 scripts/workspace_hygiene_doctor.py --scan`
- `python3 scripts/instruction_surface_doctor.py --scan --root .`
- `python3 scripts/brain_index_build.py`

Tests relevantes por dominio:

- runtime/ingress: `tests/test_channel_ingress_and_approvals.py`
- heartbeat: `tests/test_heartbeat_worker.py`
- outbox/delivery: `tests/test_outbox_queue_and_delivery_mock_cli.py`
- memory: `tests/test_memory_pipeline.py`
- doctors/hygiene/surface: `tests/test_repo_reality_doctor.py`, `tests/test_workspace_hygiene.py`, `tests/test_instruction_surface_doctor.py`

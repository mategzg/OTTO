from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import dashboard_server
import index_docs
import otto_state


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_state_set_status_writes_json_and_log(tmp_path: Path) -> None:
    otto_state.set_status(
        root=tmp_path,
        status="working",
        task="Preparando proposal",
    )

    status_data = _read_json(tmp_path / "state" / "status.json")
    assert status_data["status"] == "working"
    assert status_data["task"] == "Preparando proposal"

    activity_lines = (tmp_path / "logs" / "activity.ndjson").read_text(
        encoding="utf-8"
    ).strip().splitlines()
    assert len(activity_lines) >= 1
    last = json.loads(activity_lines[-1])
    assert last["event"] == "set_status"


def test_kanban_add_task_and_move_task(tmp_path: Path) -> None:
    created = otto_state.add_task(
        root=tmp_path,
        title="Crear flujo B1",
        detail="Definir pasos",
        priority="high",
    )

    otto_state.move_task(root=tmp_path, task_id=created["id"], to_column="done")

    kanban_data = _read_json(tmp_path / "state" / "kanban.json")
    assert kanban_data["todo"] == []
    assert len(kanban_data["done"]) == 1
    assert kanban_data["done"][0]["id"] == created["id"]


def test_index_docs_generates_indexes_deterministically(tmp_path: Path) -> None:
    docs_root = tmp_path / "docs" / "empresa"
    lic = docs_root / "licitaciones"
    leads = docs_root / "leads"
    cot = docs_root / "cotizaciones"
    for folder in (lic, leads, cot):
        folder.mkdir(parents=True, exist_ok=True)

    (lic / "2026-02-11-zeta.md").write_text("z", encoding="utf-8")
    (lic / "2026-02-10-alpha.md").write_text("a", encoding="utf-8")
    (leads / "lead-b.md").write_text("b", encoding="utf-8")
    (leads / "lead-a.md").write_text("a", encoding="utf-8")

    index_docs.rebuild_indexes(root=tmp_path)

    lic_index = (lic / "index.md").read_text(encoding="utf-8")
    leads_index = (leads / "index.md").read_text(encoding="utf-8")

    assert lic_index.index("2026-02-10-alpha.md") < lic_index.index("2026-02-11-zeta.md")
    assert leads_index.index("lead-a.md") < leads_index.index("lead-b.md")


def test_dashboard_api_path_traversal_blocked(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "status.json").write_text(
        json.dumps({"status": "idle", "task": "", "updated_at": ""}, indent=2),
        encoding="utf-8",
    )
    (tmp_path / "state" / "kanban.json").write_text(
        json.dumps(
            {"archive": [], "done": [], "in_progress": [], "todo": []},
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "activity.ndjson").write_text("", encoding="utf-8")

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    _, port = sock.getsockname()
    sock.close()

    server = dashboard_server.build_server(port=port, root=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/docs?path=../",
                timeout=2,
            )
        assert exc.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

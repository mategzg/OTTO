from __future__ import annotations

import statistics
import time
from pathlib import Path

from scripts.dispatcher_policy import load_dispatcher_policy, should_delegate, within_limits
from scripts.outbox_queue import enqueue_message, materialized_items
from scripts.repo_root import set_canonical_root


def _mk_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    for d in ("openclaw", "scripts", "ops", "brain", "docs/_inbox", "logs", "state"):
        (root / d).mkdir(parents=True, exist_ok=True)


def _setup(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / "workspace"
    _mk_workspace(workspace)
    monkeypatch.setenv("HOME", str(home))
    set_canonical_root(workspace, created_by="test")
    return workspace


def test_should_delegate_hard_rules(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pol = load_dispatcher_policy(workspace)
    a = should_delegate(pol, intent_id="odoo_cotizar", attachments=[], selected_target="rag.answer")
    assert a["delegate"] is True
    b = should_delegate(pol, intent_id="chat_normal", attachments=[{"x": 1}], selected_target="rag.answer")
    assert b["delegate"] is True
    c = should_delegate(pol, intent_id="chat_normal", attachments=[], selected_target="odoo.enqueue")
    assert c["delegate"] is True


def test_limits_enforced(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    pol = load_dispatcher_policy(workspace)
    ok = within_limits(pol, active_runs=1, spawn_depth=0, children_for_agent=1)
    assert ok["ok"] is True
    no = within_limits(pol, active_runs=99, spawn_depth=0, children_for_agent=1)
    assert no["ok"] is False


def test_queue_collect_under_load(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    for i in range(100):
        enqueue_message(
            workspace,
            channel="whatsapp",
            target="client-1",
            text=f"ack {i}",
            purpose="dispatcher_ack",
            metadata={"collect_key": "ack:client-1"},
        )
    items = materialized_items(workspace)
    pending = [x for x in items if x.get("status") == "pending"]
    assert len(pending) == 1
    assert pending[0]["text"] == "ack 99"


def test_ack_benchmark_p95_under_2s(tmp_path: Path, monkeypatch):
    workspace = _setup(tmp_path, monkeypatch)
    samples = []
    for i in range(50):
        t0 = time.perf_counter()
        enqueue_message(
            workspace,
            channel="whatsapp",
            target="client-burst",
            text=f"ack burst {i}",
            purpose="dispatcher_ack",
            metadata={"collect_key": "ack:burst"},
        )
        dt_ms = (time.perf_counter() - t0) * 1000.0
        samples.append(dt_ms)
    p95 = statistics.quantiles(samples, n=100)[94]
    assert p95 < 2000, p95

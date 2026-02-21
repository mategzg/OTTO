from pathlib import Path

from scripts.nl_skill_router import route_request, run_nl_router


def test_router_maps_reminder_to_skill(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    out = route_request(tmp_path, text="recuerdame mañana pagar", channel="telegram")
    assert out["intent_id"] == "reminder_request"
    assert out["route_type"] == "skill"
    assert out["selected_target"] == "reminder.create"


def test_router_create_skill_decision_for_repeated_high_impact_tool(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    out = route_request(
        tmp_path,
        text="explicame la vision completa y cita fuentes",
        channel="telegram",
        repeat_count_30d=5,
        impact_score=9,
        risk_score=3,
    )
    assert out["route_type"] in {"tool", "workflow", "skill"}
    assert out["create_skill_decision"]["eligible"] is True
    # chat_normal routes to tool by default, thus create should be enabled
    assert out["create_skill_decision"]["decision"] == "create"


def test_router_defers_skill_creation_when_random(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    out = route_request(
        tmp_path,
        text="hola",
        channel="telegram",
        repeat_count_30d=1,
        impact_score=1,
        risk_score=1,
    )
    assert out["create_skill_decision"]["eligible"] is False
    assert out["create_skill_decision"]["decision"] == "defer"


def test_unified_router_returns_contracts_and_idempotency(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    out = run_nl_router(
        tmp_path,
        text="recuérdame mañana pagar internet",
        channel="telegram",
        conversation_id="c1",
        thread_id="t1",
        message_id="m1",
    )
    assert out["status"] == "success"
    assert out["idempotency_key"].startswith("nlr:")
    assert out["plan"]["intent_id"] == "reminder_request"
    assert out["contracts"]["execution"]["idempotent"] is True


def test_unified_router_falls_back_when_skill_not_registered(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    out = run_nl_router(
        tmp_path,
        text="quiero odoo stock de hoy",
        channel="telegram",
        conversation_id="c1",
        thread_id="t1",
        message_id="m3",
    )
    assert out["status"] == "success"
    assert out["plan"]["route_type"] == "tool"
    assert out["plan"]["selected_target"] == "rag.answer"


def test_unified_router_returns_cooldown_when_circuit_open(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    # force breaker open via repeated failed records
    from scripts.circuit_breaker import record_execution

    for _ in range(6):
        record_execution(tmp_path, resource="nl_router", success=False, latency_ms=100, timed_out=True)

    out = run_nl_router(
        tmp_path,
        text="hola",
        channel="telegram",
        conversation_id="c1",
        thread_id="t1",
        message_id="m4",
    )
    assert out["status"] == "cooldown"
    assert out["error"]["code"] == "circuit_open"


def test_unified_router_honors_cancel(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)

    import scripts.nl_skill_router as r

    monkeypatch.setattr(r, "get_canonical_root", lambda root: Path(root).resolve())

    out = run_nl_router(
        tmp_path,
        text="hola",
        channel="telegram",
        conversation_id="c1",
        thread_id="t1",
        message_id="m2",
        cancel_requested=True,
    )
    assert out["status"] == "cancelled"
    assert out["error"]["code"] == "cancelled"

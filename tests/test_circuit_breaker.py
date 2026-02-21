from pathlib import Path

from scripts.circuit_breaker import record_execution, should_allow


def test_circuit_breaker_opens_after_repeated_failures(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)

    import scripts.circuit_breaker as cb

    monkeypatch.setattr(cb, "get_canonical_root", lambda root: Path(root).resolve())

    for _ in range(6):
        record_execution(tmp_path, resource="nl_router", success=False, latency_ms=100, timed_out=True)

    gate = should_allow(tmp_path, resource="nl_router")
    assert gate["allowed"] is False
    assert gate["status"] == "open"


def test_circuit_breaker_allows_when_closed(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)

    import scripts.circuit_breaker as cb

    monkeypatch.setattr(cb, "get_canonical_root", lambda root: Path(root).resolve())

    gate = should_allow(tmp_path, resource="nl_router")
    assert gate["allowed"] is True

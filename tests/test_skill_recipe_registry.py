from pathlib import Path

from scripts.skill_recipe_registry import (
    ensure_default_registries,
    resolve_target,
    transition_entity_state,
    validate_transition,
)


def test_default_registries_are_created(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)

    import scripts.skill_recipe_registry as reg

    monkeypatch.setattr(reg, "get_canonical_root", lambda root: Path(root).resolve())

    ensure_default_registries(tmp_path)
    assert (tmp_path / "state" / "skills_registry.json").is_file()
    assert (tmp_path / "state" / "recipes_registry.json").is_file()


def test_resolve_target_rejects_non_enabled_skill(tmp_path: Path, monkeypatch):
    (tmp_path / "CEO.md").write_text("# CEO\n", encoding="utf-8")
    (tmp_path / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
    (tmp_path / "openclaw").mkdir(parents=True)

    import scripts.skill_recipe_registry as reg

    monkeypatch.setattr(reg, "get_canonical_root", lambda root: Path(root).resolve())

    ensure_default_registries(tmp_path)
    moved = transition_entity_state(tmp_path, kind="skill", name="research.request", target_state="deprecated")
    assert moved["status"] == "ok"

    out = resolve_target(tmp_path, route_type="skill", selected_target="research.request", channel="telegram")
    assert out["ok"] is False
    assert "status_" in out["reason"]


def test_validate_transition_rules():
    ok, reason = validate_transition("draft", "test")
    assert ok is True and reason == "ok"

    ok, reason = validate_transition("enabled", "test")
    assert ok is False and reason == "transition_not_allowed"

#!/usr/bin/env python3
"""Formal registry for skills/recipes with lifecycle states and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from scripts.repo_root import get_canonical_root

SKILLS_REGISTRY_PATH = Path("state/skills_registry.json")
RECIPES_REGISTRY_PATH = Path("state/recipes_registry.json")

LIFECYCLE_STATES = ["draft", "test", "enabled", "deprecated", "retired"]
VALID_TRANSITIONS = {
    "draft": {"test", "retired"},
    "test": {"enabled", "deprecated", "retired"},
    "enabled": {"deprecated", "retired"},
    "deprecated": {"enabled", "retired"},
    "retired": set(),
}


DEFAULT_SKILLS_REGISTRY: Dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "entities": {
        "reminder.create": {
            "name": "reminder.create",
            "kind": "skill",
            "version": "1.0.0",
            "status": "enabled",
            "risk_level": "low",
            "permissions": ["outbox.enqueue"],
            "side_effects": ["enqueue_reminder"],
            "input_schema": {"required": ["text"], "optional": ["time_hint"]},
            "compatibility": {"channels": ["telegram", "discord", "whatsapp"]},
        },
        "research.request": {
            "name": "research.request",
            "kind": "skill",
            "version": "1.0.0",
            "status": "enabled",
            "risk_level": "medium",
            "permissions": ["research.enqueue"],
            "side_effects": ["enqueue_research"],
            "input_schema": {"required": ["text"], "optional": ["topic"]},
            "compatibility": {"channels": ["telegram", "discord", "whatsapp"]},
        },
        "odoo.cotizar": {
            "name": "odoo.cotizar",
            "kind": "skill",
            "version": "1.0.0",
            "status": "enabled",
            "risk_level": "medium",
            "permissions": ["odoo.enqueue"],
            "side_effects": ["enqueue_odoo"],
            "input_schema": {"required": ["text"], "optional": ["customer"]},
            "compatibility": {"channels": ["telegram", "whatsapp"]},
        },
    },
}

DEFAULT_RECIPES_REGISTRY: Dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "entities": {
        "status.check": {
            "name": "status.check",
            "kind": "recipe",
            "version": "1.0.0",
            "status": "enabled",
            "risk_level": "low",
            "permissions": ["status.read"],
            "side_effects": [],
            "input_schema": {"required": [], "optional": ["scope"]},
            "compatibility": {"channels": ["telegram", "discord", "whatsapp"]},
        }
    },
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def ensure_default_registries(root: str | Path) -> None:
    canonical_root = get_canonical_root(root)
    skills_path = canonical_root / SKILLS_REGISTRY_PATH
    recipes_path = canonical_root / RECIPES_REGISTRY_PATH
    if not skills_path.exists():
        _save_json(skills_path, DEFAULT_SKILLS_REGISTRY)
    if not recipes_path.exists():
        _save_json(recipes_path, DEFAULT_RECIPES_REGISTRY)


def _registry_for_kind(root: Path, kind: str) -> Dict[str, Any]:
    path = root / (SKILLS_REGISTRY_PATH if kind == "skill" else RECIPES_REGISTRY_PATH)
    payload = _load_json(path)
    if not payload:
        ensure_default_registries(root)
        payload = _load_json(path)
    if not isinstance(payload.get("entities"), dict):
        payload["entities"] = {}
    return payload


def resolve_target(
    root: str | Path,
    *,
    route_type: str,
    selected_target: str,
    channel: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    ensure_default_registries(canonical_root)

    if route_type not in {"skill", "workflow", "recipe"}:
        return {"ok": True, "route_type": route_type, "selected_target": selected_target, "status": "n/a"}

    kind = "skill" if route_type == "skill" else "recipe"
    registry = _registry_for_kind(canonical_root, kind)
    entity = registry.get("entities", {}).get(selected_target)
    if not isinstance(entity, dict):
        return {
            "ok": False,
            "route_type": route_type,
            "selected_target": selected_target,
            "reason": "not_registered",
            "fallback": {"route_type": "tool", "selected_target": "rag.answer"},
        }

    status = str(entity.get("status", "draft"))
    if status != "enabled":
        return {
            "ok": False,
            "route_type": route_type,
            "selected_target": selected_target,
            "reason": f"status_{status}",
            "fallback": {"route_type": "tool", "selected_target": "rag.answer"},
        }

    channels = entity.get("compatibility", {}).get("channels", [])
    clean_channel = channel.split("_")[0].strip().lower()
    if channels and clean_channel and clean_channel not in [str(c).strip().lower() for c in channels]:
        return {
            "ok": False,
            "route_type": route_type,
            "selected_target": selected_target,
            "reason": "channel_incompatible",
            "fallback": {"route_type": "tool", "selected_target": "rag.answer"},
        }

    return {
        "ok": True,
        "route_type": route_type,
        "selected_target": selected_target,
        "status": status,
        "entity": {
            "kind": entity.get("kind", kind),
            "version": entity.get("version", ""),
            "risk_level": entity.get("risk_level", "low"),
            "permissions": entity.get("permissions", []),
            "side_effects": entity.get("side_effects", []),
            "input_schema": entity.get("input_schema", {}),
        },
    }


def validate_transition(current: str, target: str) -> Tuple[bool, str]:
    cur = str(current).strip().lower()
    nxt = str(target).strip().lower()
    if cur not in VALID_TRANSITIONS:
        return False, "invalid_current_state"
    if nxt not in LIFECYCLE_STATES:
        return False, "invalid_target_state"
    if nxt not in VALID_TRANSITIONS[cur]:
        return False, "transition_not_allowed"
    return True, "ok"


def transition_entity_state(
    root: str | Path,
    *,
    kind: str,
    name: str,
    target_state: str,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    ensure_default_registries(canonical_root)

    clean_kind = "skill" if kind == "skill" else "recipe"
    path = canonical_root / (SKILLS_REGISTRY_PATH if clean_kind == "skill" else RECIPES_REGISTRY_PATH)
    registry = _load_json(path)
    entities = registry.get("entities", {}) if isinstance(registry.get("entities"), dict) else {}
    entity = entities.get(name)
    if not isinstance(entity, dict):
        return {"status": "error", "reason": "entity_not_found", "kind": clean_kind, "name": name}

    current = str(entity.get("status", "draft"))
    ok, reason = validate_transition(current, target_state)
    if not ok:
        return {
            "status": "error",
            "reason": reason,
            "kind": clean_kind,
            "name": name,
            "current_state": current,
            "target_state": target_state,
        }

    entity["status"] = target_state
    entities[name] = entity
    registry["entities"] = entities
    _save_json(path, registry)
    return {
        "status": "ok",
        "kind": clean_kind,
        "name": name,
        "previous_state": current,
        "new_state": target_state,
    }

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/dispatcher_policy.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "ack_target_ms": 2000,
    "delegation": {
        "always_delegate_if": {
            "intent_ids": [
                "research_request",
                "reminder_request",
                "odoo_cotizar",
                "odoo_stock",
                "odoo_cliente",
                "odoo_factura",
                "odoo_pago",
                "odoo_cuenta",
                "odoo_reporte",
            ],
            "has_attachments": True,
            "router_targets_not_safe": ["rag.answer"],
        }
    },
    "limits": {
        "maxConcurrent": 8,
        "maxSpawnDepth": 2,
        "maxChildrenPerAgent": 20,
    },
}


def load_dispatcher_policy(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    path = canonical_root / POLICY_PATH
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_POLICY, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return json.loads(json.dumps(DEFAULT_POLICY))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    merged = json.loads(json.dumps(DEFAULT_POLICY))
    merged.update(payload)
    for key in ("delegation", "limits"):
        if isinstance(payload.get(key), dict):
            merged[key] = dict(DEFAULT_POLICY.get(key, {})) | dict(payload.get(key, {}))
    return merged


def should_delegate(policy: Dict[str, Any], *, intent_id: str, attachments: list[Any], selected_target: str) -> Dict[str, Any]:
    rules = policy.get("delegation", {}).get("always_delegate_if", {}) if isinstance(policy.get("delegation", {}), dict) else {}
    intents = {str(x).strip() for x in rules.get("intent_ids", []) if str(x).strip()}
    safe_targets = {str(x).strip() for x in rules.get("router_targets_not_safe", []) if str(x).strip()}

    if str(intent_id).strip() in intents:
        return {"delegate": True, "reason": "intent_policy"}
    if bool(rules.get("has_attachments", True)) and bool(attachments):
        return {"delegate": True, "reason": "attachments"}
    if selected_target and selected_target not in safe_targets:
        return {"delegate": True, "reason": "tooling_target"}
    return {"delegate": False, "reason": "safe_inline"}


def within_limits(policy: Dict[str, Any], *, active_runs: int, spawn_depth: int, children_for_agent: int) -> Dict[str, Any]:
    limits = policy.get("limits", {}) if isinstance(policy.get("limits", {}), dict) else {}
    max_concurrent = int(limits.get("maxConcurrent", 8))
    max_depth = int(limits.get("maxSpawnDepth", 2))
    max_children = int(limits.get("maxChildrenPerAgent", 20))
    ok = active_runs < max_concurrent and spawn_depth < max_depth and children_for_agent < max_children
    return {
        "ok": ok,
        "active_runs": active_runs,
        "spawn_depth": spawn_depth,
        "children_for_agent": children_for_agent,
        "maxConcurrent": max_concurrent,
        "maxSpawnDepth": max_depth,
        "maxChildrenPerAgent": max_children,
    }

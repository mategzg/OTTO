#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/runtime_guardrails_policy.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "dm_scope": {"whatsapp_require_real_peer": True},
    "send_policy": {
        "block_sources": ["cron:", "hook:"],
        "protected_channels": ["whatsapp"],
        "protected_recipient_types": ["client"],
        "internal_recipient_types": ["owner", "worker", "internal"],
    },
    "tool_policy": {
        "default": {"allow": ["*"], "deny": []},
        "agents": {}
    },
    "no_leak": {"whatsapp_client_redaction": True},
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_guardrails(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    payload = _load_json(canonical_root / POLICY_PATH)
    merged: Dict[str, Any] = json.loads(json.dumps(DEFAULT_POLICY))
    if payload:
        merged.update(payload)
        for key in ("dm_scope", "send_policy", "tool_policy", "no_leak"):
            if isinstance(payload.get(key), dict):
                merged[key] = dict(DEFAULT_POLICY.get(key, {})) | dict(payload.get(key, {}))
    path = canonical_root / POLICY_PATH
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return merged


def is_real_peer(peer_id: str) -> bool:
    p = str(peer_id or "").strip().lower()
    return p not in {"", "_", "unknown", "none", "null"}


def redact_no_leak_report(report: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(report))
    route = out.get("nl_skill_route", {}) if isinstance(out.get("nl_skill_route", {}), dict) else {}
    retrieval = route.get("retrieval_v2", {}) if isinstance(route.get("retrieval_v2", {}), dict) else {}
    pack = retrieval.get("pack", {}) if isinstance(retrieval.get("pack", {}), dict) else {}
    for key in ("candidates_lexical", "candidates_vector", "candidates_union", "reranked", "final_topk"):
        if key in pack:
            pack[key] = []
    retrieval["pack"] = pack
    route["retrieval_v2"] = retrieval
    evidence = route.get("evidence_guard", {}) if isinstance(route.get("evidence_guard", {}), dict) else {}
    if isinstance(evidence.get("evidence"), dict):
        evidence["evidence"]["citations"] = []
    route["evidence_guard"] = evidence
    out["nl_skill_route"] = route

    event = out.get("event", {}) if isinstance(out.get("event", {}), dict) else {}
    if "attachments" in event:
        event["attachments"] = []
    out["event"] = event

    for key in ("attachments", "media", "files"):
        if key in out:
            out[key] = []

    out.setdefault("no_leak", {})["redacted"] = True
    return out


def is_tool_allowed(root: str | Path, *, agent_id: str, target: str) -> Dict[str, Any]:
    policy = load_guardrails(root)
    cfg = policy.get("tool_policy", {}) if isinstance(policy.get("tool_policy", {}), dict) else {}
    agents = cfg.get("agents", {}) if isinstance(cfg.get("agents", {}), dict) else {}
    default_cfg = cfg.get("default", {}) if isinstance(cfg.get("default", {}), dict) else {"allow": ["*"], "deny": []}
    agent_cfg = agents.get(str(agent_id).strip(), default_cfg) if isinstance(agents.get(str(agent_id).strip(), default_cfg), dict) else default_cfg
    allow = [str(x).strip() for x in agent_cfg.get("allow", ["*"]) if str(x).strip()]
    deny = [str(x).strip() for x in agent_cfg.get("deny", []) if str(x).strip()]
    if target in deny:
        return {"allowed": False, "reason": "deny_list", "agent_id": agent_id, "target": target}
    if "*" in allow or target in allow:
        return {"allowed": True, "reason": "allow_list", "agent_id": agent_id, "target": target}
    return {"allowed": False, "reason": "not_in_allow_list", "agent_id": agent_id, "target": target}

#!/usr/bin/env python3
"""Executable and auditable heuristic for recipe/skill creation decisions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/skill_creation_policy.json")
AUDIT_LOG_PATH = Path("logs/skill_creation_decisions.ndjson")
AUTOQUEUE_PATH = Path("state/skill_autocreate_queue.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "repeat_threshold_30d": 3,
    "impact_threshold": 7,
    "max_risk_for_auto_create": 5,
    "high_risk_requires_approval": 8,
    "weights": {
        "repeat": 0.30,
        "impact": 0.30,
        "generality": 0.20,
        "risk": 0.10,
        "latency_cost": 0.10,
    },
    "score_threshold_create": 0.65,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def observed_repeat_count_30d(root: str | Path, *, selected_target: str) -> int:
    canonical_root = get_canonical_root(root)
    path = canonical_root / AUDIT_LOG_PATH
    if not path.is_file() or not selected_target:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("selected_target", "")).strip() != selected_target:
                continue
            ts_raw = str(row.get("ts", "")).strip()
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                continue
            if ts >= cutoff:
                count += 1
    return count


def _upsert_autocreate_queue(root: Path, row: Dict[str, Any]) -> None:
    path = root / AUTOQUEUE_PATH
    payload = _load_json(path)
    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []

    target = str(row.get("selected_target", "")).strip()
    merged = False
    for item in items:
        if str(item.get("selected_target", "")).strip() == target:
            item.update(row)
            item["updated_at"] = _utc_now()
            merged = True
            break
    if not merged:
        row = dict(row)
        row["created_at"] = _utc_now()
        row["updated_at"] = _utc_now()
        items.append(row)

    out = {
        "updated_at": _utc_now(),
        "items": sorted(items, key=lambda x: (str(x.get("priority", "")), -_safe_float(x.get("score", 0), 0.0))),
    }
    _save_json(path, out)


def load_policy(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    payload = _load_json(canonical_root / POLICY_PATH)
    out = dict(DEFAULT_POLICY)
    out.update({k: payload.get(k) for k in DEFAULT_POLICY.keys() if k in payload and k != "weights"})
    weights = dict(DEFAULT_POLICY["weights"])
    if isinstance(payload.get("weights"), dict):
        for key in weights.keys():
            if key in payload["weights"]:
                weights[key] = _safe_float(payload["weights"][key], weights[key])
    out["weights"] = weights
    return out


def evaluate_creation(
    root: str | Path,
    *,
    route_type: str,
    selected_target: str,
    repeat_count_30d: int,
    impact_score: int,
    risk_score: int,
    generality_score: int = 5,
    latency_cost_score: int = 5,
    trace_id: str = "",
    suggested_name: str = "",
    pattern_key: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_policy(canonical_root)

    repeat = max(0, _safe_int(repeat_count_30d))
    impact = max(0, min(10, _safe_int(impact_score)))
    risk = max(0, min(10, _safe_int(risk_score)))
    generality = max(0, min(10, _safe_int(generality_score)))
    latency_cost = max(0, min(10, _safe_int(latency_cost_score)))

    repeat_norm = min(1.0, repeat / max(1, int(policy.get("repeat_threshold_30d", 3))))
    impact_norm = impact / 10.0
    generality_norm = generality / 10.0
    risk_safety_norm = 1.0 - (risk / 10.0)
    latency_eff_norm = 1.0 - (latency_cost / 10.0)

    w = policy["weights"]
    score = (
        repeat_norm * _safe_float(w.get("repeat", 0.30), 0.30)
        + impact_norm * _safe_float(w.get("impact", 0.30), 0.30)
        + generality_norm * _safe_float(w.get("generality", 0.20), 0.20)
        + risk_safety_norm * _safe_float(w.get("risk", 0.10), 0.10)
        + latency_eff_norm * _safe_float(w.get("latency_cost", 0.10), 0.10)
    )

    threshold_create = _safe_float(policy.get("score_threshold_create", 0.65), 0.65)
    hard_risk_limit = int(policy.get("max_risk_for_auto_create", 5))
    requires_approval = risk >= int(policy.get("high_risk_requires_approval", 8))

    if route_type not in {"tool", "workflow"}:
        decision = "defer"
        reason = "route_not_eligible"
    elif risk > hard_risk_limit:
        decision = "defer"
        reason = "risk_above_limit"
    elif score >= threshold_create:
        decision = "create"
        reason = "score_above_threshold"
    else:
        decision = "defer"
        reason = "score_below_threshold"

    out = {
        "eligible": decision == "create",
        "decision": decision,
        "reason": reason,
        "score": round(score, 4),
        "threshold_create": threshold_create,
        "requires_approval": requires_approval,
        "inputs": {
            "route_type": route_type,
            "selected_target": selected_target,
            "repeat_count_30d": repeat,
            "impact_score": impact,
            "risk_score": risk,
            "generality_score": generality,
            "latency_cost_score": latency_cost,
        },
        "components": {
            "repeat_norm": round(repeat_norm, 4),
            "impact_norm": round(impact_norm, 4),
            "generality_norm": round(generality_norm, 4),
            "risk_safety_norm": round(risk_safety_norm, 4),
            "latency_eff_norm": round(latency_eff_norm, 4),
        },
        "weights": w,
    }

    audit_row = {
        "ts": _utc_now(),
        "trace_id": trace_id,
        "selected_target": selected_target,
        "route_type": route_type,
        "decision": decision,
        "reason": reason,
        "score": out["score"],
        "inputs": out["inputs"],
    }
    _append_ndjson(canonical_root / AUDIT_LOG_PATH, audit_row)

    if decision == "create":
        priority = "high" if impact >= 8 else "medium" if impact >= 5 else "low"
        _upsert_autocreate_queue(
            canonical_root,
            {
                "selected_target": selected_target,
                "suggested_name": suggested_name or selected_target,
                "pattern_key": pattern_key or selected_target,
                "artifact_type": "skill" if str(suggested_name).startswith("skill.") else "workflow",
                "route_type": route_type,
                "score": out["score"],
                "priority": priority,
                "decision": decision,
                "reason": reason,
                "repeat_count_30d": repeat,
                "impact_score": impact,
                "risk_score": risk,
                "requires_approval": requires_approval,
                "status": "pending",
            },
        )

    return out

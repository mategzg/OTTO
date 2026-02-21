#!/usr/bin/env python3
"""Global circuit breaker + cooldown for router/tools/retrieval/jobs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/circuit_breaker_policy.json")
STATE_PATH = Path("state/circuit_breakers_state.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "resources": {
        "nl_router": {
            "enabled": True,
            "window_size": 20,
            "error_rate_open_threshold": 0.5,
            "latency_p95_open_ms": 1500,
            "timeout_open_count": 3,
            "cooldown_seconds": 120,
        },
        "tooling": {
            "enabled": True,
            "window_size": 20,
            "error_rate_open_threshold": 0.5,
            "latency_p95_open_ms": 2500,
            "timeout_open_count": 3,
            "cooldown_seconds": 180,
        },
        "retrieval": {
            "enabled": True,
            "window_size": 20,
            "error_rate_open_threshold": 0.5,
            "latency_p95_open_ms": 2000,
            "timeout_open_count": 3,
            "cooldown_seconds": 180,
        },
        "cron_jobs": {
            "enabled": True,
            "window_size": 20,
            "error_rate_open_threshold": 0.5,
            "latency_p95_open_ms": 3000,
            "timeout_open_count": 3,
            "cooldown_seconds": 300,
        },
    },
}

DEFAULT_STATE: Dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "resources": {},
}


def _resolve_root(root: str | Path) -> Path:
    candidate = Path(root)
    if candidate.exists() and (candidate / "CEO.md").is_file() and (candidate / "INDEX.md").is_file():
        return candidate.resolve()
    return get_canonical_root(root)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_policy(root: str | Path) -> Dict[str, Any]:
    canonical_root = _resolve_root(root)
    payload = _load_json(canonical_root / POLICY_PATH)
    out = dict(DEFAULT_POLICY)
    resources = dict(DEFAULT_POLICY["resources"])
    in_resources = payload.get("resources", {}) if isinstance(payload.get("resources"), dict) else {}
    for key, cfg in in_resources.items():
        if isinstance(cfg, dict):
            base = dict(resources.get(key, {}))
            base.update(cfg)
            resources[key] = base
    out["resources"] = resources
    if not (canonical_root / POLICY_PATH).exists():
        _save_json(canonical_root / POLICY_PATH, out)
    return out


def load_state(root: str | Path) -> Dict[str, Any]:
    canonical_root = _resolve_root(root)
    payload = _load_json(canonical_root / STATE_PATH)
    if not payload:
        payload = dict(DEFAULT_STATE)
    if not isinstance(payload.get("resources"), dict):
        payload["resources"] = {}
    return payload


def save_state(root: str | Path, state: Dict[str, Any]) -> None:
    canonical_root = _resolve_root(root)
    state["updated_at"] = _iso(_utc_now())
    _save_json(canonical_root / STATE_PATH, state)


def _resource_state(state: Dict[str, Any], resource: str) -> Dict[str, Any]:
    resources = state.setdefault("resources", {})
    r = resources.get(resource)
    if not isinstance(r, dict):
        r = {
            "status": "closed",
            "open_until": "",
            "events": [],
            "last_reason": "",
            "opened_count": 0,
        }
        resources[resource] = r
    if not isinstance(r.get("events"), list):
        r["events"] = []
    return r


def _percentile(values: List[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    idx = max(0, min(len(ordered) - 1, idx))
    return int(ordered[idx])


def should_allow(root: str | Path, *, resource: str) -> Dict[str, Any]:
    policy = load_policy(root)
    state = load_state(root)
    cfg = policy["resources"].get(resource, {})
    if not bool(cfg.get("enabled", False)):
        return {"allowed": True, "resource": resource, "status": "disabled"}

    r = _resource_state(state, resource)
    now = _utc_now()
    open_until = _parse_iso(str(r.get("open_until", "")))

    if str(r.get("status", "closed")) == "open" and open_until and now < open_until:
        return {
            "allowed": False,
            "resource": resource,
            "status": "open",
            "open_until": _iso(open_until),
            "reason": str(r.get("last_reason", "cooldown_active")),
        }

    if str(r.get("status", "closed")) == "open" and open_until and now >= open_until:
        r["status"] = "half_open"
        r["open_until"] = ""
        save_state(root, state)
        return {"allowed": True, "resource": resource, "status": "half_open"}

    return {"allowed": True, "resource": resource, "status": str(r.get("status", "closed"))}


def record_execution(
    root: str | Path,
    *,
    resource: str,
    success: bool,
    latency_ms: int,
    timed_out: bool = False,
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    policy = load_policy(root)
    state = load_state(root)
    cfg = policy["resources"].get(resource, {})
    if not bool(cfg.get("enabled", False)):
        return {"status": "disabled", "resource": resource}

    r = _resource_state(state, resource)
    events: List[Dict[str, Any]] = r.get("events", [])
    window_size = max(5, int(cfg.get("window_size", 20)))

    events.append(
        {
            "ts": _iso(_utc_now()),
            "success": bool(success),
            "latency_ms": max(0, int(latency_ms)),
            "timed_out": bool(timed_out),
            "meta": meta or {},
        }
    )
    if len(events) > window_size:
        events = events[-window_size:]
    r["events"] = events

    total = len(events)
    errors = sum(1 for e in events if not bool(e.get("success", False)))
    timeouts = sum(1 for e in events if bool(e.get("timed_out", False)))
    latencies = [int(e.get("latency_ms", 0)) for e in events]
    p95 = _percentile(latencies, 0.95)
    error_rate = (errors / total) if total > 0 else 0.0

    open_reason = ""
    if error_rate >= float(cfg.get("error_rate_open_threshold", 0.5)) and total >= min(5, window_size):
        open_reason = f"error_rate:{round(error_rate,3)}"
    elif p95 >= int(cfg.get("latency_p95_open_ms", 1500)) and total >= min(5, window_size):
        open_reason = f"latency_p95:{p95}"
    elif timeouts >= int(cfg.get("timeout_open_count", 3)):
        open_reason = f"timeouts:{timeouts}"

    if open_reason:
        cooldown = max(15, int(cfg.get("cooldown_seconds", 120)))
        r["status"] = "open"
        r["open_until"] = _iso(_utc_now() + timedelta(seconds=cooldown))
        r["last_reason"] = open_reason
        r["opened_count"] = int(r.get("opened_count", 0)) + 1
    elif str(r.get("status", "closed")) == "half_open" and success:
        r["status"] = "closed"
        r["open_until"] = ""
        r["last_reason"] = "recovered"

    save_state(root, state)
    return {
        "status": str(r.get("status", "closed")),
        "resource": resource,
        "error_rate": round(error_rate, 4),
        "latency_p95_ms": p95,
        "timeouts": timeouts,
        "open_until": str(r.get("open_until", "")),
        "last_reason": str(r.get("last_reason", "")),
    }

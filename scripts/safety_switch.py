#!/usr/bin/env python3
"""Global safety switch state for pausing autonomous processing."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

SWITCH_PATH = Path("state/safety_switch.json")
POLICY_PATH = Path("state/safety_policy.json")

DEFAULT_SWITCH: Dict[str, Any] = {
    "version": 1,
    "paused": False,
    "reason": "",
    "until_ts": "",
    "set_by": "",
    "last_change": "",
    "last_auto_trigger": "",
    "counters": {
        "hook_backlog_failures": 0,
        "hook_backlog_stall_ticks": 0,
        "autonomy_failures": 0,
    },
}

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "autopause_hours": 2,
    "hook_backlog_consecutive_failures_autopause": 3,
    "hook_backlog_pending_threshold": 300,
    "hook_backlog_stall_ticks_autopause": 3,
    "autonomy_consecutive_failures_autopause": 3,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_policy(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    path = canonical_root / POLICY_PATH
    policy = dict(DEFAULT_POLICY)
    policy.update(_load_json(path))
    if not path.is_file():
        _save_json(path, policy)
    return policy


def load_switch(root: str | Path, *, create_if_missing: bool = True) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    path = canonical_root / SWITCH_PATH
    payload = dict(DEFAULT_SWITCH)
    payload.update(_load_json(path))
    if not isinstance(payload.get("counters", {}), dict):
        payload["counters"] = dict(DEFAULT_SWITCH["counters"])
    else:
        merged = dict(DEFAULT_SWITCH["counters"])
        merged.update(payload["counters"])
        payload["counters"] = merged
    if create_if_missing and not path.is_file():
        _save_json(path, payload)
    return payload


def save_switch(root: str | Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    _save_json(canonical_root / SWITCH_PATH, payload)
    return payload


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def get_safety_status(root: str | Path, *, auto_expire: bool = True) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = load_switch(canonical_root)
    now = _utc_now()
    until = _parse_iso(str(state.get("until_ts", "")))
    expired = bool(state.get("paused", False)) and until is not None and now >= until
    if auto_expire and expired:
        state["paused"] = False
        state["reason"] = ""
        state["until_ts"] = ""
        state["set_by"] = "auto_expire"
        state["last_change"] = now.isoformat()
        save_switch(canonical_root, state)
    return {
        "canonical_root": str(canonical_root.resolve()),
        "paused": bool(state.get("paused", False)),
        "reason": str(state.get("reason", "")),
        "until_ts": str(state.get("until_ts", "")),
        "set_by": str(state.get("set_by", "")),
        "last_change": str(state.get("last_change", "")),
        "last_auto_trigger": str(state.get("last_auto_trigger", "")),
        "counters": dict(state.get("counters", {})),
        "expired": expired,
        "version": 1,
    }


def pause_switch(
    root: str | Path,
    *,
    hours: int,
    reason: str,
    set_by: str = "manual",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = load_switch(canonical_root)
    now = _utc_now()
    until = now + timedelta(hours=max(1, int(hours)))
    state["paused"] = True
    state["reason"] = reason.strip()[:300]
    state["until_ts"] = until.isoformat()
    state["set_by"] = set_by.strip()[:80] or "manual"
    state["last_change"] = now.isoformat()
    if set_by.strip().lower().startswith("auto"):
        state["last_auto_trigger"] = now.isoformat()
    save_switch(canonical_root, state)
    return get_safety_status(canonical_root, auto_expire=False)


def resume_switch(root: str | Path, *, reason: str = "", set_by: str = "manual") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = load_switch(canonical_root)
    now = _utc_now()
    state["paused"] = False
    state["reason"] = reason.strip()[:300]
    state["until_ts"] = ""
    state["set_by"] = set_by.strip()[:80] or "manual"
    state["last_change"] = now.isoformat()
    save_switch(canonical_root, state)
    return get_safety_status(canonical_root, auto_expire=False)


def autopause_switch(root: str | Path, *, reason: str, hours: int | None = None) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_policy(canonical_root)
    duration = int(hours if hours is not None else policy.get("autopause_hours", 2))
    return pause_switch(
        canonical_root,
        hours=max(1, duration),
        reason=reason,
        set_by="auto",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Global safety switch")
    parser.add_argument("--root", default=".")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--pause", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--hours", type=int, default=2)
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    if args.pause:
        out = pause_switch(args.root, hours=max(1, args.hours), reason=args.reason or "manual_pause", set_by="manual")
    elif args.resume:
        out = resume_switch(args.root, reason=args.reason or "manual_resume", set_by="manual")
    else:
        out = get_safety_status(args.root, auto_expire=True)

    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

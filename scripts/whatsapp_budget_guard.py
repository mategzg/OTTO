#!/usr/bin/env python3
"""WhatsApp budget guard: refresh 5h usage snapshot and release held events."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/channel_runtime_policy.json")
USAGE_STATE_PATH = Path("state/model_usage_guard.json")
HOLD_QUEUE_PATH = Path("state/whatsapp_hold_queue.ndjson")


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


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_ndjson(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_ndjson(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _guard_cfg(root: Path) -> Dict[str, Any]:
    policy = _load_json(root / POLICY_PATH)
    cfg = policy.get("whatsapp_runtime_guard", {}) if isinstance(policy, dict) else {}
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "min_5h_remaining_pct": int(cfg.get("min_5h_remaining_pct", 50)),
    }


def refresh_usage_state(root: Path) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            ["openclaw", "status"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
    except Exception as exc:
        out = {
            "updated_at": _utc_now(),
            "status": "error",
            "error": f"openclaw_status_failed:{exc}",
            "five_hour_remaining_pct": None,
        }
        _save_json(root / USAGE_STATE_PATH, out)
        return out

    merged = (proc.stdout or "") + "\n" + (proc.stderr or "")
    m = re.search(r"Usage:\s*5h\s*(\d+)%\s*left", merged)
    pct = int(m.group(1)) if m else None
    if pct is None:
        prev = _load_json(root / USAGE_STATE_PATH)
        prev_pct = prev.get("five_hour_remaining_pct")
        if isinstance(prev_pct, int):
            out = {
                "updated_at": _utc_now(),
                "status": "ok" if proc.returncode == 0 else "warn",
                "five_hour_remaining_pct": prev_pct,
                "raw_matched": False,
                "fallback": "preserve_previous",
            }
            _save_json(root / USAGE_STATE_PATH, out)
            return out
    out = {
        "updated_at": _utc_now(),
        "status": "ok" if proc.returncode == 0 else "warn",
        "five_hour_remaining_pct": pct,
        "raw_matched": bool(m),
    }
    _save_json(root / USAGE_STATE_PATH, out)
    return out


def release_hold_queue(root: Path, *, max_events: int = 50) -> Dict[str, Any]:
    from scripts.channel_ingress_adapter import handle_runtime_event

    cfg = _guard_cfg(root)
    usage = _load_json(root / USAGE_STATE_PATH)
    pct = usage.get("five_hour_remaining_pct")
    if not cfg["enabled"]:
        return {"status": "guard_disabled", "released": 0}
    if not isinstance(pct, int):
        return {"status": "no_usage_data", "released": 0}
    if pct < int(cfg["min_5h_remaining_pct"]):
        return {"status": "below_threshold", "released": 0, "remaining_pct": pct}

    rows = _read_ndjson(root / HOLD_QUEUE_PATH)
    if not rows:
        return {"status": "empty", "released": 0}

    released = 0
    keep: List[Dict[str, Any]] = []
    for row in rows:
        if released >= max_events:
            keep.append(row)
            continue
        event = row.get("event", {}) if isinstance(row.get("event", {}), dict) else {}
        if not event:
            continue
        event.setdefault("metadata", {})
        if isinstance(event.get("metadata"), dict):
            event["metadata"]["budget_replay"] = True
        try:
            handle_runtime_event(root, event)
            released += 1
        except Exception:
            keep.append(row)

    _write_ndjson(root / HOLD_QUEUE_PATH, keep)
    return {"status": "released", "released": released, "remaining": len(keep), "remaining_pct": pct}


def main() -> int:
    parser = argparse.ArgumentParser(description="WhatsApp budget guard helper")
    parser.add_argument("--root", default=".")
    parser.add_argument("--refresh-usage", action="store_true")
    parser.add_argument("--release-hold", action="store_true")
    parser.add_argument("--set-remaining-pct", type=int, default=-1)
    parser.add_argument("--max-events", type=int, default=50)
    args = parser.parse_args()

    root = get_canonical_root(args.root)
    out: Dict[str, Any] = {}
    if args.set_remaining_pct >= 0:
        pct = max(0, min(100, int(args.set_remaining_pct)))
        payload = {
            "updated_at": _utc_now(),
            "status": "manual",
            "five_hour_remaining_pct": pct,
            "raw_matched": True,
        }
        _save_json(root / USAGE_STATE_PATH, payload)
        out["set"] = payload
    if args.refresh_usage:
        out["refresh"] = refresh_usage_state(root)
    if args.release_hold:
        out["release"] = release_hold_queue(root, max_events=max(1, args.max_events))
    if not args.refresh_usage and not args.release_hold and args.set_remaining_pct < 0:
        parser.error("Use --refresh-usage and/or --release-hold and/or --set-remaining-pct")
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

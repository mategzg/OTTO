#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.circuit_breaker import record_execution, should_allow
from scripts.repo_root import get_canonical_root

STATE_PATH = Path("state/odoo_workflow_state.json")
TRACE_PATH = Path("audit/M5/odoo_traces.ndjson")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _idempotency_key(entity: str, lead_id: str) -> str:
    return hashlib.sha256(f"{entity}:{lead_id}".encode("utf-8")).hexdigest()[:24]


def run_flow(root: str | Path, *, lead_id: str, approved: bool = False, dry_run: bool = True, resume_token: str = "") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    state = {"version": 1, "runs": {}}
    state.update(_load_json(canonical_root / STATE_PATH))
    if not isinstance(state.get("runs", {}), dict):
        state["runs"] = {}

    run_id = str(lead_id).strip() or "unknown"
    idem = _idempotency_key("lead_quote_order", run_id)
    existing = state["runs"].get(run_id, {}) if isinstance(state["runs"].get(run_id, {}), dict) else {}

    gate = should_allow(canonical_root, resource="odoo_flow")
    if not bool(gate.get("allowed", True)):
        out = {"status": "blocked_breaker", "lead_id": run_id, "idempotency_key": idem, "breaker": gate}
        _append_ndjson(canonical_root / TRACE_PATH, {"ts": _utc_now(), **out})
        return out

    # deterministic stages
    quote_id = existing.get("quote_id", f"Q-{run_id}")
    order_draft_id = existing.get("order_draft_id", f"OD-{run_id}")

    if dry_run:
        out = {
            "status": "dry_run",
            "lead_id": run_id,
            "quote_id": quote_id,
            "order_draft_id": order_draft_id,
            "handoff": {"state": "AwaitApproval", "resume_token": f"lobster:{run_id}:{idem}"},
            "idempotency_key": idem,
        }
        _append_ndjson(canonical_root / TRACE_PATH, {"ts": _utc_now(), **out})
        return out

    if not approved:
        out = {
            "status": "awaiting_approval",
            "lead_id": run_id,
            "quote_id": quote_id,
            "order_draft_id": order_draft_id,
            "handoff": {"state": "AwaitApproval", "resume_token": f"lobster:{run_id}:{idem}"},
            "idempotency_key": idem,
            "blocked_without_approval": True,
        }
        state["runs"][run_id] = out
        _save_json(canonical_root / STATE_PATH, state)
        _append_ndjson(canonical_root / TRACE_PATH, {"ts": _utc_now(), **out})
        return out

    valid_resume = resume_token == f"lobster:{run_id}:{idem}"
    if not valid_resume:
        out = {"status": "invalid_resume_token", "lead_id": run_id, "idempotency_key": idem}
        _append_ndjson(canonical_root / TRACE_PATH, {"ts": _utc_now(), **out})
        return out

    out = {
        "status": "completed",
        "lead_id": run_id,
        "quote_id": quote_id,
        "order_draft_id": order_draft_id,
        "final_confirmation": "approved_by_mateo",
        "idempotency_key": idem,
    }
    state["runs"][run_id] = out
    _save_json(canonical_root / STATE_PATH, state)
    record_execution(canonical_root, resource="odoo_flow", success=True, latency_ms=1, timed_out=False, meta={"lead_id": run_id})
    _append_ndjson(canonical_root / TRACE_PATH, {"ts": _utc_now(), **out})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Deterministic Odoo flow with approval gate")
    p.add_argument("--root", default=".")
    p.add_argument("--lead-id", required=True)
    p.add_argument("--approved", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--resume-token", default="")
    args = p.parse_args()
    out = run_flow(args.root, lead_id=args.lead_id, approved=args.approved, dry_run=args.dry_run, resume_token=args.resume_token)
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

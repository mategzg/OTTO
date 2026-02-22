#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.circuit_breaker import record_execution, should_allow
from scripts.repo_root import get_canonical_root

REPORT_PATH = Path("audit/M7/breaker_fault_injection.json")
SAMPLES_PATH = Path("audit/M7/heartbeat_samples.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def heartbeat_reply(has_alert: bool, alert_text: str = "") -> str:
    if not has_alert:
        return "HEARTBEAT_OK"
    return alert_text.strip() or "ALERT"


def cron_session_id(job_id: str) -> str:
    clean = "".join(c for c in str(job_id) if c.isalnum() or c in "-_:")
    return f"cron:{clean or 'job'}"


def run_fault_injection(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    before = {
        "router": should_allow(canonical_root, resource="nl_router"),
        "tooling": should_allow(canonical_root, resource="tooling"),
        "cron_jobs": should_allow(canonical_root, resource="cron_jobs"),
    }
    for _ in range(4):
        record_execution(canonical_root, resource="cron_jobs", success=False, latency_ms=900, timed_out=True, meta={"fault": "injected"})
    after = {
        "router": should_allow(canonical_root, resource="nl_router"),
        "tooling": should_allow(canonical_root, resource="tooling"),
        "cron_jobs": should_allow(canonical_root, resource="cron_jobs"),
    }

    out = {
        "status": "ok",
        "created_at": _utc_now(),
        "before": before,
        "after": after,
        "cross_surface_breaker": {
            "router_allowed": bool(after["router"].get("allowed", True)),
            "tooling_allowed": bool(after["tooling"].get("allowed", True)),
            "cron_allowed": bool(after["cron_jobs"].get("allowed", True)),
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    samples = {
        "created_at": _utc_now(),
        "heartbeat_no_alert": heartbeat_reply(False),
        "heartbeat_with_alert": heartbeat_reply(True, "⚠️ alerta de prueba"),
        "cron_session_example": cron_session_id("sharepoint-sync"),
    }
    SAMPLES_PATH.write_text(json.dumps(samples, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Day-2 autonomy probes")
    p.add_argument("--root", default=".")
    args = p.parse_args()
    out = run_fault_injection(args.root)
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

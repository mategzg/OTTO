#!/usr/bin/env python3
"""Lightweight observability telemetry for SPEC-002 M5."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

EVENTS_PATH = Path("logs/observability_events.ndjson")
SUMMARY_PATH = Path("docs/_inbox/observability_summary_latest.json")


def _resolve_root(root: str | Path) -> Path:
    candidate = Path(root)
    if candidate.exists() and (candidate / "CEO.md").is_file() and (candidate / "INDEX.md").is_file():
        return candidate.resolve()
    return get_canonical_root(root)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_ndjson(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _percentile(values: List[int], p: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * p))
    idx = max(0, min(len(ordered) - 1, idx))
    return int(ordered[idx])


def _write_summary(root: Path) -> None:
    rows = _read_ndjson(root / EVENTS_PATH)[-500:]
    if not rows:
        return

    latencies = [int(r.get("latency_ms", 0)) for r in rows if "latency_ms" in r]
    total = len(rows)
    router_total = sum(1 for r in rows if str(r.get("kind", "")) == "nl_router")
    router_ok = sum(1 for r in rows if str(r.get("kind", "")) == "nl_router" and bool(r.get("success", False)))
    tool_total = sum(1 for r in rows if str(r.get("kind", "")) == "tooling")
    tool_ok = sum(1 for r in rows if str(r.get("kind", "")) == "tooling" and bool(r.get("success", False)))
    retrieval_total = sum(1 for r in rows if str(r.get("kind", "")) == "retrieval")
    retrieval_hit = sum(1 for r in rows if str(r.get("kind", "")) == "retrieval" and bool(r.get("retrieval_hit", False)))
    retries = sum(int(r.get("retry_count", 0)) for r in rows)
    tokens = sum(int(r.get("token_estimate", 0)) for r in rows)

    summary = {
        "updated_at": _utc_now(),
        "window_events": total,
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
        },
        "rates": {
            "router_success_rate": round((router_ok / router_total), 4) if router_total else 0.0,
            "tool_success_rate": round((tool_ok / tool_total), 4) if tool_total else 0.0,
            "retrieval_hit_rate": round((retrieval_hit / retrieval_total), 4) if retrieval_total else 0.0,
            "retry_rate": round((retries / total), 4) if total else 0.0,
            "groundedness_rate": round((retrieval_hit / retrieval_total), 4) if retrieval_total else 0.0,
        },
        "cost": {
            "token_estimate": tokens,
        },
        "version": 1,
    }

    (root / SUMMARY_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / SUMMARY_PATH).write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def record_event(root: str | Path, event: Dict[str, Any]) -> None:
    canonical_root = _resolve_root(root)
    row = dict(event)
    row.setdefault("ts", _utc_now())
    _append_ndjson(canonical_root / EVENTS_PATH, row)
    _write_summary(canonical_root)

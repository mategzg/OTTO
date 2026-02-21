#!/usr/bin/env python3
"""Run golden-set regression for SPEC-002 and emit deterministic reports."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.nl_skill_router import run_nl_router
from scripts.repo_root import get_canonical_root

GOLDEN_PATH = Path("state/golden_set_spec002.json")
REPORT_JSON = Path("docs/_inbox/golden_regression_latest.json")
REPORT_MD = Path("docs/_inbox/golden_regression_latest.md")
LOG_NDJSON = Path("logs/golden_regression_runs.ndjson")


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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def run_golden_regression(root: str | Path, *, fail_on_degradation: bool = False) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    golden = _load_json(canonical_root / GOLDEN_PATH)
    items = golden.get("items", []) if isinstance(golden.get("items"), list) else []

    checks: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        q = str(item.get("question", "")).strip()
        if not q:
            continue
        out = run_nl_router(
            canonical_root,
            text=q,
            channel="telegram",
            conversation_id="golden",
            thread_id="spec002",
            message_id=str(item.get("id", f"g{idx+1}")),
        )
        plan = out.get("plan", {}) if isinstance(out.get("plan"), dict) else {}
        intent_ok = str(plan.get("intent_id", "")) == str(item.get("expected_intent", ""))
        route_ok = str(plan.get("route_type", "")) == str(item.get("expected_route_type", ""))
        target_ok = str(plan.get("selected_target", "")) == str(item.get("expected_target", ""))
        checks.append(
            {
                "id": item.get("id", ""),
                "question": q,
                "expected": {
                    "intent": item.get("expected_intent", ""),
                    "route_type": item.get("expected_route_type", ""),
                    "target": item.get("expected_target", ""),
                },
                "actual": {
                    "status": out.get("status", ""),
                    "intent": plan.get("intent_id", ""),
                    "route_type": plan.get("route_type", ""),
                    "target": plan.get("selected_target", ""),
                },
                "scores": {
                    "intent": 1 if intent_ok else 0,
                    "route_type": 1 if route_ok else 0,
                    "target": 1 if target_ok else 0,
                },
                "pass": bool(intent_ok and route_ok and target_ok),
            }
        )

    total = len(checks)
    passed = sum(1 for c in checks if c.get("pass"))
    intent_hits = sum(int(c.get("scores", {}).get("intent", 0)) for c in checks)
    route_hits = sum(int(c.get("scores", {}).get("route_type", 0)) for c in checks)
    target_hits = sum(int(c.get("scores", {}).get("target", 0)) for c in checks)

    ndcg_proxy = round((route_hits + target_hits) / max(1, 2 * total), 4)
    mrr_proxy = round(sum(1.0 if c.get("pass") else 0.5 if c.get("scores", {}).get("route_type", 0) else 0.0 for c in checks) / max(1, total), 4)
    groundedness = round(target_hits / max(1, total), 4)

    report = {
        "created_at": _utc_now(),
        "status": "pass" if passed == total else "degraded",
        "summary": {
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / max(1, total), 4),
            "metrics": {
                "ndcg": ndcg_proxy,
                "mrr": mrr_proxy,
                "groundedness": groundedness,
            },
        },
        "checks": checks,
        "version": 1,
    }

    _save_json(canonical_root / REPORT_JSON, report)
    _append_ndjson(canonical_root / LOG_NDJSON, report)

    lines = [
        "# Golden Regression Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Total: `{total}`",
        f"- Passed: `{passed}`",
        f"- Pass rate: `{report['summary']['pass_rate']}`",
        f"- nDCG: `{ndcg_proxy}`",
        f"- MRR: `{mrr_proxy}`",
        f"- Groundedness: `{groundedness}`",
    ]
    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

    if fail_on_degradation and report["status"] != "pass":
        raise RuntimeError("Golden regression degraded")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SPEC-002 golden regression")
    parser.add_argument("--root", default=".")
    parser.add_argument("--fail-on-degradation", action="store_true")
    args = parser.parse_args()

    out = run_golden_regression(args.root, fail_on_degradation=args.fail_on_degradation)
    print(json.dumps({"status": out.get("status"), "summary": out.get("summary", {})}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

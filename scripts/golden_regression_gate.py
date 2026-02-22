#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.golden_regression_runner import run_golden_regression
from scripts.repo_root import get_canonical_root

THRESHOLDS_PATH = Path("state/golden_regression_thresholds.json")
REPORT_PATH = Path("docs/_inbox/golden_regression_gate_latest.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def run_gate(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    thresholds = _load_json(canonical_root / THRESHOLDS_PATH)
    golden = run_golden_regression(canonical_root, fail_on_degradation=False)

    summary = golden.get("summary", {}) if isinstance(golden.get("summary"), dict) else {}
    metrics = summary.get("metrics", {}) if isinstance(summary.get("metrics"), dict) else {}

    checks: List[Dict[str, Any]] = [
        {"name": "min_total", "ok": int(summary.get("total", 0)) >= int(thresholds.get("min_total", 50)), "actual": int(summary.get("total", 0)), "required": int(thresholds.get("min_total", 50))},
        {"name": "min_pass_rate", "ok": float(summary.get("pass_rate", 0.0)) >= float(thresholds.get("min_pass_rate", 0.95)), "actual": float(summary.get("pass_rate", 0.0)), "required": float(thresholds.get("min_pass_rate", 0.95))},
        {"name": "min_ndcg", "ok": float(metrics.get("ndcg", 0.0)) >= float(thresholds.get("min_ndcg", 0.95)), "actual": float(metrics.get("ndcg", 0.0)), "required": float(thresholds.get("min_ndcg", 0.95))},
        {"name": "min_mrr", "ok": float(metrics.get("mrr", 0.0)) >= float(thresholds.get("min_mrr", 0.95)), "actual": float(metrics.get("mrr", 0.0)), "required": float(thresholds.get("min_mrr", 0.95))},
        {"name": "min_groundedness", "ok": float(metrics.get("groundedness", 0.0)) >= float(thresholds.get("min_groundedness", 0.95)), "actual": float(metrics.get("groundedness", 0.0)), "required": float(thresholds.get("min_groundedness", 0.95))},
    ]

    ok = all(c["ok"] for c in checks)
    out = {
        "status": "pass" if ok else "fail",
        "checks": checks,
        "golden_summary": summary,
        "thresholds": thresholds,
        "version": 1,
    }
    p = canonical_root / REPORT_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Golden regression quality gate")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    out = run_gate(args.root)
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if out.get("status") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())

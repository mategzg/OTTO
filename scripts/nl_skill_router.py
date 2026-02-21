#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.nl_intent_classifier import classify_intent
from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/skill_creation_policy.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "repeat_threshold_30d": 3,
    "impact_threshold": 7,
    "max_risk_for_auto_create": 5,
    "high_risk_requires_approval": 8,
}

INTENT_ROUTE_MAP: Dict[str, Dict[str, str]] = {
    "status_request": {"route_type": "workflow", "selected_target": "status.check"},
    "reminder_request": {"route_type": "skill", "selected_target": "reminder.create"},
    "research_request": {"route_type": "skill", "selected_target": "research.request"},
    "odoo_cotizar": {"route_type": "skill", "selected_target": "odoo.cotizar"},
    "odoo_stock": {"route_type": "skill", "selected_target": "odoo.stock"},
    "odoo_cliente": {"route_type": "skill", "selected_target": "odoo.cliente"},
    "odoo_factura": {"route_type": "skill", "selected_target": "odoo.factura"},
    "odoo_pago": {"route_type": "skill", "selected_target": "odoo.pago"},
    "odoo_cuenta": {"route_type": "skill", "selected_target": "odoo.cuenta"},
    "odoo_reporte": {"route_type": "skill", "selected_target": "odoo.reporte"},
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _policy(root: Path) -> Dict[str, Any]:
    payload = _load_json(root / POLICY_PATH)
    out = dict(DEFAULT_POLICY)
    out.update({k: payload.get(k) for k in DEFAULT_POLICY.keys() if k in payload})
    return out


def _domain_for_intent(intent: str) -> str:
    if intent.startswith("odoo_"):
        return "sg_acabados"
    if intent in {"research_request", "reminder_request", "status_request"}:
        return "openclaw_ops"
    return "personal_ops"


def route_request(
    root: str | Path,
    *,
    text: str,
    channel: str = "",
    attachments: List[Dict[str, Any]] | None = None,
    repeat_count_30d: int = 0,
    impact_score: int = 0,
    risk_score: int = 0,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    pol = _policy(canonical_root)
    attachments = attachments or []

    intent = classify_intent(text=text, attachments=attachments, channel=channel).get("intent", "chat_normal")
    route = INTENT_ROUTE_MAP.get(intent, {"route_type": "tool", "selected_target": "rag.answer"})

    requires_approval = int(risk_score) >= int(pol.get("high_risk_requires_approval", 8))

    eligible = (
        int(repeat_count_30d) >= int(pol.get("repeat_threshold_30d", 3))
        and int(impact_score) >= int(pol.get("impact_threshold", 7))
        and int(risk_score) <= int(pol.get("max_risk_for_auto_create", 5))
    )

    if eligible and route["route_type"] in {"tool", "workflow"}:
        create_decision = "create"
    else:
        create_decision = "defer"

    return {
        "intent_id": intent,
        "confidence": 0.8,
        "route_type": route["route_type"],
        "selected_target": route["selected_target"],
        "domain": _domain_for_intent(intent),
        "reasons": [
            f"intent={intent}",
            f"repeat_count_30d={repeat_count_30d}",
            f"impact_score={impact_score}",
            f"risk_score={risk_score}",
        ],
        "risk_level": "high" if int(risk_score) >= 8 else "medium" if int(risk_score) >= 4 else "low",
        "requires_approval": requires_approval,
        "fallback_plan": {
            "on_cooldown": "read_only_backlog",
            "on_missing_handoff": "block_fix_retry",
        },
        "cost_estimate": {
            "tokens": "high" if route["route_type"] == "tool" else "medium",
            "latency": "high" if route["route_type"] == "tool" else "medium",
        },
        "create_skill_decision": {
            "eligible": eligible,
            "repeat_count_30d": int(repeat_count_30d),
            "impact_score": int(impact_score),
            "risk_score": int(risk_score),
            "decision": create_decision,
        },
        "version": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Natural-language skill router MVP")
    parser.add_argument("--root", default=".")
    parser.add_argument("--text", required=True)
    parser.add_argument("--channel", default="")
    parser.add_argument("--repeat-count-30d", type=int, default=0)
    parser.add_argument("--impact-score", type=int, default=0)
    parser.add_argument("--risk-score", type=int, default=0)
    args = parser.parse_args()

    out = route_request(
        args.root,
        text=args.text,
        channel=args.channel,
        repeat_count_30d=args.repeat_count_30d,
        impact_score=args.impact_score,
        risk_score=args.risk_score,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

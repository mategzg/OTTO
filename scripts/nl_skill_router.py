#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from scripts.circuit_breaker import record_execution, should_allow
from scripts.nl_intent_classifier import classify_intent
from scripts.observability import record_event
from scripts.repo_root import get_canonical_root
from scripts.retrieval_service import retrieve as retrieval_v2_retrieve
from scripts.skill_creation_heuristics import evaluate_creation
from scripts.skill_recipe_registry import ensure_default_registries, resolve_target

POLICY_PATH = Path("state/skill_creation_policy.json")
RETRIEVAL_POLICY_PATH = Path("state/retrieval_policy.json")

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


def _retrieval_v2_enabled(root: Path) -> bool:
    payload = _load_json(root / RETRIEVAL_POLICY_PATH)
    cfg = payload.get("retrieval_v2", {}) if isinstance(payload.get("retrieval_v2"), dict) else {}
    return bool(cfg.get("enabled", False))


def _domain_for_intent(intent: str) -> str:
    if intent.startswith("odoo_"):
        return "sg_acabados"
    if intent in {"research_request", "reminder_request", "status_request"}:
        return "openclaw_ops"
    return "personal_ops"


def _build_idempotency_key(
    *,
    channel: str,
    conversation_id: str,
    thread_id: str,
    message_id: str,
    text: str,
) -> str:
    basis = "|".join([
        channel.strip().lower(),
        conversation_id.strip(),
        thread_id.strip(),
        message_id.strip(),
        text.strip(),
    ])
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"nlr:{digest[:24]}"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def run_nl_router(
    root: str | Path,
    *,
    text: str,
    channel: str = "",
    attachments: List[Dict[str, Any]] | None = None,
    repeat_count_30d: int = 0,
    impact_score: int = 0,
    risk_score: int = 0,
    conversation_id: str = "",
    thread_id: str = "",
    message_id: str = "",
    timeout_ms: int = 1500,
    cancel_requested: bool = False,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    ensure_default_registries(canonical_root)
    started = time.monotonic()
    timeout_ms = max(50, _safe_int(timeout_ms, 1500))
    attachments = attachments or []

    idempotency_key = _build_idempotency_key(
        channel=channel,
        conversation_id=conversation_id,
        thread_id=thread_id,
        message_id=message_id,
        text=text,
    )

    def _obs(status: str, *, success: bool, elapsed_ms: int, route_type: str = "", selected_target: str = "", retry_count: int = 0) -> None:
        record_event(
            canonical_root,
            {
                "kind": "nl_router",
                "trace_id": idempotency_key,
                "channel": channel,
                "status": status,
                "success": success,
                "latency_ms": max(0, int(elapsed_ms)),
                "route_type": route_type,
                "selected_target": selected_target,
                "retry_count": max(0, int(retry_count)),
                "token_estimate": max(1, len(text) // 4),
            },
        )
        if route_type == "tool" and selected_target == "rag.answer":
            record_event(
                canonical_root,
                {
                    "kind": "retrieval",
                    "trace_id": idempotency_key,
                    "channel": channel,
                    "success": success,
                    "latency_ms": max(0, int(elapsed_ms)),
                    "retrieval_hit": bool(success),
                    "token_estimate": max(1, len(text) // 8),
                },
            )

    if cancel_requested:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        record_execution(
            canonical_root,
            resource="nl_router",
            success=True,
            latency_ms=elapsed_ms,
            timed_out=False,
            meta={"status": "cancelled"},
        )
        _obs("cancelled", success=True, elapsed_ms=elapsed_ms)
        return {
            "status": "cancelled",
            "idempotency_key": idempotency_key,
            "error": {"code": "cancelled", "message": "router execution cancelled before classification"},
            "version": 2,
        }

    breaker_gate = should_allow(canonical_root, resource="nl_router")
    if not bool(breaker_gate.get("allowed", True)):
        _obs("cooldown", success=False, elapsed_ms=int((time.monotonic() - started) * 1000))
        return {
            "status": "cooldown",
            "idempotency_key": idempotency_key,
            "error": {
                "code": "circuit_open",
                "message": "nl_router in cooldown, using safe fallback",
            },
            "fallback": {
                "route_type": "tool",
                "selected_target": "rag.answer",
                "mode": "no_verificado_with_next_action",
            },
            "circuit_breaker": breaker_gate,
            "version": 2,
        }
    def _ensure_timeout(stage: str) -> None:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if elapsed_ms > timeout_ms:
            raise TimeoutError(f"timeout at stage={stage} elapsed_ms={elapsed_ms} timeout_ms={timeout_ms}")

    try:
        _ensure_timeout("pre_classification")
        classification = classify_intent(text=text, attachments=attachments, channel=channel)
        intent = str(classification.get("primary_intent", "chat_normal")).strip() or "chat_normal"

        _ensure_timeout("post_classification")
        route = INTENT_ROUTE_MAP.get(intent, {"route_type": "tool", "selected_target": "rag.answer"})
        resolution = resolve_target(
            canonical_root,
            route_type=route["route_type"],
            selected_target=route["selected_target"],
            channel=channel,
        )
        if not bool(resolution.get("ok", False)):
            fallback = resolution.get("fallback", {"route_type": "tool", "selected_target": "rag.answer"})
            route = {
                "route_type": str(fallback.get("route_type", "tool")),
                "selected_target": str(fallback.get("selected_target", "rag.answer")),
            }

        pol = _policy(canonical_root)

        repeat = _safe_int(repeat_count_30d)
        impact = _safe_int(impact_score)
        risk = _safe_int(risk_score)
        requires_approval = risk >= int(pol.get("high_risk_requires_approval", 8))

        creation_eval = evaluate_creation(
            canonical_root,
            route_type=route["route_type"],
            selected_target=route["selected_target"],
            repeat_count_30d=repeat,
            impact_score=impact,
            risk_score=risk,
            trace_id=idempotency_key,
        )

        plan = {
            "intent_id": intent,
            "confidence": classification.get("confidence", "medium"),
            "route_type": route["route_type"],
            "selected_target": route["selected_target"],
            "domain": _domain_for_intent(intent),
            "reasons": [
                f"intent={intent}",
                f"repeat_count_30d={repeat}",
                f"impact_score={impact}",
                f"risk_score={risk}",
                f"registry_resolution={'ok' if resolution.get('ok') else resolution.get('reason', 'fallback')}",
            ],
            "risk_level": "high" if risk >= 8 else "medium" if risk >= 4 else "low",
            "requires_approval": requires_approval,
            "fallback_plan": {
                "on_cooldown": "read_only_backlog",
                "on_missing_handoff": "block_fix_retry",
                "on_low_grounding": "no_verificado_with_next_action",
            },
            "cost_estimate": {
                "tokens": "high" if route["route_type"] == "tool" else "medium",
                "latency": "high" if route["route_type"] == "tool" else "medium",
            },
            "create_skill_decision": creation_eval,
            "registry": {
                "checked": True,
                "resolution": resolution,
            },
        }

        retrieval_v2 = {
            "enabled": _retrieval_v2_enabled(canonical_root),
            "pack": {},
        }
        if retrieval_v2["enabled"] and plan["route_type"] == "tool" and plan["selected_target"] == "rag.answer":
            retrieval_v2["pack"] = retrieval_v2_retrieve(
                canonical_root,
                query=text,
                principal_ctx={"channel": channel, "conversation_id": conversation_id},
                retrieval_mode="grounded_answer",
                filters={},
            )

        _ensure_timeout("post_planning")
        elapsed_ms = int((time.monotonic() - started) * 1000)
        breaker_status = record_execution(
            canonical_root,
            resource="nl_router",
            success=True,
            latency_ms=elapsed_ms,
            timed_out=False,
            meta={"status": "success", "target": plan["selected_target"]},
        )
        _obs("success", success=True, elapsed_ms=elapsed_ms, route_type=plan["route_type"], selected_target=plan["selected_target"])
        return {
            "status": "success",
            "idempotency_key": idempotency_key,
            "contracts": {
                "input": {
                    "channel": channel,
                    "conversation_id": conversation_id,
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "attachment_count": len(attachments),
                },
                "execution": {
                    "timeout_ms": timeout_ms,
                    "cancel_requested": cancel_requested,
                    "idempotent": True,
                },
            },
            "classification": classification,
            "plan": plan,
            "execution": {
                "selected_target": plan["selected_target"],
                "route_type": plan["route_type"],
                "status": "planned",
            },
            "retrieval_v2": retrieval_v2,
            "grounded_response": {
                "mode": "evidence_first",
                "status": "pending_execution",
                "required_if_critical": ["direct_answer", "evidence", "confidence", "gaps", "actions_executed"],
            },
            "timing": {
                "elapsed_ms": elapsed_ms,
            },
            "circuit_breaker": breaker_status,
            "version": 2,
        }
    except TimeoutError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        breaker_status = record_execution(
            canonical_root,
            resource="nl_router",
            success=False,
            latency_ms=elapsed_ms,
            timed_out=True,
            meta={"status": "timeout"},
        )
        _obs("timeout", success=False, elapsed_ms=elapsed_ms)
        return {
            "status": "timeout",
            "idempotency_key": idempotency_key,
            "error": {"code": "timeout", "message": str(exc)},
            "timing": {"elapsed_ms": elapsed_ms, "timeout_ms": timeout_ms},
            "circuit_breaker": breaker_status,
            "version": 2,
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        breaker_status = record_execution(
            canonical_root,
            resource="nl_router",
            success=False,
            latency_ms=elapsed_ms,
            timed_out=False,
            meta={"status": "error"},
        )
        _obs("error", success=False, elapsed_ms=elapsed_ms)
        return {
            "status": "error",
            "idempotency_key": idempotency_key,
            "error": {"code": "router_error", "message": str(exc)},
            "timing": {"elapsed_ms": elapsed_ms, "timeout_ms": timeout_ms},
            "circuit_breaker": breaker_status,
            "version": 2,
        }


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
    """Backward-compatible router API: returns only the planning payload."""
    out = run_nl_router(
        root,
        text=text,
        channel=channel,
        attachments=attachments,
        repeat_count_30d=repeat_count_30d,
        impact_score=impact_score,
        risk_score=risk_score,
    )
    if out.get("status") != "success":
        return {
            "intent_id": "chat_normal",
            "confidence": 0.2,
            "route_type": "tool",
            "selected_target": "rag.answer",
            "domain": "personal_ops",
            "reasons": ["router_fallback"],
            "risk_level": "medium",
            "requires_approval": False,
            "fallback_plan": {"on_router_failure": "tool_rag_answer"},
            "cost_estimate": {"tokens": "medium", "latency": "medium"},
            "create_skill_decision": {
                "eligible": False,
                "repeat_count_30d": _safe_int(repeat_count_30d),
                "impact_score": _safe_int(impact_score),
                "risk_score": _safe_int(risk_score),
                "decision": "defer",
            },
            "version": 1,
        }
    plan = dict(out.get("plan", {}))
    plan.setdefault("version", 1)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Natural-language skill router (unified)")
    parser.add_argument("--root", default=".")
    parser.add_argument("--text", required=True)
    parser.add_argument("--channel", default="")
    parser.add_argument("--repeat-count-30d", type=int, default=0)
    parser.add_argument("--impact-score", type=int, default=0)
    parser.add_argument("--risk-score", type=int, default=0)
    parser.add_argument("--conversation-id", default="")
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--timeout-ms", type=int, default=1500)
    parser.add_argument("--cancel", action="store_true")
    args = parser.parse_args()

    out = run_nl_router(
        args.root,
        text=args.text,
        channel=args.channel,
        repeat_count_30d=args.repeat_count_30d,
        impact_score=args.impact_score,
        risk_score=args.risk_score,
        conversation_id=args.conversation_id,
        thread_id=args.thread_id,
        message_id=args.message_id,
        timeout_ms=args.timeout_ms,
        cancel_requested=args.cancel,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

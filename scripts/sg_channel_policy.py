#!/usr/bin/env python3
"""SG channel policy helpers: actor classification and sensitivity."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/sg_policy.json")
LOG_PATH = Path("logs/sg_channel_policy_latest.json")

TOKEN_RE = re.compile(r"[a-z0-9_]+")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "worker_auth_mode": "password_plus_owner_approval",
    "password_required": True,
    "owner_channel": "telegram_owner",
    "promotion_rules": {
        "low": "auto",
        "medium": "approval_required",
        "high": "approval_required",
    },
    "worker_password_hash": "",
    "worker_password_hint": "",
    "actor_detection": {
        "worker_keywords": ["worker", "trabajador", "backoffice", "operaciones"],
        "client_keywords": ["cliente", "client", "cotizacion", "quotation", "pedido"],
    },
    "sensitivity_keywords": {
        "low": ["estado", "status", "seguimiento", "agenda", "resumen", "nota"],
        "medium": ["cotizacion", "quotation", "cliente", "proveedor", "orden", "incidencia", "sop"],
        "high": ["password", "token", "secret", "credential", "cuenta", "bank", "dni", "ruc"],
    },
}
DEFAULT_WORKER_PASSWORD = "JACKYMANOLO"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _hash_password(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_sg_policy(root: str | Path, *, create_if_missing: bool = True) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy_path = canonical_root / POLICY_PATH
    payload = _load_json(policy_path)
    policy = json.loads(json.dumps(DEFAULT_POLICY))
    if payload:
        policy.update(payload)
        policy["promotion_rules"] = dict(DEFAULT_POLICY["promotion_rules"]) | dict(payload.get("promotion_rules", {}))
        policy["actor_detection"] = dict(DEFAULT_POLICY["actor_detection"]) | dict(payload.get("actor_detection", {}))
        sens = dict(DEFAULT_POLICY["sensitivity_keywords"])
        for key, values in payload.get("sensitivity_keywords", {}).items():
            if isinstance(values, list):
                sens[key] = [str(item).lower() for item in values if str(item).strip()]
        policy["sensitivity_keywords"] = sens
    if not str(policy.get("worker_password_hash", "")).strip():
        policy["worker_password_hash"] = _hash_password(DEFAULT_WORKER_PASSWORD)
    if not str(policy.get("worker_password_hint", "")).strip():
        policy["worker_password_hint"] = "clave interna"
    if create_if_missing and (not policy_path.is_file() or not payload):
        _save_json(policy_path, policy)
    elif create_if_missing:
        existing = _load_json(policy_path)
        existing_hash = str(existing.get("worker_password_hash", "")).strip() if isinstance(existing, dict) else ""
        if not existing_hash:
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(policy)
            _save_json(policy_path, merged)
    return policy


def _tokens(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


def classify_actor(event: Dict[str, Any], policy: Dict[str, Any]) -> str:
    actor_type = str(event.get("actor_type", "")).strip().lower()
    if actor_type in {"worker", "client"}:
        return actor_type
    text = str(event.get("text", ""))
    tokens = set(_tokens(text))
    worker_hits = sum(1 for kw in policy.get("actor_detection", {}).get("worker_keywords", []) if str(kw).lower() in tokens)
    client_hits = sum(1 for kw in policy.get("actor_detection", {}).get("client_keywords", []) if str(kw).lower() in tokens)
    if worker_hits > client_hits and worker_hits > 0:
        return "worker"
    if client_hits > 0:
        return "client"
    return "unknown"


def classify_sensitivity(text: str, policy: Dict[str, Any]) -> str:
    tokens = set(_tokens(text))
    sens = policy.get("sensitivity_keywords", {})
    for level in ("high", "medium", "low"):
        keywords = [str(item).lower() for item in sens.get(level, [])]
        if any(keyword in tokens for keyword in keywords):
            return level
    return "low"


def worker_auth_check(event: Dict[str, Any], actor: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    auth = event.get("auth", {})
    if not isinstance(auth, dict):
        auth = {}

    password_hash = str(policy.get("worker_password_hash", "")).strip().lower()
    password_candidate = str(auth.get("password", "")).strip()
    if not password_candidate:
        password_candidate = str(event.get("password", "")).strip()
    if not password_candidate:
        password_candidate = str(event.get("text", "")).strip()
    password_ok = bool(auth.get("password_ok", False))
    if not password_ok and password_candidate and password_hash:
        password_ok = _hash_password(password_candidate) == password_hash

    # Allow direct password validation even when actor keyword is omitted in a follow-up message.
    if actor != "worker" and not password_ok:
        return {"status": "not_applicable", "needs_owner_approval": False}

    owner_approved = bool(auth.get("owner_approved", False))
    mode = str(policy.get("worker_auth_mode", "password_plus_owner_approval"))

    if mode == "password_only":
        return {"status": "granted" if password_ok else "challenge", "needs_owner_approval": False}
    if mode == "owner_approval_only":
        return {"status": "granted" if owner_approved else "pending_owner", "needs_owner_approval": True}

    if password_ok and owner_approved:
        return {"status": "granted", "needs_owner_approval": True}
    if not password_ok:
        return {"status": "challenge", "needs_owner_approval": True}
    return {"status": "pending_owner", "needs_owner_approval": True}


def evaluate_sg_event(root: str | Path, event: Dict[str, Any]) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_sg_policy(canonical_root, create_if_missing=True)
    text = str(event.get("text", ""))
    actor = classify_actor(event, policy)
    sensitivity = classify_sensitivity(text, policy)
    auth = worker_auth_check(event, actor, policy)
    payload = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "actor": actor,
        "sensitivity": sensitivity,
        "auth": auth,
        "promotion_mode": str(policy.get("promotion_rules", {}).get(sensitivity, "approval_required")),
        "version": 1,
    }
    _save_json(canonical_root / LOG_PATH, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate SG channel policy for an event")
    parser.add_argument("--root", default=".")
    parser.add_argument("--event-json", required=True)
    args = parser.parse_args()

    raw = args.event_json
    source = Path(raw)
    if source.is_file():
        event = json.loads(source.read_text(encoding="utf-8"))
    else:
        event = json.loads(raw)
    if not isinstance(event, dict):
        raise SystemExit("event json must be an object")

    out = evaluate_sg_event(args.root, event)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

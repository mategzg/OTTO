#!/usr/bin/env python3
"""Deterministic NL intent classifier for channel runtime events."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/channel_runtime_policy.json")
LOG_PATH = Path("logs/nl_intent_classifier_latest.json")

TOKEN_RE = re.compile(r"[a-z0-9_]+")

MEMORY_KEYWORDS = {
    "decision",
    "decidir",
    "decidimos",
    "prefer",
    "preference",
    "prefiero",
    "principle",
    "principio",
    "timeline",
    "proyecto",
    "project",
}
SG_KEYWORDS = {
    "cliente",
    "client",
    "cotizacion",
    "quotation",
    "orden",
    "order",
    "incidencia",
    "sop",
    "sg",
}
WORKER_AUTH_KEYWORDS = {
    "worker",
    "trabajador",
    "backoffice",
    "password",
    "clave",
    "auth",
}


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


def _load_policy(root: Path) -> Dict[str, Any]:
    payload = _load_json(root / POLICY_PATH)
    thresholds = {
        "long_text_chars": 1800,
        "high_signal_keyword_hits": 2,
        "corpus_line_threshold": 25,
    }
    thresholds.update(payload.get("nl_classifier_thresholds", {}))
    return {"thresholds": thresholds}


def _tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


def _contains_corpus(text: str, thresholds: Dict[str, Any]) -> bool:
    if len(text) >= int(thresholds.get("long_text_chars", 1800)):
        return True
    if text.count("\n") + 1 >= int(thresholds.get("corpus_line_threshold", 25)):
        return True
    if "```" in text:
        return True
    return False


def _score_intersection(tokens: Sequence[str], keywords: Sequence[str]) -> int:
    token_set = set(tokens)
    return sum(1 for keyword in keywords if keyword in token_set)


def classify_intent(
    *,
    text: str,
    attachments: Sequence[Dict[str, Any]] | None = None,
    channel: str = "",
    actor_type: str = "",
    thresholds: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    clean_text = text.strip()
    threshold_cfg = {
        "long_text_chars": 1800,
        "high_signal_keyword_hits": 2,
        "corpus_line_threshold": 25,
    }
    if thresholds:
        threshold_cfg.update(thresholds)

    labels: Dict[str, int] = {
        "chat_normal": 1,
        "contains_corpus": 0,
        "contains_attachment": 0,
        "memory_worthy": 0,
        "sg_worthy": 0,
        "requires_worker_auth": 0,
    }
    signals: List[str] = []
    tokens = _tokenize(clean_text)

    if _contains_corpus(clean_text, threshold_cfg):
        labels["contains_corpus"] += 3
        signals.append("long_or_structured_text")

    if attachments:
        labels["contains_attachment"] += 3
        signals.append("attachment_present")

    memory_hits = _score_intersection(tokens, list(MEMORY_KEYWORDS))
    if memory_hits >= int(threshold_cfg.get("high_signal_keyword_hits", 2)):
        labels["memory_worthy"] += 3
        signals.append(f"memory_keyword_hits:{memory_hits}")
    elif memory_hits > 0:
        labels["memory_worthy"] += 1
        signals.append(f"memory_keyword_hits:{memory_hits}")

    sg_hits = _score_intersection(tokens, list(SG_KEYWORDS))
    if sg_hits >= int(threshold_cfg.get("high_signal_keyword_hits", 2)):
        labels["sg_worthy"] += 3
        signals.append(f"sg_keyword_hits:{sg_hits}")
    elif sg_hits > 0:
        labels["sg_worthy"] += 1
        signals.append(f"sg_keyword_hits:{sg_hits}")

    worker_hits = _score_intersection(tokens, list(WORKER_AUTH_KEYWORDS))
    if worker_hits > 0 and str(channel).lower().startswith("whatsapp"):
        labels["requires_worker_auth"] += 3
        signals.append(f"worker_auth_hits:{worker_hits}")
    if str(actor_type).lower() == "worker":
        labels["requires_worker_auth"] += 2
        signals.append("actor_type_worker")

    ranked = sorted(labels.items(), key=lambda item: (-item[1], item[0]))
    primary_label, primary_score = ranked[0]
    if primary_score >= 3:
        confidence = "high"
    elif primary_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    active = [name for name, score in ranked if score > 0 and name != "chat_normal"]
    if not active:
        active = ["chat_normal"]

    return {
        "primary_intent": primary_label if primary_label != "chat_normal" or not active else active[0],
        "confidence": confidence,
        "labels": active,
        "label_scores": {name: score for name, score in sorted(labels.items())},
        "signals": sorted(set(signals)),
        "stats": {
            "char_count": len(clean_text),
            "line_count": clean_text.count("\n") + (1 if clean_text else 0),
            "token_count": len(tokens),
            "attachment_count": len(attachments or []),
        },
    }


def run_classifier(
    root: str | Path,
    *,
    text: str,
    attachments: Sequence[Dict[str, Any]] | None = None,
    channel: str = "",
    actor_type: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    result = classify_intent(
        text=text,
        attachments=attachments or [],
        channel=channel,
        actor_type=actor_type,
        thresholds=policy["thresholds"],
    )
    payload = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "channel": channel,
        "actor_type": actor_type,
        "result": result,
        "version": 1,
    }
    _save_json(canonical_root / LOG_PATH, payload)
    return payload


def _load_attachments(raw: str) -> List[Dict[str, Any]]:
    text = raw.strip()
    if not text:
        return []
    path = Path(text)
    if path.is_file():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify NL intents for runtime messages")
    parser.add_argument("--root", default=".")
    parser.add_argument("--text", default="")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--attachments-json", default="")
    parser.add_argument("--channel", default="")
    parser.add_argument("--actor-type", default="")
    args = parser.parse_args()

    text = sys.stdin.read() if args.stdin else args.text
    if not text.strip():
        raise SystemExit("Provide text via --text or --stdin.")

    out = run_classifier(
        args.root,
        text=text,
        attachments=_load_attachments(args.attachments_json),
        channel=args.channel,
        actor_type=args.actor_type,
    )
    print(
        json.dumps(
            {
                "canonical_root": out["canonical_root"],
                "primary_intent": out["result"]["primary_intent"],
                "labels": out["result"]["labels"],
                "confidence": out["result"]["confidence"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

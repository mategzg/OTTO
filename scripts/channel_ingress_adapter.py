#!/usr/bin/env python3
"""Channel ingress adapter: normalize event -> session memory -> NL routing."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.approval_manager import enqueue_request, is_worker_paired, process_owner_reply
from scripts.chat_to_inbox_drop import run_chat_to_drop
from scripts.context_loader import load_context_plan
from scripts.episode_linker import get_episode
from scripts.memory_capture import run_capture
from scripts.mission_activation import decide_and_act as decide_mission_activation
from scripts.nl_intent_classifier import classify_intent
try:
    from scripts.nl_skill_router import run_nl_router
except Exception:  # pragma: no cover - optional integration
    run_nl_router = None
from scripts.odoo_enqueuer import enqueue_odoo
from scripts.observability import record_event
from scripts.research_enqueuer import enqueue_research
from scripts.repo_root import get_canonical_root
from scripts.session_memory_manager import append_event
from scripts.sg_channel_policy import evaluate_sg_event
from scripts.sg_promotion import enqueue_promotion
from scripts.outbox_queue import enqueue_message
from scripts.reminder_engine import add_reminder
from scripts.status_reporter import build_status, render_status_text

REPORT_JSON = Path("docs/_inbox/ingress_report_latest.json")
REPORT_MD = Path("docs/_inbox/ingress_report_latest.md")
REPORT_LOG = Path("logs/ingress_latest.json")
DISCORD_DOMAINS_PATH = Path("state/discord_domains.json")
WORKER_PAIRINGS_PATH = Path("state/sg_worker_pairings.json")
CHANNEL_POLICY_PATH = Path("state/channel_runtime_policy.json")
USAGE_GUARD_PATH = Path("state/model_usage_guard.json")
WHATSAPP_HOLD_QUEUE_PATH = Path("state/whatsapp_hold_queue.ndjson")

_SLUG_SEP_RE = re.compile(r"[^a-z0-9]+")
_WORKER_BACKOFFICE_RE = re.compile(r"\b(backoffice|worker|trabajador|operaciones|interno|acceso)\b", re.IGNORECASE)
_TOPIC_FOLLOWUP_RE = re.compile(
    r"\b(sobre eso|y lo de|mas sobre|más sobre|cuentame mas|cuéntame más|que mas|qué más|amplia|amplía|detalla)\b",
    re.IGNORECASE,
)
_TOPIC_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TOPIC_STOPWORDS = {
    "el",
    "la",
    "los",
    "las",
    "de",
    "del",
    "en",
    "y",
    "a",
    "que",
    "es",
    "se",
    "con",
    "por",
}
_ODOO_INTENT_PREFIX = "odoo_"
_REMINDER_HOURS_RE = re.compile(r"\ben\s+(\d{1,3})\s*horas?\b", re.IGNORECASE)
_REMINDER_MINUTES_RE = re.compile(r"\ben\s+(\d{1,4})\s*minutos?\b", re.IGNORECASE)
_REMINDER_HHMM_RE = re.compile(r"\ba\s+las\s+(\d{1,2}):(\d{2})\b", re.IGNORECASE)
_REMINDER_DAY_RE = re.compile(r"\bel\s+d[ií]a\s+(\d{1,2})/(\d{1,2})\b", re.IGNORECASE)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_json_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_pairings(root: Path, payload: Dict[str, Any]) -> None:
    payload["updated_at"] = _utc_now()
    _save_json(root / WORKER_PAIRINGS_PATH, payload)


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _load_channel_policy(root: Path) -> Dict[str, Any]:
    payload = _load_json_file(root / CHANNEL_POLICY_PATH)
    return payload if isinstance(payload, dict) else {}


def _whatsapp_budget_guard_status(root: Path, event: Dict[str, Any], *, is_inbound: bool) -> Dict[str, Any]:
    channel = str(event.get("channel", "")).lower()
    if not is_inbound or channel != "whatsapp":
        return {"status": "not_applicable", "allowed": True}

    if bool(event.get("metadata", {}).get("budget_replay", False)):
        return {"status": "bypass_replay", "allowed": True}

    policy = _load_channel_policy(root)
    guard = policy.get("whatsapp_runtime_guard", {}) if isinstance(policy.get("whatsapp_runtime_guard", {}), dict) else {}
    if not bool(guard.get("enabled", False)):
        return {"status": "disabled", "allowed": True}

    min_pct = max(1, int(guard.get("min_5h_remaining_pct", 50)))
    usage = _load_json_file(root / USAGE_GUARD_PATH)
    remaining = usage.get("five_hour_remaining_pct")
    if not isinstance(remaining, int):
        hold_row = {
            "ts": _utc_now(),
            "reason": "missing_5h_usage_data",
            "remaining_pct": None,
            "min_pct": min_pct,
            "event": event,
        }
        _append_ndjson(root / WHATSAPP_HOLD_QUEUE_PATH, hold_row)
        return {
            "status": "held_missing_usage_data",
            "allowed": False,
            "remaining_pct": None,
            "min_pct": min_pct,
            "hold_queue_path": WHATSAPP_HOLD_QUEUE_PATH.as_posix(),
        }
    if remaining >= min_pct:
        return {"status": "allowed", "allowed": True, "remaining_pct": remaining, "min_pct": min_pct}

    hold_row = {
        "ts": _utc_now(),
        "reason": "below_5h_threshold",
        "remaining_pct": remaining,
        "min_pct": min_pct,
        "event": event,
    }
    _append_ndjson(root / WHATSAPP_HOLD_QUEUE_PATH, hold_row)
    return {
        "status": "held_below_threshold",
        "allowed": False,
        "remaining_pct": remaining,
        "min_pct": min_pct,
        "hold_queue_path": WHATSAPP_HOLD_QUEUE_PATH.as_posix(),
    }


def _load_pairings(root: Path) -> Dict[str, Any]:
    payload = _load_json_file(root / WORKER_PAIRINGS_PATH)
    if not payload:
        payload = {"version": 1, "updated_at": "", "workers": {}}
    if not isinstance(payload.get("workers"), dict):
        payload["workers"] = {}
    return payload


def _load_json(raw: str) -> Dict[str, Any]:
    data = raw.strip()
    if not data:
        raise RuntimeError("event payload is required")
    path = Path(data)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = json.loads(data)
    if not isinstance(payload, dict):
        raise RuntimeError("event payload must be JSON object")
    return payload


def _text_of(event: Dict[str, Any]) -> str:
    text = str(event.get("text", "")).strip()
    if text:
        return text
    # Fallback fields used by some gateways.
    for key in ("message", "body", "content", "caption"):
        value = str(event.get(key, "")).strip()
        if value:
            return value
    return ""


def _topic_keywords(text: str, *, max_words: int) -> List[str]:
    normalized = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii").lower()
    out: List[str] = []
    for token in _TOPIC_TOKEN_RE.findall(normalized):
        if token in _TOPIC_STOPWORDS:
            continue
        if token in out:
            continue
        out.append(token)
        if len(out) >= max_words:
            break
    return out


def _topic_slug_from_text(text: str) -> str:
    words = _topic_keywords(text, max_words=3)
    return "_".join(words) if words else ""


def _topic_label_from_text(text: str) -> str:
    words = _topic_keywords(text, max_words=5)
    return " ".join(words) if words else "tema"


def _maybe_add_episodic_context(root: Path, event: Dict[str, Any], intent: Dict[str, Any], *, is_inbound: bool) -> Dict[str, Any]:
    if not is_inbound:
        return {"status": "skipped_outbound"}
    text = str(event.get("text", "")).strip()
    if not text:
        return {"status": "skipped_empty"}
    signals = intent.get("signals", [])
    if not isinstance(signals, list):
        signals = []
    wants_followup = "topic_followup" in signals or bool(_TOPIC_FOLLOWUP_RE.search(text))
    if not wants_followup:
        return {"status": "skipped"}
    topic_slug = _topic_slug_from_text(text)
    if not topic_slug:
        return {"status": "skipped_no_topic"}
    try:
        episode = get_episode(root, topic_slug)
    except Exception as exc:
        return {"status": "error", "error": f"{exc.__class__.__name__}:{exc}"}
    if not isinstance(episode, dict):
        return {"status": "not_found", "topic_slug": topic_slug}
    topic = str(episode.get("topic", "")).strip() or topic_slug
    summary = str(episode.get("summary", "")).strip()
    if not summary:
        return {"status": "empty_summary", "topic_slug": topic_slug}
    note = f"[CONTEXTO EPISODICO: {topic}]\n{summary[:500]}".strip()
    metadata = event.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    metadata["episodic_context"] = {
        "topic_slug": topic_slug,
        "episode_id": str(episode.get("episode_id", "")),
        "topic": topic,
        "summary": summary[:500],
        "note": note,
    }
    event["metadata"] = metadata
    attachments = event.get("attachments", [])
    if not isinstance(attachments, list):
        attachments = []
    attachments.append(
        {
            "type": "episodic_context",
            "episode_id": str(episode.get("episode_id", "")),
            "topic": topic,
            "summary": summary[:500],
        }
    )
    event["attachments"] = attachments
    return {
        "status": "matched",
        "topic_slug": topic_slug,
        "episode_id": str(episode.get("episode_id", "")),
        "topic": topic,
    }


def _maybe_enqueue_research_request(root: Path, event: Dict[str, Any], intent: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    if str(event.get("action", "")).strip().lower() == "sent":
        return {"status": "skipped_outbound"}
    if str(intent.get("primary_intent", "")) != "research_request":
        return {"status": "skipped"}
    text = str(event.get("text", "")).strip()
    if not text:
        return {"status": "skipped_empty_text"}
    topic = _topic_label_from_text(text)
    requested_by = f"{str(event.get('channel', '')).strip()}:{str(event.get('peer_id', '')).strip()}"
    enqueued = enqueue_research(root, topic, text, requested_by)
    target = str(event.get("peer_id", "")).strip()
    queue_item_id = ""
    if target:
        ack = enqueue_message(
            root,
            channel=str(event.get("channel", "")).strip(),
            target=target,
            text=f"🔍 Entendido. Investigo sobre '{topic}' y te aviso cuando termine.",
            purpose="research_ack",
            session_id=session_id,
            source_ref=f"runtime:{session_id}",
            metadata={"kind": "research_request", "task_id": str(enqueued.get("task_id", ""))},
        )
        queue_item_id = str(ack.get("item_id", ""))
    return {
        "status": "enqueued",
        "task_id": str(enqueued.get("task_id", "")),
        "enqueue_status": str(enqueued.get("status", "")),
        "topic": topic,
        "queue_item_id": queue_item_id,
    }


def _maybe_enqueue_odoo_request(root: Path, event: Dict[str, Any], intent: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    if str(event.get("action", "")).strip().lower() == "sent":
        return {"status": "skipped_outbound"}
    primary = str(intent.get("primary_intent", "")).strip().lower()
    if not primary.startswith(_ODOO_INTENT_PREFIX):
        return {"status": "skipped"}
    text = str(event.get("text", "")).strip()
    if not text:
        return {"status": "skipped_empty_text"}

    requested_by = f"{str(event.get('channel', '')).strip()}:{str(event.get('peer_id', '')).strip()}"
    try:
        enqueued = enqueue_odoo(root, primary, text, requested_by)
    except Exception as exc:
        return {"status": "error", "error": f"{exc.__class__.__name__}:{exc}", "odoo_intent": primary}

    queue_item_id = ""
    target = str(event.get("peer_id", "")).strip()
    if target:
        ack = enqueue_message(
            root,
            channel=str(event.get("channel", "")).strip(),
            target=target,
            text=f"⚙️ Consultando Odoo sobre '{primary}'. Te aviso cuando tenga resultado.",
            purpose="odoo_ack",
            session_id=session_id,
            source_ref=f"runtime:{session_id}",
            metadata={"kind": "odoo_request", "task_id": str(enqueued.get("task_id", "")), "odoo_intent": primary},
        )
        queue_item_id = str(ack.get("item_id", ""))
    return {
        "status": "enqueued",
        "task_id": str(enqueued.get("task_id", "")),
        "enqueue_status": str(enqueued.get("status", "")),
        "odoo_intent": primary,
        "queue_item_id": queue_item_id,
    }


def _parse_reminder_time(text: str, now: datetime) -> Dict[str, Any]:
    clean = str(text or "").strip()
    if not clean:
        fallback = now + timedelta(hours=1)
        return {"deliver_at": fallback, "fallback": True, "reason": "empty_text"}

    match = _REMINDER_HOURS_RE.search(clean)
    if match:
        hours = max(1, int(match.group(1)))
        return {"deliver_at": now + timedelta(hours=hours), "fallback": False, "reason": "in_hours"}

    match = _REMINDER_MINUTES_RE.search(clean)
    if match:
        minutes = max(1, int(match.group(1)))
        return {"deliver_at": now + timedelta(minutes=minutes), "fallback": False, "reason": "in_minutes"}

    hhmm = _REMINDER_HHMM_RE.search(clean)
    day_mm = _REMINDER_DAY_RE.search(clean)
    tomorrow = ("mañana" in clean.lower()) or ("manana" in clean.lower())
    if hhmm:
        hour = min(23, max(0, int(hhmm.group(1))))
        minute = min(59, max(0, int(hhmm.group(2))))
        if day_mm:
            day = min(31, max(1, int(day_mm.group(1))))
            month = min(12, max(1, int(day_mm.group(2))))
            year = now.year
            try:
                candidate = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            except ValueError:
                candidate = now + timedelta(hours=1)
                return {"deliver_at": candidate, "fallback": True, "reason": "invalid_day_month"}
            if candidate < now:
                try:
                    candidate = datetime(year + 1, month, day, hour, minute, tzinfo=timezone.utc)
                except ValueError:
                    pass
            return {"deliver_at": candidate, "fallback": False, "reason": "day_and_time"}
        base = now + timedelta(days=1 if tomorrow else 0)
        candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return {"deliver_at": candidate, "fallback": False, "reason": "time_only"}

    if day_mm:
        day = min(31, max(1, int(day_mm.group(1))))
        month = min(12, max(1, int(day_mm.group(2))))
        year = now.year
        try:
            candidate = datetime(year, month, day, 9, 0, tzinfo=timezone.utc)
        except ValueError:
            candidate = now + timedelta(hours=1)
            return {"deliver_at": candidate, "fallback": True, "reason": "invalid_day_month"}
        if candidate < now:
            try:
                candidate = datetime(year + 1, month, day, 9, 0, tzinfo=timezone.utc)
            except ValueError:
                pass
        return {"deliver_at": candidate, "fallback": False, "reason": "day_only"}

    if tomorrow:
        candidate = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return {"deliver_at": candidate, "fallback": False, "reason": "tomorrow_default_9am"}

    fallback = now + timedelta(hours=1)
    return {"deliver_at": fallback, "fallback": True, "reason": "parse_fallback_1h"}


def _maybe_enqueue_reminder_request(root: Path, event: Dict[str, Any], intent: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    if str(event.get("action", "")).strip().lower() == "sent":
        return {"status": "skipped_outbound"}
    if str(intent.get("primary_intent", "")) != "reminder_request":
        return {"status": "skipped"}
    text = str(event.get("text", "")).strip()
    if not text:
        return {"status": "skipped_empty_text"}

    now = datetime.now(timezone.utc)
    parsed = _parse_reminder_time(text, now)
    due_dt = parsed["deliver_at"]
    due_iso = due_dt.astimezone(timezone.utc).isoformat()
    add_out = add_reminder(
        root,
        text=text,
        deliver_at=due_iso,
        source_session=session_id,
        channel="telegram_owner",
    )
    target = str(event.get("peer_id", "")).strip()
    if str(event.get("channel", "")).strip().lower().startswith("whatsapp") or not target:
        target = "telegram_owner"
    note = " (hora no detectada, recordando en 1h)" if bool(parsed.get("fallback", False)) else ""
    ack = enqueue_message(
        root,
        channel="telegram_owner",
        target=target,
        text=f"⏳ Recordatorio agendado para {due_iso}.{note}",
        purpose="reminder_ack",
        session_id=session_id,
        source_ref=f"runtime:{session_id}",
        metadata={"kind": "reminder_request", "reminder_id": str(add_out.get('id', ''))},
    )
    return {
        "status": "enqueued" if add_out.get("status") in {"enqueued", "duplicate_existing"} else str(add_out.get("status", "")),
        "reminder_id": str(add_out.get("id", "")),
        "enqueue_status": str(add_out.get("status", "")),
        "deliver_at": due_iso,
        "fallback": bool(parsed.get("fallback", False)),
        "queue_item_id": str(ack.get("item_id", "")),
    }


def _as_attachments(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = event.get("attachments", [])
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [raw]
    # Lightweight normalization for gateways that provide file/url.
    name = str(event.get("file_name", "")).strip()
    path = str(event.get("file_path", "")).strip()
    url = str(event.get("file_url", "")).strip()
    if name or path or url:
        return [{"name": name, "path": path, "url": url}]
    return []


def _looks_like_openclaw_message_event(raw: Dict[str, Any]) -> bool:
    if not isinstance(raw, dict):
        return False
    event_type = str(raw.get("type", "")).strip().lower()
    action = str(raw.get("action", "")).strip().lower()
    context = raw.get("context", {})
    if not isinstance(context, dict):
        return False
    if str(context.get("channelId", "")).strip():
        if event_type == "message" and action in {"received", "sent"}:
            return True
        if event_type in {"message:received", "message:sent"}:
            return True
    return False


def _normalize_openclaw_message_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    context = raw.get("context", {})
    if not isinstance(context, dict):
        context = {}
    metadata = context.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    event_type = str(raw.get("type", "")).strip().lower()
    action = str(raw.get("action", "")).strip().lower()
    if action not in {"received", "sent"}:
        if event_type == "message:received":
            action = "received"
        elif event_type == "message:sent":
            action = "sent"

    channel = str(context.get("channelId", "")).strip().lower()
    conversation_id = str(context.get("conversationId", "")).strip()
    thread_id = str(metadata.get("threadId", context.get("threadId", ""))).strip()
    account_id = str(context.get("accountId", "")).strip()
    message_id = str(context.get("messageId", "")).strip()
    timestamp = str(context.get("timestamp", raw.get("timestamp", ""))).strip() or _utc_now()
    channel_name = str(metadata.get("channelName", context.get("channelName", context.get("roomName", "")))).strip()

    from_obj = context.get("from", {})
    to_obj = context.get("to", {})
    if not isinstance(from_obj, dict):
        from_obj = {}
    if not isinstance(to_obj, dict):
        to_obj = {}

    sender_id = str(metadata.get("senderId", from_obj.get("id", ""))).strip()
    sender_name = str(metadata.get("senderName", from_obj.get("name", ""))).strip()
    peer_id = conversation_id or sender_id or str(to_obj.get("id", "")).strip() or "_"
    actor_type = str(raw.get("actor_type", "")).strip().lower()
    if not actor_type:
        actor_type = "assistant" if action == "sent" else "user"

    # Keep session stable by conversation + thread.
    channel_id = str(metadata.get("channelId", context.get("channelRef", conversation_id))).strip() or conversation_id or "_"
    chat_type = "dm"
    if thread_id:
        chat_type = "thread"
    elif channel.startswith("discord"):
        chat_type = "channel"

    normalized = {
        "agent_id": str(raw.get("agent_id", "otto")).strip() or "otto",
        "channel": channel or "_",
        "action": action or "received",
        "account_id": account_id or "_",
        "peer_id": peer_id,
        "conversation_id": conversation_id,
        "channel_id": channel_id,
        "thread_id": thread_id,
        "channel_name": channel_name,
        "chat_type": chat_type,
        "actor_type": actor_type,
        "message_id": message_id,
        "timestamp": timestamp,
        "text": str(context.get("content", "")).strip(),
        "attachments": _as_attachments(context),
        "labels": [],
        "metadata": {
            "is_owner": bool(raw.get("is_owner", False)),
            "author_name": sender_name or str(metadata.get("senderUsername", "")).strip(),
            "sender_username": str(metadata.get("senderUsername", "")).strip(),
            "sender_e164": str(metadata.get("senderE164", "")).strip(),
            "openclaw_event_type": event_type,
            "openclaw_action": action,
            "openclaw_session_key": str(raw.get("sessionKey", "")),
            "openclaw_workspace_dir": str(context.get("workspaceDir", "")),
        },
        "auth": raw.get("auth", {}) if isinstance(raw.get("auth", {}), dict) else {},
    }
    if action == "sent":
        normalized["metadata"]["is_outbound"] = True
    return normalized


def _slug_domain(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii")
    clean = normalized.strip().lower().replace("_", " ")
    clean = _SLUG_SEP_RE.sub("-", clean)
    clean = clean.strip("-")
    return clean or "unknown"


def _normalize_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    if _looks_like_openclaw_message_event(raw):
        return _normalize_openclaw_message_event(raw)

    channel = str(raw.get("channel", raw.get("platform", ""))).strip().lower()
    if not channel:
        raise RuntimeError("event requires channel/platform")
    account_id = str(raw.get("account_id", raw.get("account", "_"))).strip() or "_"
    peer_id = str(raw.get("peer_id", raw.get("chat_id", raw.get("from_id", "_")))).strip() or "_"
    channel_id = str(raw.get("channel_id", raw.get("room_id", "_"))).strip() or "_"
    thread_id = str(raw.get("thread_id", raw.get("topic_id", ""))).strip()
    chat_type = str(raw.get("chat_type", "dm" if channel.startswith(("telegram", "whatsapp")) else "channel")).strip().lower()
    actor_type = str(raw.get("actor_type", raw.get("role", ""))).strip().lower()
    message_id = str(raw.get("message_id", raw.get("id", ""))).strip()
    timestamp = str(raw.get("timestamp", raw.get("ts", ""))).strip() or _utc_now()
    channel_name = str(raw.get("channel_name", raw.get("room_name", raw.get("channel_title", "")))).strip()
    action = str(raw.get("action", "sent" if bool(raw.get("is_outbound", False)) else "received")).strip().lower()
    if action not in {"received", "sent"}:
        action = "received"
    is_owner = bool(raw.get("is_owner", False))
    if channel.startswith("telegram") and str(raw.get("owner", "")).strip().lower() in {"1", "true", "yes"}:
        is_owner = True

    out = {
        "agent_id": str(raw.get("agent_id", "otto")).strip() or "otto",
        "channel": channel,
        "action": action,
        "account_id": account_id,
        "peer_id": peer_id,
        "channel_id": channel_id,
        "thread_id": thread_id,
        "channel_name": channel_name,
        "chat_type": chat_type,
        "actor_type": actor_type,
        "message_id": message_id,
        "timestamp": timestamp,
        "text": _text_of(raw),
        "attachments": _as_attachments(raw),
        "labels": [],
        "metadata": {
            "is_owner": is_owner,
            "author_name": str(raw.get("author_name", raw.get("from_name", ""))).strip(),
            "is_outbound": bool(raw.get("is_outbound", False)),
        },
    }

    auth = raw.get("auth", {})
    if isinstance(auth, dict):
        out["auth"] = auth
    elif "password_ok" in raw:
        out["auth"] = {"password_ok": bool(raw.get("password_ok", False))}
    else:
        out["auth"] = {}
    return out


def _infer_discord_domain(root: Path, event: Dict[str, Any]) -> Dict[str, Any]:
    if not str(event.get("channel", "")).startswith("discord"):
        return {
            "domain_slug": "",
            "channel_id": str(event.get("channel_id", "")),
            "channel_name": str(event.get("channel_name", "")),
            "updated": False,
            "mapping_path": DISCORD_DOMAINS_PATH.as_posix(),
        }

    mapping_path = root / DISCORD_DOMAINS_PATH
    mapping = _load_json_file(mapping_path)
    if not isinstance(mapping.get("domains"), dict):
        mapping = {"version": 1, "updated_at": "", "domains": {}}
    domains: Dict[str, Any] = mapping["domains"]

    channel_id = str(event.get("channel_id", "")).strip() or "unknown"
    channel_name = str(event.get("channel_name", "")).strip()
    inferred_slug = _slug_domain(channel_name) if channel_name else "unknown"

    existing = domains.get(channel_id, {})
    existing_slug = str(existing.get("domain_slug", "")).strip() if isinstance(existing, dict) else ""
    if existing_slug and existing_slug != "unknown":
        final_slug = existing_slug
    elif existing_slug == "unknown" and inferred_slug != "unknown":
        final_slug = inferred_slug
    else:
        final_slug = inferred_slug

    now = _utc_now()
    updated_entry = {
        "domain_slug": final_slug or "unknown",
        "channel_name_last_seen": channel_name,
        "updated_at": now,
        "source": "inferred",
    }
    changed = domains.get(channel_id) != updated_entry
    domains[channel_id] = updated_entry
    mapping["version"] = 1
    mapping["updated_at"] = now
    mapping["domains"] = {key: domains[key] for key in sorted(domains)}
    if changed or not mapping_path.is_file():
        _save_json(mapping_path, mapping)

    return {
        "domain_slug": updated_entry["domain_slug"],
        "channel_id": channel_id,
        "channel_name": channel_name,
        "updated": changed,
        "mapping_path": DISCORD_DOMAINS_PATH.as_posix(),
    }


def _wants_drop(event: Dict[str, Any], labels: List[str], channel: str) -> bool:
    if str(event.get("action", "")).strip().lower() == "sent":
        return False
    contains_payload = "contains_attachment" in labels or "contains_corpus" in labels
    if not contains_payload:
        return False
    if channel.startswith(("telegram", "discord")):
        return True
    # WhatsApp only for SG-worthy payload.
    return channel.startswith("whatsapp") and "sg_worthy" in labels


def _capture_memory_if_applicable(root: Path, event: Dict[str, Any], labels: List[str], session_id: str) -> Dict[str, Any]:
    if str(event.get("action", "")).strip().lower() == "sent":
        return {"status": "skipped_outbound"}
    channel = str(event.get("channel", "")).lower()
    if "memory_worthy" not in labels:
        return {"status": "skipped"}
    # Hard rule for SEQ015: WhatsApp never feeds personal memory.
    if channel.startswith("whatsapp"):
        return {"status": "blocked_whatsapp_policy"}
    text = str(event.get("text", "")).strip()
    if not text:
        return {"status": "skipped_empty_text"}
    out = run_capture(
        root,
        record_type="note_raw",
        key="",
        source_ref=f"runtime:{session_id}#{event.get('message_id', '_')}",
        confidence="medium",
        tags_csv=f"runtime,{channel}",
        text=text,
        fields={},
    )
    return {"status": "captured", "record_id": out["record"]["id"]}


def _maybe_enqueue_worker_pairing(root: Path, event: Dict[str, Any], sg_eval: Dict[str, Any], session_id: str) -> Dict[str, Any]:
    if str(event.get("channel", "")).lower() != "whatsapp":
        return {"status": "not_applicable"}
    if str(sg_eval.get("actor", "")) != "worker":
        return {"status": "not_worker"}

    auth = sg_eval.get("auth", {})
    if not isinstance(auth, dict):
        auth = {}
    if str(auth.get("status", "")) == "challenge":
        return {"status": "password_required"}

    account_id = str(event.get("account_id", "_"))
    peer_id = str(event.get("peer_id", "_"))
    if is_worker_paired(root, channel="whatsapp", account_id=account_id, peer_id=peer_id):
        return {"status": "already_paired"}

    if str(auth.get("status", "")) != "pending_owner":
        return {"status": "not_pending_owner"}

    worker_key = "|".join(["whatsapp", account_id.lower() or "_", peer_id.lower() or "_"])
    payload = {
        "worker_key": worker_key,
        "channel": "whatsapp",
        "account_id": account_id,
        "peer_id": peer_id,
        "display_name": str(event.get("metadata", {}).get("author_name", "")),
    }
    out = enqueue_request(
        root,
        request_type="worker_pairing",
        subject=f"Worker pairing for {peer_id}",
        payload=payload,
        source_ref=f"runtime:{session_id}",
        dedupe_key=f"worker_pairing:{worker_key}",
    )
    pairings = _load_pairings(root)
    pairings["workers"][worker_key] = {
        "status": "pending_pairing",
        "requested_at": _utc_now(),
        "channel": "whatsapp",
        "account_id": account_id,
        "peer_id": peer_id,
        "display_name": str(event.get("metadata", {}).get("author_name", "")),
        "source_ref": f"runtime:{session_id}",
    }
    _save_pairings(root, pairings)
    return {"status": out["status"], "approval_id": out.get("approval_id", ""), "worker_key": worker_key}


def _maybe_reply_worker_flow(
    root: Path,
    event: Dict[str, Any],
    sg_eval: Dict[str, Any],
    pairing_action: Dict[str, Any],
    session_id: str,
) -> Dict[str, Any]:
    if str(event.get("channel", "")).lower() != "whatsapp":
        return {"status": "not_applicable"}
    if str(event.get("action", "")).strip().lower() == "sent":
        return {"status": "skip_outbound"}
    if str(sg_eval.get("actor", "")) != "worker":
        return {"status": "not_worker"}

    target = str(event.get("peer_id", "")).strip()
    if not target:
        return {"status": "missing_target"}

    auth = sg_eval.get("auth", {})
    if not isinstance(auth, dict):
        auth = {}
    auth_status = str(auth.get("status", ""))
    pairing_status = str(pairing_action.get("status", ""))
    text = str(event.get("text", "")).strip()

    reply_text = ""
    if pairing_status in {"enqueued", "duplicate_pending", "already_paired"}:
        if pairing_status == "already_paired":
            return {"status": "already_paired"}
        reply_text = "Listo, solicitud enviada. En breve tendras confirmacion."
    elif auth_status == "challenge":
        if _WORKER_BACKOFFICE_RE.search(text):
            reply_text = "Necesito verificacion para continuar. Comparte la clave de trabajador."
    elif auth_status == "pending_owner":
        reply_text = "Solicitud de verificacion en revision por owner. Te confirmo en breve."

    if not reply_text:
        return {"status": "no_reply"}

    queued = enqueue_message(
        root,
        channel="whatsapp",
        target=target,
        text=reply_text,
        purpose="worker_pairing_flow",
        session_id=session_id,
        source_ref=f"runtime:{session_id}",
        metadata={"flow": "whatsapp_worker_pairing", "auth_status": auth_status, "pairing_status": pairing_status},
    )
    return {
        "status": "queued",
        "queue_item_id": queued.get("item_id", ""),
        "target": target,
    }


def _maybe_enqueue_sg_promotion(root: Path, event: Dict[str, Any], labels: List[str], session_id: str, sg_eval: Dict[str, Any]) -> Dict[str, Any]:
    if "sg_worthy" not in labels:
        return {"status": "not_sg_worthy"}
    text = str(event.get("text", "")).strip()
    if not text:
        return {"status": "empty_text"}
    sensitivity = str(sg_eval.get("sensitivity", "low"))
    enqueued = enqueue_promotion(
        root,
        {
            "text": text,
            "sensitivity": sensitivity,
            "source_ref": f"runtime:{session_id}#{event.get('message_id', '_')}",
            "target": "sg_global",
        },
    )
    if sensitivity in {"medium", "high"} and enqueued.get("status") in {"enqueued", "duplicate"}:
        promotion_id = str(enqueued.get("promotion_id", ""))
        app = enqueue_request(
            root,
            request_type="sg_promotion",
            subject=f"SG promotion {promotion_id or 'pending'}",
            payload={"promotion_id": promotion_id, "sensitivity": sensitivity, "text": text[:320]},
            source_ref=f"runtime:{session_id}",
            dedupe_key=f"sg_promotion:{promotion_id}" if promotion_id else "",
        )
        return {
            "status": "queued_for_owner_approval",
            "promotion": enqueued,
            "approval_request": app,
        }
    return {"status": "queued", "promotion": enqueued}


def handle_runtime_event(root: str | Path, raw_event: Dict[str, Any]) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    event = _normalize_event(raw_event)
    channel = str(event.get("channel", ""))
    action = str(event.get("action", "received")).strip().lower()
    is_inbound = action != "sent"

    budget_guard = _whatsapp_budget_guard_status(canonical_root, event, is_inbound=is_inbound)
    if not bool(budget_guard.get("allowed", True)):
        report = {
            "canonical_root": str(canonical_root.resolve()),
            "created_at": _utc_now(),
            "status": "held_budget_guard",
            "event": {
                "channel": channel,
                "action": action,
                "peer_id": str(event.get("peer_id", "")),
                "message_id": str(event.get("message_id", "")),
            },
            "primary_intent": "deferred_budget_guard",
            "labels": ["deferred", "whatsapp_budget_guard"],
            "actions": {"whatsapp_budget_guard": budget_guard},
            "version": 1,
        }
        _save_json(canonical_root / REPORT_JSON, report)
        _save_json(canonical_root / REPORT_LOG, report)
        (canonical_root / REPORT_MD).write_text(
            "\n".join(
                [
                    "# Ingress Report",
                    "",
                    "- Status: `held_budget_guard`",
                    f"- Channel: `{channel}`",
                    f"- Message id: `{event.get('message_id', '')}`",
                    f"- Guard status: `{budget_guard.get('status', '')}`",
                    f"- Remaining 5h pct: `{budget_guard.get('remaining_pct', 'unknown')}`",
                    f"- Threshold pct: `{budget_guard.get('min_pct', 'unknown')}`",
                    f"- Hold queue: `{budget_guard.get('hold_queue_path', '')}`",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return report

    domain_info = _infer_discord_domain(canonical_root, event)
    if channel.startswith("discord"):
        event["domain_slug"] = domain_info["domain_slug"] or "unknown"
        event["recommended_domain"] = event["domain_slug"]
    else:
        event["domain_slug"] = str(event.get("domain_slug", "")).strip()
        event["recommended_domain"] = str(event.get("recommended_domain", "")).strip()

    intent = classify_intent(
        text=str(event.get("text", "")),
        attachments=event.get("attachments", []),
        channel=channel,
        actor_type=str(event.get("actor_type", "")),
    )
    labels = sorted(set(intent.get("labels", [])))
    event["labels"] = labels

    if run_nl_router is not None:
        nl_route = run_nl_router(
            canonical_root,
            text=str(event.get("text", "")),
            channel=channel,
            attachments=event.get("attachments", []),
            conversation_id=str(event.get("conversation_id", "")),
            thread_id=str(event.get("thread_id", "")),
            message_id=str(event.get("message_id", "")),
            timeout_ms=1500,
        )
    else:
        nl_route = {
            "status": "error",
            "error": {"code": "router_unavailable", "message": "run_nl_router import failed"},
            "version": 2,
        }

    if nl_route.get("status") == "success":
        routed_intent = str(nl_route.get("plan", {}).get("intent_id", "")).strip()
        if routed_intent:
            intent["primary_intent"] = routed_intent
        routed_conf = str(nl_route.get("classification", {}).get("confidence", "")).strip()
        if routed_conf:
            intent["confidence"] = routed_conf

    episodic_context = _maybe_add_episodic_context(canonical_root, event, intent, is_inbound=is_inbound)

    session_out = append_event(canonical_root, event)
    session_id = session_out["session_id"]
    meta_rel = str(session_out.get("paths", {}).get("meta", ""))
    session_meta = _load_json_file(canonical_root / meta_rel) if meta_rel else {}
    session_is_new = int(session_meta.get("event_count_total", 0)) <= 1

    actions: Dict[str, Any] = {
        "session": session_out,
        "intent": intent,
        "context_profile": {},
        "status_reply": {},
        "owner_reply": {},
        "episodic_context": episodic_context,
        "research": {},
        "reminder": {},
        "odoo": {},
        "mission_activation": {},
        "memory_capture": {},
        "drop": {},
        "sg_evaluation": {},
        "sg_promotion": {},
        "worker_pairing": {},
        "worker_reply": {},
    }

    is_owner = bool(event.get("metadata", {}).get("is_owner", False)) or channel == "telegram_owner"
    if is_inbound and channel.startswith("telegram") and is_owner:
        owner_reply = process_owner_reply(canonical_root, reply_text=str(event.get("text", "")))
        actions["owner_reply"] = owner_reply
        if str(intent.get("primary_intent", "")) == "status_request":
            status_text = render_status_text(build_status(canonical_root))
            queued = enqueue_message(
                canonical_root,
                channel=channel,
                target=str(event.get("peer_id", "")),
                text=status_text,
                purpose="status_reply",
                session_id=session_id,
                source_ref=f"runtime:{session_id}",
                metadata={"kind": "status_request"},
            )
            actions["status_reply"] = {
                "status": "queued",
                "queue_item_id": queued.get("item_id", ""),
                "target": str(event.get("peer_id", "")),
            }
        else:
            actions["status_reply"] = {"status": "skipped"}
    else:
        actions["status_reply"] = {"status": "skipped"}

    if is_inbound and session_is_new:
        context_plan = load_context_plan(
            canonical_root,
            channel=channel,
            actor_tier=str(session_out.get("tier", "")),
            actor_type=str(event.get("actor_type", "")),
            topic_signals=labels,
            domain_slug=str(event.get("recommended_domain", event.get("domain_slug", ""))),
        )
        actions["context_profile"] = {
            "status": "loaded",
            "profile": str(context_plan.get("profile", "")),
            "entry_count": len(context_plan.get("entries", [])),
            "entries": context_plan.get("entries", []),
        }
    elif is_inbound:
        actions["context_profile"] = {"status": "skipped_existing_session"}
    else:
        actions["context_profile"] = {"status": "skipped_outbound"}

    sg_eval = evaluate_sg_event(canonical_root, event) if (is_inbound and channel.startswith("whatsapp")) else {}
    if is_inbound:
        if sg_eval:
            actions["sg_evaluation"] = sg_eval
            actions["worker_pairing"] = _maybe_enqueue_worker_pairing(canonical_root, event, sg_eval, session_id)
            actions["worker_reply"] = _maybe_reply_worker_flow(
                canonical_root,
                event,
                sg_eval,
                actions["worker_pairing"],
                session_id,
            )
            actions["sg_promotion"] = _maybe_enqueue_sg_promotion(canonical_root, event, labels, session_id, sg_eval)
        elif "sg_worthy" in labels:
            actions["sg_promotion"] = _maybe_enqueue_sg_promotion(canonical_root, event, labels, session_id, {"sensitivity": "medium"})

        actions["mission_activation"] = decide_mission_activation(
            canonical_root,
            event=event,
            intent=intent,
            session_id=session_id,
            sg_eval=sg_eval,
            owner_reply=actions["owner_reply"],
        )["report"]
        actions["research"] = _maybe_enqueue_research_request(canonical_root, event, intent, session_id)
        actions["reminder"] = _maybe_enqueue_reminder_request(canonical_root, event, intent, session_id)
        actions["odoo"] = _maybe_enqueue_odoo_request(canonical_root, event, intent, session_id)
        actions["memory_capture"] = _capture_memory_if_applicable(canonical_root, event, labels, session_id)
    else:
        actions["episodic_context"] = {"status": "skipped_outbound"}
        actions["research"] = {"status": "skipped_outbound"}
        actions["reminder"] = {"status": "skipped_outbound"}
        actions["odoo"] = {"status": "skipped_outbound"}
        actions["mission_activation"] = {"status": "skipped_outbound"}
        actions["sg_evaluation"] = {"status": "skipped_outbound"}
        actions["worker_pairing"] = {"status": "skipped_outbound"}
        actions["worker_reply"] = {"status": "skipped_outbound"}
        actions["sg_promotion"] = {"status": "skipped_outbound"}
        actions["memory_capture"] = {"status": "skipped_outbound"}

    if is_inbound and _wants_drop(event, labels, channel):
        actions["drop"] = run_chat_to_drop(canonical_root, event=event, session_id=session_id, source_label="channel_ingress")
    else:
        actions["drop"] = {"status": "skipped_outbound" if not is_inbound else "skipped"}

    trace_id = str(nl_route.get("idempotency_key", "")).strip() if isinstance(nl_route, dict) else ""

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": "success",
        "trace_id": trace_id,
        "event": {
            "channel": channel,
            "action": str(event.get("action", "received")),
            "account_id": event["account_id"],
            "conversation_id": str(event.get("conversation_id", "")),
            "peer_id": event["peer_id"],
            "channel_id": event["channel_id"],
            "channel_name": event.get("channel_name", ""),
            "domain_slug": event.get("domain_slug", ""),
            "thread_id": event["thread_id"],
            "message_id": event["message_id"],
        },
        "session_id": session_id,
        "labels": labels,
        "nl_skill_route": nl_route,
        "primary_intent": intent.get("primary_intent", "chat_normal"),
        "discord_domain": domain_info,
        "actions": actions,
        "version": 1,
    }
    record_event(
        canonical_root,
        {
            "kind": "tooling",
            "trace_id": trace_id,
            "channel": channel,
            "success": report.get("status") == "success",
            "latency_ms": int(nl_route.get("timing", {}).get("elapsed_ms", 0)) if isinstance(nl_route, dict) else 0,
            "retry_count": 0,
            "token_estimate": max(1, len(str(event.get("text", ""))) // 4),
        },
    )

    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)
    lines = [
        "# Ingress Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Channel: `{channel}`",
        f"- Session: `{session_id}`",
        f"- Intent: `{report['primary_intent']}`",
        f"- Labels: `{', '.join(labels) if labels else 'none'}`",
        f"- Drop status: `{actions['drop'].get('status', '')}`",
        f"- Context profile: `{actions['context_profile'].get('profile', actions['context_profile'].get('status', ''))}`",
        f"- Status reply: `{actions['status_reply'].get('status', '')}`",
        f"- Episodic context: `{actions['episodic_context'].get('status', '')}`",
        f"- Research: `{actions['research'].get('status', '')}`",
        f"- Reminder: `{actions['reminder'].get('status', '')}`",
        f"- Odoo: `{actions['odoo'].get('status', '')}`",
        f"- Memory capture: `{actions['memory_capture'].get('status', '')}`",
        f"- Worker pairing: `{actions['worker_pairing'].get('status', '')}`",
        f"- Worker reply: `{actions['worker_reply'].get('status', '')}`",
        f"- SG promotion: `{actions['sg_promotion'].get('status', '')}`",
        f"- Mission activation: `{actions['mission_activation'].get('decision', actions['mission_activation'].get('status', ''))}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
    ]
    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime channel ingress adapter")
    parser.add_argument("--root", default=".")
    parser.add_argument("--event-json", default="")
    parser.add_argument("--stdin", action="store_true")
    args = parser.parse_args()

    if args.stdin:
        raw_payload = _load_json(sys.stdin.read())
    elif args.event_json:
        raw_payload = _load_json(args.event_json)
    else:
        parser.error("Provide --event-json <json|path> or --stdin")

    out = handle_runtime_event(args.root, raw_payload)
    print(
        json.dumps(
            {
                "status": out.get("status", "error"),
                "session_id": out.get("session_id", ""),
                "primary_intent": out.get("primary_intent", ""),
                "labels": out.get("labels", []),
                "paths": {
                    "json": REPORT_JSON.as_posix(),
                    "markdown": REPORT_MD.as_posix(),
                    "log": REPORT_LOG.as_posix(),
                },
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

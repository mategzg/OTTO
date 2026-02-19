#!/usr/bin/env python3
"""Channel runtime session memory manager."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.repo_root import get_canonical_root

POLICY_PATH = Path("state/channel_runtime_policy.json")
SESSIONS_ROOT = Path("state/sessions")
RUNTIME_JSON = Path("docs/_inbox/runtime_report_latest.json")
RUNTIME_MD = Path("docs/_inbox/runtime_report_latest.md")
RUNTIME_LOG = Path("logs/runtime_latest.json")

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "session_id_schema": {
        "version": 1,
        "fields": [
            "agent_id",
            "channel",
            "account_id",
            "chat_type",
            "peer_id",
            "channel_id",
            "thread_id",
        ],
        "prefix": "rtm:v1",
        "hash_algo": "sha1",
        "id_prefix": "sid_",
        "id_length": 16,
    },
    "tiers": {
        "telegram_owner": {
            "rolling_max_events": 400,
            "rolling_max_chars": 240000,
            "summary_max_chars": 8000,
            "compact_trigger_events": 160,
            "compact_trigger_chars": 120000,
            "distill_inactive_hours": 0,
            "max_facts_per_compact": 120,
        },
        "discord_domain": {
            "rolling_max_events": 220,
            "rolling_max_chars": 120000,
            "summary_max_chars": 4000,
            "compact_trigger_events": 90,
            "compact_trigger_chars": 60000,
            "distill_inactive_hours": 0,
            "max_facts_per_compact": 80,
        },
        "discord_thread": {
            "rolling_max_events": 180,
            "rolling_max_chars": 90000,
            "summary_max_chars": 2500,
            "compact_trigger_events": 70,
            "compact_trigger_chars": 45000,
            "distill_inactive_hours": 24,
            "max_facts_per_compact": 64,
        },
        "whatsapp_client": {
            "rolling_max_events": 60,
            "rolling_max_chars": 20000,
            "summary_max_chars": 700,
            "compact_trigger_events": 24,
            "compact_trigger_chars": 8000,
            "distill_inactive_hours": 0,
            "max_facts_per_compact": 20,
        },
        "whatsapp_worker": {
            "rolling_max_events": 120,
            "rolling_max_chars": 45000,
            "summary_max_chars": 1500,
            "compact_trigger_events": 45,
            "compact_trigger_chars": 18000,
            "distill_inactive_hours": 0,
            "max_facts_per_compact": 36,
        },
    },
    "heartbeat_limits": {
        "max_sessions_per_tick": 12,
        "max_compactions_per_tick": 8,
        "max_distill_per_tick": 4,
        "max_runtime_seconds": 300,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_iso(value: str) -> Optional[datetime]:
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


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


def _read_ndjson(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_ndjson(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _normalize_component(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "_"
    out = []
    prev_sep = False
    for ch in text:
        ok = ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in {"-", "_", "."}
        if ok:
            out.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out.append("_")
            prev_sep = True
    normalized = "".join(out).strip("_")
    return normalized or "_"


def _load_policy(root: Path) -> Dict[str, Any]:
    payload = _load_json(root / POLICY_PATH)
    merged: Dict[str, Any] = json.loads(json.dumps(DEFAULT_POLICY))
    if payload:
        merged.update(payload)
        merged["session_id_schema"] = dict(DEFAULT_POLICY["session_id_schema"]) | dict(payload.get("session_id_schema", {}))
        merged["heartbeat_limits"] = dict(DEFAULT_POLICY["heartbeat_limits"]) | dict(payload.get("heartbeat_limits", {}))
        merged_tiers = dict(DEFAULT_POLICY["tiers"])
        for tier_name, tier_cfg in payload.get("tiers", {}).items():
            if isinstance(tier_cfg, dict):
                merged_tiers[tier_name] = dict(DEFAULT_POLICY["tiers"].get(tier_name, {})) | tier_cfg
        merged["tiers"] = merged_tiers
    if not (root / POLICY_PATH).is_file():
        _save_json(root / POLICY_PATH, merged)
    return merged


def _default_meta(session_id: str, session_key: str, tier: str, identity: Dict[str, str]) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "session_key": session_key,
        "tier": tier,
        "identity": identity,
        "created_at": _utc_now(),
        "last_activity": "",
        "rolling_events": 0,
        "rolling_chars": 0,
        "event_count_total": 0,
        "compaction_count": 0,
        "distill_count": 0,
        "last_compact_at": "",
        "last_distilled_at": "",
        "last_distilled_activity": "",
        "channel_id": "",
        "channel_name_last_seen": "",
        "domain_slug": "",
        "recommended_domain": "",
    }


def _event_chars(event: Dict[str, Any]) -> int:
    return len(str(event.get("text", "")))


def _resolve_tier(event: Dict[str, Any]) -> str:
    channel = _normalize_component(event.get("channel", ""))
    thread_id = _normalize_component(event.get("thread_id", ""))
    actor_type = _normalize_component(event.get("actor_type", ""))
    labels = [str(item).strip().lower() for item in event.get("labels", []) if str(item).strip()]

    if channel.startswith("telegram"):
        return "telegram_owner"
    if channel.startswith("discord"):
        if thread_id != "_":
            return "discord_thread"
        return "discord_domain"
    if channel.startswith("whatsapp"):
        if actor_type == "worker" or "requires_worker_auth" in labels:
            return "whatsapp_worker"
        return "whatsapp_client"
    return "discord_domain"


def build_session_id(event: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    schema = policy.get("session_id_schema", {})
    fields: List[str] = list(schema.get("fields", []))
    if not fields:
        fields = list(DEFAULT_POLICY["session_id_schema"]["fields"])

    tier = _resolve_tier(event)
    normalized: Dict[str, str] = {}
    for field in fields:
        if field == "agent_id":
            normalized[field] = _normalize_component(event.get(field, "otto"))
        else:
            normalized[field] = _normalize_component(event.get(field, ""))

    tuple_raw = "|".join(normalized[field] for field in fields)
    prefix = str(schema.get("prefix", "rtm:v1"))
    session_key = f"{prefix}:{tuple_raw}"
    digest = hashlib.sha1(session_key.encode("utf-8")).hexdigest()
    sid_len = int(schema.get("id_length", 16))
    sid_prefix = str(schema.get("id_prefix", "sid_"))
    session_id = f"{sid_prefix}{digest[: max(8, sid_len)]}"

    return {
        "session_id": session_id,
        "session_key": session_key,
        "identity": normalized,
        "tier": tier,
    }


def _session_paths(root: Path, session_id: str) -> Dict[str, Path]:
    base = root / SESSIONS_ROOT / session_id
    return {
        "base": base,
        "rolling": base / "rolling.ndjson",
        "summary": base / "summary.md",
        "facts": base / "facts.ndjson",
        "meta": base / "meta.json",
        "archive": base / "archive",
        "lock_session": base / "locks" / "session.lock",
        "lock_compact": base / "locks" / "compact.lock",
        "lock_distill": base / "locks" / "distill.lock",
    }


def _acquire_lock(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    return True


def _release_lock(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _load_meta(paths: Dict[str, Path], identity_payload: Dict[str, Any]) -> Dict[str, Any]:
    meta = _load_json(paths["meta"])
    if not meta:
        meta = _default_meta(
            identity_payload["session_id"],
            identity_payload["session_key"],
            identity_payload["tier"],
            identity_payload["identity"],
        )
    return meta


def append_event(root: str | Path, event: Dict[str, Any]) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    identity = build_session_id(event, policy)
    paths = _session_paths(canonical_root, identity["session_id"])
    paths["base"].mkdir(parents=True, exist_ok=True)

    if not _acquire_lock(paths["lock_session"]):
        raise RuntimeError(f"session lock exists for {identity['session_id']}")

    try:
        meta = _load_meta(paths, identity)
        timestamp = str(event.get("timestamp", "")).strip() or _utc_now()
        message_id = str(event.get("message_id", "")).strip() or "_"
        text = str(event.get("text", "")).strip()
        labels = sorted({str(item).strip() for item in event.get("labels", []) if str(item).strip()})
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            raw = "|".join(
                [
                    identity["session_id"],
                    message_id,
                    timestamp,
                    text[:500],
                    str(event.get("thread_id", "")),
                ]
            )
            event_id = "evt_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]

        row = {
            "event_id": event_id,
            "action": str(event.get("action", "received")),
            "message_id": message_id,
            "timestamp": timestamp,
            "channel": str(event.get("channel", "")),
            "chat_type": str(event.get("chat_type", "")),
            "peer_id": str(event.get("peer_id", "")),
            "channel_id": str(event.get("channel_id", "")),
            "channel_name": str(event.get("channel_name", "")),
            "domain_slug": str(event.get("domain_slug", "")),
            "recommended_domain": str(event.get("recommended_domain", "")),
            "thread_id": str(event.get("thread_id", "")),
            "actor_type": str(event.get("actor_type", "")),
            "labels": labels,
            "text": text,
            "attachments": event.get("attachments", []),
            "source_ref": str(event.get("source_ref", f"runtime:{identity['session_id']}#{event_id}")),
        }
        _append_ndjson(paths["rolling"], row)

        meta["last_activity"] = timestamp
        meta["rolling_events"] = int(meta.get("rolling_events", 0)) + 1
        meta["rolling_chars"] = int(meta.get("rolling_chars", 0)) + _event_chars(row)
        meta["event_count_total"] = int(meta.get("event_count_total", 0)) + 1
        if str(event.get("channel", "")).startswith("discord"):
            meta["channel_id"] = str(event.get("channel_id", ""))
            meta["channel_name_last_seen"] = str(event.get("channel_name", ""))
            meta["domain_slug"] = str(event.get("domain_slug", "") or "unknown")
            meta["recommended_domain"] = str(event.get("recommended_domain", "") or meta.get("domain_slug", "unknown"))
        _save_json(paths["meta"], meta)

        return {
            "canonical_root": str(canonical_root.resolve()),
            "session_id": identity["session_id"],
            "tier": identity["tier"],
            "event_id": event_id,
            "paths": {
                "rolling": str(paths["rolling"].resolve().relative_to(canonical_root.resolve()).as_posix()),
                "meta": str(paths["meta"].resolve().relative_to(canonical_root.resolve()).as_posix()),
            },
            "status": "ok",
        }
    finally:
        _release_lock(paths["lock_session"])


def _tier_cfg(policy: Dict[str, Any], tier: str) -> Dict[str, Any]:
    tiers = policy.get("tiers", {})
    if tier in tiers and isinstance(tiers[tier], dict):
        return tiers[tier]
    return DEFAULT_POLICY["tiers"]["discord_domain"]


def needs_compact(root: str | Path, session_id: str) -> bool:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    paths = _session_paths(canonical_root, session_id)
    meta = _load_json(paths["meta"])
    if not meta:
        return False
    cfg = _tier_cfg(policy, str(meta.get("tier", "discord_domain")))
    rolling_events = int(meta.get("rolling_events", 0))
    rolling_chars = int(meta.get("rolling_chars", 0))
    return rolling_events >= int(cfg.get("compact_trigger_events", 70)) or rolling_chars >= int(
        cfg.get("compact_trigger_chars", 45000)
    )


def _extract_facts(events: Sequence[Dict[str, Any]], max_count: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in events:
        labels = [str(item).strip().lower() for item in row.get("labels", []) if str(item).strip()]
        text = str(row.get("text", "")).strip()
        lower = text.lower()
        worthy = (
            "memory_worthy" in labels
            or "sg_worthy" in labels
            or "decision" in lower
            or "prefiero" in lower
            or "project" in lower
            or "proyecto" in lower
        )
        if not worthy or not text:
            continue
        key_seed = f"{row.get('event_id', '')}:{text[:120]}"
        fact_id = "fact_" + hashlib.sha1(key_seed.encode("utf-8")).hexdigest()[:12]
        if fact_id in seen:
            continue
        seen.add(fact_id)
        out.append(
            {
                "fact_id": fact_id,
                "event_id": str(row.get("event_id", "")),
                "captured_at": str(row.get("timestamp", "")),
                "text": text[:500],
                "source_ref": str(row.get("source_ref", "")),
                "labels": labels,
            }
        )
        if len(out) >= max(1, max_count):
            break
    return out


def compact_plan(root: str | Path, session_id: str) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    paths = _session_paths(canonical_root, session_id)
    meta = _load_json(paths["meta"])
    if not meta:
        return {"status": "missing_session", "session_id": session_id}

    cfg = _tier_cfg(policy, str(meta.get("tier", "discord_domain")))
    rows = _read_ndjson(paths["rolling"])
    if not rows:
        return {"status": "idle", "session_id": session_id, "reason": "empty_rolling"}

    max_events = max(1, int(cfg.get("rolling_max_events", 120)))
    max_chars = max(300, int(cfg.get("rolling_max_chars", 45000)))
    summary_max_chars = max(300, int(cfg.get("summary_max_chars", 1500)))
    max_facts = max(1, int(cfg.get("max_facts_per_compact", 36)))

    by_events = rows[-max_events:]
    kept_reversed: List[Dict[str, Any]] = []
    chars = 0
    for row in reversed(by_events):
        next_chars = chars + _event_chars(row)
        if kept_reversed and next_chars > max_chars:
            continue
        kept_reversed.append(row)
        chars = next_chars
    kept = list(reversed(kept_reversed)) if kept_reversed else [rows[-1]]

    keep_event_ids = {str(row.get("event_id", "")) for row in kept}
    removed = [row for row in rows if str(row.get("event_id", "")) not in keep_event_ids]
    facts = _extract_facts(rows, max_facts)

    lines = [f"# Session Summary `{session_id}`", "", "Compact summary generated automatically.", "", "## Recent Context", ""]
    for row in kept:
        who = str(row.get("actor_type", "") or row.get("peer_id", "") or "peer")
        timestamp = str(row.get("timestamp", ""))
        text = str(row.get("text", "")).replace("\n", " ").strip()
        lines.append(f"- [{timestamp}] {who}: {text[:180]}")
    summary_text = "\n".join(lines) + "\n"
    if len(summary_text) > summary_max_chars:
        summary_text = summary_text[: summary_max_chars - 1] + "\n"

    return {
        "status": "ok",
        "session_id": session_id,
        "tier": str(meta.get("tier", "discord_domain")),
        "before": {
            "rolling_events": len(rows),
            "rolling_chars": sum(_event_chars(row) for row in rows),
        },
        "after": {
            "rolling_events": len(kept),
            "rolling_chars": sum(_event_chars(row) for row in kept),
        },
        "kept": kept,
        "removed": removed,
        "facts": facts,
        "summary_text": summary_text,
        "paths": {
            "rolling": paths["rolling"].as_posix(),
            "summary": paths["summary"].as_posix(),
            "facts": paths["facts"].as_posix(),
            "meta": paths["meta"].as_posix(),
            "archive": paths["archive"].as_posix(),
        },
    }


def _archive_snapshot(paths: Dict[str, Path], rows: Sequence[Dict[str, Any]], root: Path) -> Dict[str, str]:
    stamp = _utc_stamp()
    archive_file = paths["archive"] / f"{stamp}_rolling_snapshot.ndjson"
    manifest_file = paths["archive"] / f"{stamp}_MANIFEST.json"
    paths["archive"].mkdir(parents=True, exist_ok=True)
    _write_ndjson(archive_file, rows)

    entries = []
    for idx, row in enumerate(rows, start=1):
        encoded = json.dumps(row, sort_keys=True, ensure_ascii=False)
        entries.append(
            {
                "line_no": idx,
                "event_id": str(row.get("event_id", "")),
                "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                "size": len(encoded.encode("utf-8")),
            }
        )
    _save_json(
        manifest_file,
        {
            "created_at": _utc_now(),
            "entry_count": len(rows),
            "entries": entries,
            "archive_file": archive_file.resolve().relative_to(root.resolve()).as_posix(),
            "version": 1,
        },
    )
    return {
        "archive_file": archive_file.resolve().relative_to(root.resolve()).as_posix(),
        "manifest_file": manifest_file.resolve().relative_to(root.resolve()).as_posix(),
    }


def apply_compact(root: str | Path, session_id: str) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    paths = _session_paths(canonical_root, session_id)
    if not _acquire_lock(paths["lock_compact"]):
        raise RuntimeError(f"compact lock exists for {session_id}")
    try:
        plan = compact_plan(canonical_root, session_id)
        if plan.get("status") != "ok":
            return plan

        previous_rows = _read_ndjson(paths["rolling"])
        archive_paths = _archive_snapshot(paths, previous_rows, canonical_root)
        _write_ndjson(paths["rolling"], plan["kept"])

        existing_facts = _read_ndjson(paths["facts"])
        known = {str(row.get("fact_id", "")) for row in existing_facts}
        merged = list(existing_facts)
        for row in plan["facts"]:
            if str(row.get("fact_id", "")) in known:
                continue
            merged.append(row)
        _write_ndjson(paths["facts"], merged)
        paths["summary"].parent.mkdir(parents=True, exist_ok=True)
        paths["summary"].write_text(plan["summary_text"], encoding="utf-8")

        meta = _load_json(paths["meta"])
        meta["rolling_events"] = plan["after"]["rolling_events"]
        meta["rolling_chars"] = plan["after"]["rolling_chars"]
        meta["compaction_count"] = int(meta.get("compaction_count", 0)) + 1
        meta["last_compact_at"] = _utc_now()
        if plan["kept"]:
            meta["last_activity"] = str(plan["kept"][-1].get("timestamp", meta.get("last_activity", "")))
        _save_json(paths["meta"], meta)

        return {
            "status": "success",
            "session_id": session_id,
            "tier": plan["tier"],
            "before": plan["before"],
            "after": plan["after"],
            "facts_added": max(0, len(merged) - len(existing_facts)),
            "archive": archive_paths,
            "paths": {
                "rolling": paths["rolling"].resolve().relative_to(canonical_root.resolve()).as_posix(),
                "summary": paths["summary"].resolve().relative_to(canonical_root.resolve()).as_posix(),
                "facts": paths["facts"].resolve().relative_to(canonical_root.resolve()).as_posix(),
                "meta": paths["meta"].resolve().relative_to(canonical_root.resolve()).as_posix(),
            },
        }
    finally:
        _release_lock(paths["lock_compact"])


def needs_distill(root: str | Path, session_id: str) -> bool:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    paths = _session_paths(canonical_root, session_id)
    meta = _load_json(paths["meta"])
    if not meta:
        return False
    cfg = _tier_cfg(policy, str(meta.get("tier", "discord_domain")))
    hours = int(cfg.get("distill_inactive_hours", 0))
    if hours <= 0:
        return False
    last_activity = _parse_iso(str(meta.get("last_activity", "")))
    if last_activity is None:
        return False
    last_distilled_activity = str(meta.get("last_distilled_activity", ""))
    if last_distilled_activity and last_distilled_activity == str(meta.get("last_activity", "")):
        return False
    return datetime.now(timezone.utc) - last_activity >= timedelta(hours=hours)


def _distill_target(root: Path, session_id: str) -> Path:
    base = root / "vault" / "inbox_raw" / "_pending_drop"
    base.mkdir(parents=True, exist_ok=True)
    candidate = base / f"{_utc_stamp()}_{session_id}_distill"
    idx = 1
    while candidate.exists():
        candidate = base / f"{_utc_stamp()}_{session_id}_distill_{idx}"
        idx += 1
    return candidate


def apply_distill(root: str | Path, session_id: str) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    paths = _session_paths(canonical_root, session_id)
    if not _acquire_lock(paths["lock_distill"]):
        raise RuntimeError(f"distill lock exists for {session_id}")
    try:
        if not needs_distill(canonical_root, session_id):
            return {"status": "idle", "session_id": session_id, "reason": "distill_not_needed"}

        meta = _load_json(paths["meta"])
        summary_text = paths["summary"].read_text(encoding="utf-8") if paths["summary"].is_file() else ""
        facts_rows = _read_ndjson(paths["facts"])
        target = _distill_target(canonical_root, session_id)
        source_dir = target / "source"
        source_dir.mkdir(parents=True, exist_ok=True)

        (source_dir / "thread_summary.md").write_text(summary_text or "# Thread Summary\n\nNo summary yet.\n", encoding="utf-8")

        lines = ["# Domain Learnings", "", f"Session: `{session_id}`", ""]
        for row in facts_rows[:80]:
            lines.append(f"- {str(row.get('text', '')).strip()[:220]}")
        if len(lines) <= 4:
            lines.append("- No extracted learnings.")
        (source_dir / "domain_learnings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        meta_payload = {
            "session_id": session_id,
            "tier": str(meta.get("tier", "")),
            "created_at": _utc_now(),
            "last_activity": str(meta.get("last_activity", "")),
            "source_ref": f"state/sessions/{session_id}",
            "reason": "inactive_thread_distillation",
            "version": 1,
        }
        _save_json(source_dir / "DISTILL_META.json", meta_payload)

        meta["distill_count"] = int(meta.get("distill_count", 0)) + 1
        meta["last_distilled_at"] = _utc_now()
        meta["last_distilled_activity"] = str(meta.get("last_activity", ""))
        _save_json(paths["meta"], meta)

        return {
            "status": "success",
            "session_id": session_id,
            "target_rel": target.resolve().relative_to(canonical_root.resolve()).as_posix(),
            "source_files": [
                (source_dir / "thread_summary.md").resolve().relative_to(canonical_root.resolve()).as_posix(),
                (source_dir / "domain_learnings.md").resolve().relative_to(canonical_root.resolve()).as_posix(),
                (source_dir / "DISTILL_META.json").resolve().relative_to(canonical_root.resolve()).as_posix(),
            ],
        }
    finally:
        _release_lock(paths["lock_distill"])


def run_session_maintenance(
    root: str | Path,
    *,
    max_sessions: int = 12,
    max_compactions: int = 8,
    max_distills: int = 4,
    max_runtime_seconds: int = 300,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = _load_policy(canonical_root)
    limits = policy.get("heartbeat_limits", {})
    max_sessions_eff = max(0, min(max_sessions, int(limits.get("max_sessions_per_tick", max_sessions))))
    max_compact_eff = max(0, min(max_compactions, int(limits.get("max_compactions_per_tick", max_compactions))))
    max_distill_eff = max(0, min(max_distills, int(limits.get("max_distill_per_tick", max_distills))))
    runtime_limit = max(30, min(max_runtime_seconds, int(limits.get("max_runtime_seconds", max_runtime_seconds))))

    start = time.time()
    session_root = canonical_root / SESSIONS_ROOT
    session_root.mkdir(parents=True, exist_ok=True)
    session_dirs = [item for item in sorted(session_root.iterdir(), key=lambda p: p.name) if item.is_dir()]

    scanned = 0
    compacted: List[Dict[str, Any]] = []
    distilled: List[Dict[str, Any]] = []
    errors: List[str] = []

    for session_dir in session_dirs:
        if scanned >= max_sessions_eff:
            break
        if (time.time() - start) > runtime_limit:
            break
        scanned += 1
        sid = session_dir.name

        try:
            if len(compacted) < max_compact_eff and needs_compact(canonical_root, sid):
                compacted.append(apply_compact(canonical_root, sid))
        except Exception as exc:
            errors.append(f"compact:{sid}:{exc}")

        try:
            if len(distilled) < max_distill_eff and needs_distill(canonical_root, sid):
                distilled.append(apply_distill(canonical_root, sid))
        except Exception as exc:
            errors.append(f"distill:{sid}:{exc}")

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "summary": {
            "sessions_total": len(session_dirs),
            "sessions_scanned": scanned,
            "compactions_done": len(compacted),
            "distills_done": len(distilled),
            "errors": len(errors),
            "runtime_seconds": round(time.time() - start, 3),
        },
        "limits": {
            "max_sessions_per_tick": max_sessions_eff,
            "max_compactions_per_tick": max_compact_eff,
            "max_distill_per_tick": max_distill_eff,
            "max_runtime_seconds": runtime_limit,
        },
        "compactions": compacted,
        "distills": distilled,
        "errors": errors,
        "version": 1,
    }

    _save_json(canonical_root / RUNTIME_JSON, report)
    _save_json(canonical_root / RUNTIME_LOG, report)
    md_lines = [
        "# Runtime Report",
        "",
        f"- Sessions total: {report['summary']['sessions_total']}",
        f"- Sessions scanned: {report['summary']['sessions_scanned']}",
        f"- Compactions done: {report['summary']['compactions_done']}",
        f"- Distills done: {report['summary']['distills_done']}",
        f"- Errors: {report['summary']['errors']}",
        f"- Runtime seconds: {report['summary']['runtime_seconds']}",
        f"- JSON report: `{RUNTIME_JSON.as_posix()}`",
        f"- Log report: `{RUNTIME_LOG.as_posix()}`",
    ]
    (canonical_root / RUNTIME_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / RUNTIME_MD).write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return report


def _load_event_json(raw: str) -> Dict[str, Any]:
    if raw.strip() == "-":
        parsed = json.loads(input())
    else:
        path = Path(raw)
        if path.is_file():
            parsed = json.loads(path.read_text(encoding="utf-8"))
        else:
            parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("event payload must be a JSON object")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Session runtime memory manager")
    parser.add_argument("--root", default=".")
    parser.add_argument("--append-event", action="store_true")
    parser.add_argument("--event-json", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--distill", action="store_true")
    parser.add_argument("--maintenance", action="store_true")
    parser.add_argument("--max-sessions", type=int, default=12)
    parser.add_argument("--max-compactions", type=int, default=8)
    parser.add_argument("--max-distills", type=int, default=4)
    parser.add_argument("--max-runtime-seconds", type=int, default=300)
    args = parser.parse_args()

    if args.append_event:
        if not args.event_json:
            parser.error("--append-event requires --event-json")
        out = append_event(args.root, _load_event_json(args.event_json))
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.compact:
        if not args.session_id:
            parser.error("--compact requires --session-id")
        out = apply_compact(args.root, args.session_id)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if out.get("status") in {"success", "idle"} else 3

    if args.distill:
        if not args.session_id:
            parser.error("--distill requires --session-id")
        out = apply_distill(args.root, args.session_id)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0 if out.get("status") in {"success", "idle"} else 3

    if args.maintenance:
        out = run_session_maintenance(
            args.root,
            max_sessions=max(1, args.max_sessions),
            max_compactions=max(1, args.max_compactions),
            max_distills=max(1, args.max_distills),
            max_runtime_seconds=max(30, args.max_runtime_seconds),
        )
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    parser.error("Choose one mode: --append-event | --compact | --distill | --maintenance")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

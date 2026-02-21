#!/usr/bin/env python3
"""Select context loading profile for runtime sessions."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

try:
    from scripts.brain_query import run_brain_query
    _BRAIN_QUERY_AVAILABLE = True
except ImportError:
    _BRAIN_QUERY_AVAILABLE = False

POLICY_PATH = Path("state/context_profiles.json")
logger = logging.getLogger(__name__)

try:
    from scripts.token_budget_monitor import (
        is_savings_mode_active,
        estimate_session_tokens,
        record_session,
    )
    _TOKEN_BUDGET_AVAILABLE = True
except ImportError:
    _TOKEN_BUDGET_AVAILABLE = False

DEFAULT_PROFILES: Dict[str, Any] = {
    "version": 1,
    "profiles": {
        "heartbeat_minimal": {
            "base_paths": [
                "state/heartbeat_policy.json",
                "state/safety_switch.json",
                "state/proactivity_policy.json",
            ],
            "include_recent_memory_days": 0,
            "include_active_missions": False,
        },
        "owner_personal": {
            "base_paths": [
                "SOUL.md",
                "USER.md",
                "MEMORY.md",
                "memory/01_PROFILE_CURRENT.md",
                "memory/02_PRINCIPLES_CURRENT.md",
                "memory/03_PREFERENCES.ndjson",
                "memory/04_PROJECTS.ndjson",
                "memory/05_DECISIONS.ndjson",
                "memory/06_TIMELINE.ndjson",
            ],
            "include_recent_memory_days": 2,
            "include_active_missions": True,
        },
        "sg_worker": {
            "base_paths": [
                "SOUL.md",
                "openclaw/CONTEXT_MAP.md",
                "brain/domains/openclaw_ops/15_MISSION_ACTIVATION.md",
                "state/sg_policy.json",
            ],
            "include_recent_memory_days": 0,
            "include_active_missions": True,
        },
        "sg_client": {
            "base_paths": [
                "SOUL.md",
                "openclaw/CONTEXT_MAP.md",
                "state/sg_policy.json",
            ],
            "include_recent_memory_days": 0,
            "include_active_missions": False,
        },
        "discord_domain": {
            "base_paths": [
                "SOUL.md",
                "brain/domains/openclaw_ops/00_INDEX.md",
            ],
            "include_recent_memory_days": 0,
            "include_active_missions": True,
        },
    },
}


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


def _load_profiles(root: Path) -> Dict[str, Any]:
    path = root / POLICY_PATH
    payload = _load_json(path)
    merged = dict(DEFAULT_PROFILES)
    merged_profiles = dict(DEFAULT_PROFILES["profiles"])
    merged_profiles.update(payload.get("profiles", {}) if isinstance(payload.get("profiles"), dict) else {})
    merged["profiles"] = merged_profiles
    if not path.is_file():
        _save_json(path, merged)
    return merged


def _choose_profile(channel: str, actor_tier: str, actor_type: str) -> str:
    c = channel.lower()
    tier = actor_tier.lower()
    actor = actor_type.lower()
    if c.startswith("heartbeat") or tier.startswith("heartbeat") or actor in {"heartbeat", "system"}:
        return "heartbeat_minimal"
    if c.startswith("telegram") or tier == "telegram_owner" or actor == "owner":
        return "owner_personal"
    if c.startswith("whatsapp") and actor == "worker":
        return "sg_worker"
    if c.startswith("whatsapp") and actor == "client":
        return "sg_client"
    if c.startswith("discord"):
        return "discord_domain"
    return "owner_personal"


def _existing(root: Path, rel: str) -> Dict[str, Any]:
    path = root / rel
    return {"path": rel, "exists": path.exists()}


def _recent_memory_paths(root: Path, days: int) -> List[str]:
    if days <= 0:
        return []
    memory_dir = root / "memory"
    if not memory_dir.is_dir():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    candidates: List[tuple[float, str]] = []
    for item in memory_dir.glob("*.md"):
        if item.name in {"00_INDEX.md", "01_PROFILE_CURRENT.md", "02_PRINCIPLES_CURRENT.md"}:
            continue
        try:
            mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime >= cutoff:
            candidates.append((mtime.timestamp(), item.relative_to(root).as_posix()))
    candidates.sort(reverse=True)
    return [rel for _ts, rel in candidates[:5]]


def _active_mission_paths(root: Path) -> List[str]:
    missions_root = root / "state" / "missions"
    if not missions_root.is_dir():
        return []
    paths: List[str] = []
    for mission_dir in sorted(missions_root.iterdir()):
        if not mission_dir.is_dir():
            continue
        mission_json = mission_dir / "mission.json"
        if not mission_json.is_file():
            continue
        try:
            payload = json.loads(mission_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if str(payload.get("status", "")).lower() == "completed":
            continue
        plan = mission_dir / "PLAN.md"
        if plan.is_file():
            paths.append(plan.relative_to(root).as_posix())
    return paths[:4]


def _latest_session_summary_path(root: Path) -> str:
    summaries_root = root / "memory" / "summaries"
    if not summaries_root.is_dir():
        return ""
    candidates = [path for path in summaries_root.glob("*.md") if path.is_file()]
    if not candidates:
        return ""
    latest = sorted(candidates, key=lambda item: item.name, reverse=True)[0]
    return latest.relative_to(root).as_posix()


def _episodic_entries(root: Path) -> List[Dict[str, Any]]:
    index_path = root / "state" / "episodic_index.json"
    if not index_path.is_file():
        return []
    payload = _load_json(index_path)
    episodes = payload.get("episodes", [])
    if not isinstance(episodes, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in episodes:
        if not isinstance(row, dict):
            continue
        topic = str(row.get("topic", "")).strip()
        one_liner = str(row.get("one_liner", "")).strip()
        episode_id = str(row.get("episode_id", "")).strip()
        hint = f"{topic}: {one_liner}".strip(": ").strip()
        out.append(
            {
                "path": "state/episodic_index.json",
                "exists": True,
                "type": "episodic_index",
                "reason": "episodic_summary",
                "content_hint": hint,
                "expandable": True,
                "episode_id": episode_id,
            }
        )
    return out


def _session_budget_recorded(root: Path, session_id: str) -> bool:
    if not session_id or session_id == "unknown":
        return False
    meta_path = root / "state" / "sessions" / session_id / "meta.json"
    payload = _load_json(meta_path)
    return bool(payload.get("token_budget_recorded", False))


def _mark_session_budget_recorded(root: Path, session_id: str) -> None:
    if not session_id or session_id == "unknown":
        return
    meta_path = root / "state" / "sessions" / session_id / "meta.json"
    payload = _load_json(meta_path)
    if not payload:
        return
    payload["token_budget_recorded"] = True
    _save_json(meta_path, payload)


def load_context_plan(
    root: str | Path,
    *,
    channel: str,
    actor_tier: str = "",
    actor_type: str = "",
    topic_signals: List[str] | None = None,
    domain_slug: str = "",
    session_id: str = "",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    profiles = _load_profiles(canonical_root)
    profile_name = _choose_profile(channel, actor_tier, actor_type)
    profile_cfg = profiles["profiles"].get(profile_name, {})

    include_recent = int(profile_cfg.get("include_recent_memory_days", 0))
    include_missions = bool(profile_cfg.get("include_active_missions", False))

    entries: List[Dict[str, Any]] = []
    for rel in profile_cfg.get("base_paths", []):
        entries.append(
            {
                **_existing(canonical_root, str(rel)),
                "reason": "profile_base",
            }
        )

    if profile_name == "discord_domain":
        slug = (domain_slug or "").strip() or "unknown"
        domain_paths = [
            f"brain/domains/{slug}/00_INDEX.md",
            f"brain/cards/{slug}",
        ]
        for rel in domain_paths:
            entries.append({**_existing(canonical_root, rel), "reason": "discord_domain_inference"})

    for rel in _recent_memory_paths(canonical_root, include_recent):
        entries.append({**_existing(canonical_root, rel), "reason": "recent_memory"})

    if profile_name != "heartbeat_minimal":
        latest_summary = _latest_session_summary_path(canonical_root)
        if latest_summary:
            entries.append({**_existing(canonical_root, latest_summary), "reason": "session_summary_latest"})

    if include_missions:
        for rel in _active_mission_paths(canonical_root):
            entries.append({**_existing(canonical_root, rel), "reason": "active_mission"})

    memory_enabled = bool(include_recent > 0 or profile_name == "owner_personal")
    if memory_enabled:
        entries = _episodic_entries(canonical_root) + entries

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        path = str(item.get("path", ""))
        if not path:
            continue
        dedupe_key = path
        if str(item.get("reason", "")) == "episodic_summary":
            dedupe_key = f"{path}::{str(item.get('episode_id', '')).strip()}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)

    # Brain-index assisted selective loading for non-heartbeat profiles.
    if _BRAIN_QUERY_AVAILABLE and profile_name != "heartbeat_minimal":
        query_seed = " ".join(sorted(set(topic_signals or []))).strip()
        if query_seed:
            try:
                bq = run_brain_query(canonical_root, question=query_seed, k=4)
                for row in bq.get("results", []):
                    rel = str(row.get("path", "")).strip()
                    if not rel:
                        continue
                    if rel in seen:
                        continue
                    seen.add(rel)
                    deduped.append(
                        {
                            **_existing(canonical_root, rel),
                            "reason": "brain_index_match",
                            "content_hint": str(row.get("title", "")),
                            "score": int(row.get("score", 0)),
                        }
                    )
            except Exception as _e:
                logger.warning(f"context_loader: brain query hook falló: {_e}")

    if _TOKEN_BUDGET_AVAILABLE:
        try:
            _root = str(canonical_root)
            _session_id = session_id.strip() or "unknown"
            _channel = channel.lower().strip()
            _high_power_channel = _channel.startswith(("telegram", "discord"))

            # Owner directive: telegram/discord run in high-power mode (no strict token truncation).
            if _high_power_channel:
                logger.info(
                    "context_loader: high-power channel detected; token budget truncation bypassed "
                    f"(channel={_channel or 'unknown'})"
                )
            else:
                _savings = is_savings_mode_active(_root)
                _policy_key = "savings_mode" if _savings else "normal_mode"
                _policy_path = Path(_root) / "state" / "token_budget_policy.json"
                _limits: Dict[str, Any] = {}
                if _policy_path.exists():
                    _limits = json.loads(_policy_path.read_text(encoding="utf-8")).get(_policy_key, {})

                if bool(_limits.get("skip_brain_nodes", False)):
                    deduped = [item for item in deduped if not str(item.get("path", "")).startswith("brain/")]

                _max_files = int(_limits.get("max_files_context", 8))
                if len(deduped) > _max_files:
                    protected: List[Dict[str, Any]] = []
                    truncatable: List[Dict[str, Any]] = []
                    for item in deduped:
                        _path = str(item.get("path", ""))
                        _reason = str(item.get("reason", ""))
                        if (
                            _reason in {"active_mission", "episodic_summary", "brain_index_match"}
                            or _path.endswith("PLAN.md")
                            or "/missions/" in _path
                        ):
                            protected.append(item)
                        else:
                            truncatable.append(item)
                    remaining = max(_max_files - len(protected), 0)
                    if remaining > 0:
                        deduped = protected + truncatable[:remaining]
                    else:
                        deduped = protected
                    logger.info(
                        "context_loader: token budget limit applied "
                        f"(mode={'savings' if _savings else 'normal'}, max_files={_max_files})"
                    )
                else:
                    logger.info(f"context_loader: mode={'savings' if _savings else 'normal'}, files={len(deduped)}")

            if not _session_budget_recorded(canonical_root, _session_id):
                _paths = sorted({str(e.get("path", "")) for e in deduped if str(e.get("path", "")).strip()})
                _est = estimate_session_tokens(_paths, root=_root)
                record_session(_session_id, _est, root=_root)
                _mark_session_budget_recorded(canonical_root, _session_id)
        except Exception as _e:
            logger.warning(f"context_loader: token budget hook falló: {_e}")

    result = {
        "canonical_root": str(canonical_root.resolve()),
        "root": str(canonical_root.resolve()),
        "session_id": session_id or "unknown",
        "profile": profile_name,
        "channel": channel,
        "actor_tier": actor_tier,
        "actor_type": actor_type,
        "topic_signals": sorted(set(topic_signals or [])),
        "entries": deduped,
        "version": 1,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Return context loading profile entries")
    parser.add_argument("--root", default=".")
    parser.add_argument("--channel", required=True)
    parser.add_argument("--actor-tier", default="")
    parser.add_argument("--actor-type", default="")
    parser.add_argument("--domain-slug", default="")
    parser.add_argument("--topic-signals", default="")
    args = parser.parse_args()

    signals = [item.strip() for item in args.topic_signals.split(",") if item.strip()]
    out = load_context_plan(
        args.root,
        channel=args.channel,
        actor_tier=args.actor_tier,
        actor_type=args.actor_type,
        topic_signals=signals,
        domain_slug=args.domain_slug,
    )
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Shared MemoryOS helpers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from scripts.repo_root import get_canonical_root

MEMORY_POLICY_PATH = Path("state/memory_policy.json")
MEMORY_INBOX_PATH = Path("docs/_inbox/memory_inbox.ndjson")
MEMORY_ARCHIVE_DIR = Path("docs/_inbox/memory_inbox/_processed")

MEMORY_STREAMS = {
    "preference": Path("memory/03_PREFERENCES.ndjson"),
    "project": Path("memory/04_PROJECTS.ndjson"),
    "decision": Path("memory/05_DECISIONS.ndjson"),
    "timeline": Path("memory/06_TIMELINE.ndjson"),
    "principle": Path("memory/06_TIMELINE.ndjson"),
    "profile_fact": Path("memory/06_TIMELINE.ndjson"),
}

DERIVED_FILES = {
    "profile_current": Path("memory/01_PROFILE_CURRENT.md"),
    "principles_current": Path("memory/02_PRINCIPLES_CURRENT.md"),
}

DEFAULT_POLICY: Dict[str, Any] = {
    "schema_version": 1,
    "record_types": ["preference", "project", "decision", "timeline", "principle", "profile_fact"],
    "capture_types": ["preference", "project", "decision", "timeline", "principle", "profile_fact", "note_raw"],
    "required_common_fields": [
        "id",
        "type",
        "key",
        "captured_at",
        "source_ref",
        "confidence",
        "best_known",
        "status",
        "supersedes",
        "tags",
        "notes",
    ],
    "confidence_weights": {"high": 3, "medium": 2, "low": 1},
    "status_values": ["active", "superseded", "archived", "pending"],
    "ndjson_streams": {k: v.as_posix() for k, v in MEMORY_STREAMS.items()},
    "derived_files": {k: v.as_posix() for k, v in DERIVED_FILES.items()},
    "archive_root": MEMORY_ARCHIVE_DIR.as_posix(),
}

TOKEN_RE = re.compile(r"[a-z0-9_]+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_memory_policy(root: str | Path, *, create_if_missing: bool = True) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    path = canonical_root / MEMORY_POLICY_PATH

    payload: Dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded

    policy = dict(DEFAULT_POLICY)
    policy.update(payload)
    policy["record_types"] = list(policy.get("record_types", DEFAULT_POLICY["record_types"]))
    policy["capture_types"] = list(policy.get("capture_types", DEFAULT_POLICY["capture_types"]))
    policy["required_common_fields"] = list(
        policy.get("required_common_fields", DEFAULT_POLICY["required_common_fields"])
    )
    policy["confidence_weights"] = dict(DEFAULT_POLICY["confidence_weights"]) | dict(policy.get("confidence_weights", {}))
    policy["status_values"] = list(policy.get("status_values", DEFAULT_POLICY["status_values"]))
    policy["ndjson_streams"] = dict(DEFAULT_POLICY["ndjson_streams"]) | dict(policy.get("ndjson_streams", {}))
    policy["derived_files"] = dict(DEFAULT_POLICY["derived_files"]) | dict(policy.get("derived_files", {}))
    policy["archive_root"] = str(policy.get("archive_root", DEFAULT_POLICY["archive_root"]))

    if create_if_missing and not path.is_file():
        _save_json(path, policy)

    return policy


def ensure_memory_layout(root: str | Path) -> Dict[str, str]:
    canonical_root = get_canonical_root(root)
    load_memory_policy(canonical_root, create_if_missing=True)

    paths = {
        "memory_index": "memory/00_INDEX.md",
        "profile_current": "memory/01_PROFILE_CURRENT.md",
        "principles_current": "memory/02_PRINCIPLES_CURRENT.md",
        "preferences": "memory/03_PREFERENCES.ndjson",
        "projects": "memory/04_PROJECTS.ndjson",
        "decisions": "memory/05_DECISIONS.ndjson",
        "timeline": "memory/06_TIMELINE.ndjson",
        "inbox": MEMORY_INBOX_PATH.as_posix(),
        "archive_dir": MEMORY_ARCHIVE_DIR.as_posix(),
    }

    (canonical_root / "memory").mkdir(parents=True, exist_ok=True)
    (canonical_root / MEMORY_ARCHIVE_DIR).mkdir(parents=True, exist_ok=True)

    placeholders = {
        "memory_index": "# MemoryOS Index\n\nSee `memory/00_INDEX.md` as canonical MemoryOS hub.\n",
        "profile_current": "# Profile Current\n\nGenerated from canonical memory records.\n",
        "principles_current": "# Principles Current\n\nGenerated from canonical memory records.\n",
    }

    for key, content in placeholders.items():
        target = canonical_root / paths[key]
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    for key in ("preferences", "projects", "decisions", "timeline", "inbox"):
        target = canonical_root / paths[key]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")

    return paths


def slugify(text: str) -> str:
    out: List[str] = []
    prev_sep = False
    for ch in text.lower():
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
            prev_sep = False
            continue
        if not prev_sep:
            out.append("_")
            prev_sep = True
    value = "".join(out).strip("_")
    return value or "unknown"


def tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t]


def hash_dict(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def read_ndjson(path: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows, errors

    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            errors.append({"line_no": idx, "error": "invalid_json", "raw": line[:200]})
            continue
        if not isinstance(parsed, dict):
            errors.append({"line_no": idx, "error": "not_object", "raw": line[:200]})
            continue
        parsed["_line_no"] = idx
        parsed["_raw"] = text
        rows.append(parsed)
    return rows, errors


def write_ndjson(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            clean = {k: v for k, v in row.items() if not k.startswith("_")}
            f.write(json.dumps(clean, sort_keys=True, ensure_ascii=False) + "\n")


def append_ndjson(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in row.items() if not k.startswith("_")}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(clean, sort_keys=True, ensure_ascii=False) + "\n")


def normalize_confidence(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"high", "medium", "low"}:
        return text
    return "medium"


def confidence_weight(confidence: str, policy: Dict[str, Any]) -> int:
    weights = dict(policy.get("confidence_weights", {}))
    return int(weights.get(normalize_confidence(confidence), 2))


def parse_iso_or_fallback(text: str, fallback: str) -> str:
    value = str(text or "").strip()
    if not value:
        return fallback
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return fallback
    return value


def make_id(prefix: str, *parts: str) -> str:
    raw = "|".join(str(part) for part in parts if str(part))
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"

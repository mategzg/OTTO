#!/usr/bin/env python3
"""Append-only MemoryOS capture into docs/_inbox/memory_inbox.ndjson."""

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

from scripts.memory_common import (
    MEMORY_INBOX_PATH,
    append_ndjson,
    ensure_memory_layout,
    get_canonical_root,
    load_memory_policy,
    make_id,
    normalize_confidence,
    parse_iso_or_fallback,
    slugify,
    utc_now_iso,
)

LOG_PATH = Path("logs/memory_capture_latest.json")
RECEIPT_PATH = Path("docs/_inbox/memory_capture_receipt_latest.json")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _parse_fields(values: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in values:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        k = key.strip()
        if not k:
            continue
        out[k] = value.strip()
    return out


def _read_input(stdin_arg: str, text_arg: str) -> str:
    if stdin_arg:
        if stdin_arg == "-":
            return sys.stdin.read().strip()
        return Path(stdin_arg).read_text(encoding="utf-8").strip()
    return text_arg.strip()


def _derive_key(record_type: str, text: str, fields: Dict[str, str]) -> str:
    if record_type == "preference":
        category = slugify(fields.get("category", "general"))
        rule = slugify(fields.get("rule", text))
        return f"preference:{category}:{rule}"
    if record_type == "project":
        name = slugify(fields.get("name", text))
        return f"project:{name}"
    if record_type == "decision":
        topic = slugify(fields.get("topic", text))
        return f"decision:{topic}"
    if record_type == "principle":
        principle = slugify(fields.get("principle", text))
        return f"principle:{principle}"
    if record_type == "profile_fact":
        fact = slugify(fields.get("fact", text))
        return f"profile:{fact}"
    if record_type == "note_raw":
        return f"note_raw:{slugify(text)[:48]}"
    event = slugify(fields.get("event", text))
    return f"timeline:{event}"


def _type_payload(record_type: str, text: str, fields: Dict[str, str], captured_at: str) -> Dict[str, Any]:
    if record_type == "preference":
        examples = [item.strip() for item in fields.get("examples", "").split("|") if item.strip()]
        return {
            "category": fields.get("category", "general"),
            "rule": fields.get("rule", text),
            "examples": examples,
        }
    if record_type == "project":
        next_actions = [item.strip() for item in fields.get("next_actions", "").split("|") if item.strip()]
        return {
            "name": fields.get("name", text or "unnamed project"),
            "status_text": fields.get("status_text", text),
            "state": fields.get("state", "active"),
            "next_actions": next_actions,
            "last_update": fields.get("last_update", captured_at),
        }
    if record_type == "decision":
        return {
            "topic": fields.get("topic", text or "general"),
            "decision": fields.get("decision", text),
            "rationale": fields.get("rationale", ""),
            "outcome": fields.get("outcome", ""),
            "as_of": fields.get("as_of", captured_at),
        }
    if record_type == "principle":
        return {
            "principle": fields.get("principle", text),
            "scope": fields.get("scope", "general"),
            "as_of": fields.get("as_of", captured_at),
        }
    if record_type == "profile_fact":
        return {
            "fact": fields.get("fact", text),
            "as_of": fields.get("as_of", captured_at),
        }
    if record_type == "note_raw":
        return {
            "raw_text": text,
            "as_of": fields.get("as_of", captured_at),
        }
    return {
        "date": fields.get("date", captured_at[:10]),
        "event": fields.get("event", text),
        "context": fields.get("context", ""),
    }


def run_capture(
    root: str | Path,
    *,
    record_type: str,
    key: str,
    source_ref: str,
    confidence: str,
    tags_csv: str,
    text: str,
    fields: Dict[str, str],
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_memory_policy(canonical_root, create_if_missing=True)
    ensure_memory_layout(canonical_root)

    capture_types = set(str(item) for item in policy.get("capture_types", []))
    if record_type not in capture_types:
        raise RuntimeError(f"Unsupported capture type: {record_type}")

    captured_at = parse_iso_or_fallback(fields.get("captured_at", ""), utc_now_iso())
    source = source_ref.strip() or f"manual:{captured_at}"
    tags = [item.strip() for item in tags_csv.split(",") if item.strip()]
    normalized_key = key.strip() or _derive_key(record_type, text, fields)

    record: Dict[str, Any] = {
        "id": make_id("memin", record_type, normalized_key, captured_at, source, text[:80]),
        "type": record_type,
        "key": normalized_key,
        "captured_at": captured_at,
        "source_ref": source,
        "confidence": normalize_confidence(confidence),
        "best_known": False,
        "status": "pending",
        "supersedes": [],
        "tags": sorted(set(tags)),
        "notes": text[:500],
    }
    record.update(_type_payload(record_type, text, fields, captured_at))

    inbox_path = canonical_root / MEMORY_INBOX_PATH
    append_ndjson(inbox_path, record)

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "inbox_path": MEMORY_INBOX_PATH.as_posix(),
        "record": record,
        "status": "ok",
        "version": 1,
    }
    _save_json(canonical_root / LOG_PATH, report)
    _save_json(canonical_root / RECEIPT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Append memory record to inbox")
    parser.add_argument("--root", default=".")
    parser.add_argument("--add", action="store_true", help="append one memory record")
    parser.add_argument("--stdin", nargs="?", const="-", default="", help="read text from stdin or from provided path")
    parser.add_argument("--text", default="")
    parser.add_argument("--type", dest="record_type", default="profile_fact")
    parser.add_argument("--key", default="")
    parser.add_argument("--source-ref", default="")
    parser.add_argument("--confidence", default="medium")
    parser.add_argument("--tags", default="")
    parser.add_argument("--field", action="append", default=[], help="extra field as key=value")
    args = parser.parse_args()

    text = _read_input(args.stdin, args.text)
    fields = _parse_fields(list(args.field))
    if not text and "raw_text" in fields:
        text = fields["raw_text"]
    if not text:
        text = fields.get("fact", "")
    if not text:
        raise SystemExit("memory_capture requires text via --text or --stdin")

    out = run_capture(
        args.root,
        record_type=args.record_type,
        key=args.key,
        source_ref=args.source_ref,
        confidence=args.confidence,
        tags_csv=args.tags,
        text=text,
        fields=fields,
    )
    print(
        json.dumps(
            {
                "canonical_root": out["canonical_root"],
                "id": out["record"]["id"],
                "inbox_path": out["inbox_path"],
                "type": out["record"]["type"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

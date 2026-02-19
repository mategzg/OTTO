#!/usr/bin/env python3
"""Memory compactor: promote append-only memory inbox into canonical NDJSON streams."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.memory_common import (
    DERIVED_FILES,
    MEMORY_ARCHIVE_DIR,
    MEMORY_INBOX_PATH,
    MEMORY_STREAMS,
    confidence_weight,
    ensure_memory_layout,
    get_canonical_root,
    hash_dict,
    load_memory_policy,
    make_id,
    normalize_confidence,
    parse_iso_or_fallback,
    read_ndjson,
    slugify,
    utc_now_iso,
    utc_stamp,
    write_ndjson,
)

REPORT_JSON = Path("docs/_inbox/memory_compact_report_latest.json")
REPORT_MD = Path("docs/_inbox/memory_compact_report_latest.md")
REPORT_LOG = Path("logs/memory_compact_latest.json")
STATE_PATH = Path("state/memory_compactor_state.json")


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


def _read_raw_lines(path: Path) -> List[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _stream_for_type(record_type: str) -> Path:
    return MEMORY_STREAMS.get(record_type, MEMORY_STREAMS["timeline"])


def _derive_key(record_type: str, row: Dict[str, Any]) -> str:
    if record_type == "preference":
        return f"preference:{slugify(str(row.get('category', 'general')))}:{slugify(str(row.get('rule', row.get('notes', ''))))}"
    if record_type == "project":
        return f"project:{slugify(str(row.get('name', row.get('notes', 'project'))))}"
    if record_type == "decision":
        topic = slugify(str(row.get("topic", row.get("decision", row.get("notes", "decision")))) )
        as_of = str(row.get("as_of", "")).strip()[:10]
        return f"decision:{topic}:{as_of or 'unknown'}"
    if record_type == "principle":
        return f"principle:{slugify(str(row.get('principle', row.get('notes', 'principle'))))}"
    if record_type == "profile_fact":
        return f"profile:{slugify(str(row.get('fact', row.get('notes', 'fact'))))}"
    return f"timeline:{slugify(str(row.get('event', row.get('notes', 'event'))))}"


def _note_raw_to_type(row: Dict[str, Any]) -> str:
    text = str(row.get("notes") or row.get("raw_text") or "").lower()
    if text.startswith("yo ") or text.startswith("i ") or "mi " in text or "my " in text:
        return "profile_fact"
    return "timeline"


def _normalize_record(
    row: Dict[str, Any],
    *,
    policy: Dict[str, Any],
    default_now: str,
    source_kind: str,
) -> Tuple[Dict[str, Any] | None, str]:
    record_type = str(row.get("type", "")).strip() or "timeline"
    if record_type == "note_raw":
        record_type = _note_raw_to_type(row)

    valid_types = set(policy.get("record_types", []))
    if record_type not in valid_types:
        return None, f"unsupported_type:{record_type}"

    captured_at = parse_iso_or_fallback(str(row.get("captured_at", "")), default_now)
    source_ref = str(row.get("source_ref", "")).strip() or f"manual:{captured_at}"
    notes = str(row.get("notes") or row.get("raw_text") or row.get("fact") or row.get("event") or "").strip()

    key = str(row.get("key", "")).strip() or _derive_key(record_type, row)
    confidence = normalize_confidence(str(row.get("confidence", "medium")))

    normalized: Dict[str, Any] = {
        "id": str(row.get("id", "")).strip() or make_id("mem", record_type, key, captured_at, source_ref, notes[:80]),
        "type": record_type,
        "key": key,
        "captured_at": captured_at,
        "source_ref": source_ref,
        "confidence": confidence,
        "best_known": bool(row.get("best_known", False)),
        "status": str(row.get("status", "pending") or "pending"),
        "supersedes": list(row.get("supersedes", [])) if isinstance(row.get("supersedes"), list) else [],
        "tags": sorted({str(tag).strip() for tag in row.get("tags", []) if str(tag).strip()}) if isinstance(row.get("tags"), list) else [],
        "notes": notes[:500],
        "_source_kind": source_kind,
        "_line_no": row.get("_line_no", 0),
        "_raw": row.get("_raw", ""),
    }

    if record_type == "preference":
        normalized["category"] = str(row.get("category", "general"))
        normalized["rule"] = str(row.get("rule", notes))
        examples = row.get("examples", [])
        if not isinstance(examples, list):
            examples = []
        normalized["examples"] = [str(item) for item in examples if str(item).strip()]
    elif record_type == "project":
        normalized["name"] = str(row.get("name", notes or "unnamed project"))
        normalized["status_text"] = str(row.get("status_text", notes))
        normalized["state"] = str(row.get("state", "active"))
        next_actions = row.get("next_actions", [])
        if not isinstance(next_actions, list):
            next_actions = []
        normalized["next_actions"] = [str(item) for item in next_actions if str(item).strip()]
        normalized["last_update"] = parse_iso_or_fallback(str(row.get("last_update", "")), captured_at)
    elif record_type == "decision":
        normalized["topic"] = str(row.get("topic", notes or "general"))
        normalized["decision"] = str(row.get("decision", notes))
        normalized["rationale"] = str(row.get("rationale", ""))
        normalized["outcome"] = str(row.get("outcome", ""))
        normalized["as_of"] = parse_iso_or_fallback(str(row.get("as_of", "")), captured_at)
    elif record_type == "timeline":
        normalized["date"] = str(row.get("date", captured_at[:10]))
        normalized["event"] = str(row.get("event", notes))
        normalized["context"] = str(row.get("context", ""))
    elif record_type == "principle":
        normalized["principle"] = str(row.get("principle", notes))
        normalized["scope"] = str(row.get("scope", "general"))
        normalized["as_of"] = parse_iso_or_fallback(str(row.get("as_of", "")), captured_at)
    elif record_type == "profile_fact":
        normalized["fact"] = str(row.get("fact", notes))
        normalized["as_of"] = parse_iso_or_fallback(str(row.get("as_of", "")), captured_at)

    cleaned = {k: v for k, v in normalized.items() if not k.startswith("_")}
    normalized["_content_hash"] = hash_dict(cleaned)
    return normalized, ""


def _quality_tuple(row: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[int, str, str]:
    base = confidence_weight(str(row.get("confidence", "medium")), policy)
    explicit = 0
    for key, value in row.items():
        if key.startswith("_") or key in {
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
        }:
            continue
        if isinstance(value, list):
            explicit += len([item for item in value if str(item).strip()])
        elif str(value).strip():
            explicit += 1
    return (base + explicit, str(row.get("captured_at", "")), str(row.get("id", "")))


def _load_existing_records(root: Path, policy: Dict[str, Any], now_iso: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    existing: List[Dict[str, Any]] = []
    errors: List[str] = []

    seen_streams = sorted(set(str(path) for path in policy.get("ndjson_streams", {}).values()))
    for rel in seen_streams:
        records, parse_errors = read_ndjson(root / rel)
        for item in parse_errors:
            errors.append(f"existing_parse_error:{rel}:line={item.get('line_no', 0)}:{item.get('error', 'unknown')}")
        for record in records:
            normalized, err = _normalize_record(record, policy=policy, default_now=now_iso, source_kind="existing")
            if normalized is None:
                errors.append(f"existing_invalid_type:{rel}:{err}")
                continue
            existing.append(normalized)

    return existing, errors


def _rebuild_best_known(rows: List[Dict[str, Any]], policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_key.setdefault(str(row["key"]), []).append(row)

    final_rows: List[Dict[str, Any]] = []
    for key in sorted(by_key):
        group = by_key[key]
        ranked = sorted(group, key=lambda item: _quality_tuple(item, policy), reverse=True)
        winner = ranked[0]
        superseded_ids = sorted({str(item["id"]) for item in ranked[1:] if str(item.get("id", "")).strip()})

        winner_clean = dict(winner)
        winner_clean["best_known"] = True
        winner_clean["status"] = "active"
        existing_supersedes = winner_clean.get("supersedes", []) if isinstance(winner_clean.get("supersedes"), list) else []
        winner_clean["supersedes"] = sorted({str(item) for item in existing_supersedes if str(item).strip()} | set(superseded_ids))
        final_rows.append(winner_clean)

        for item in ranked[1:]:
            loser = dict(item)
            loser["best_known"] = False
            loser["status"] = "superseded"
            loser["supersedes"] = []
            final_rows.append(loser)

    final_rows.sort(key=lambda item: (str(item["key"]), str(item.get("captured_at", "")), str(item.get("id", ""))))
    return final_rows


def _render_profile_current(rows: List[Dict[str, Any]]) -> str:
    active_profile = [
        item
        for item in rows
        if item.get("type") == "profile_fact" and bool(item.get("best_known")) and str(item.get("status")) == "active"
    ]
    active_projects = [
        item
        for item in rows
        if item.get("type") == "project" and bool(item.get("best_known")) and str(item.get("status")) == "active"
    ]

    lines: List[str] = ["# Profile Current", "", "Generated from canonical MemoryOS NDJSON.", "", "## Best Known Facts", ""]
    if not active_profile:
        lines.append("- No profile facts promoted yet.")
    else:
        for item in active_profile:
            lines.append(f"- {item.get('fact', item.get('notes', ''))} (`{item.get('id', '')}`)")

    lines.extend(["", "## Active Projects", ""])
    if not active_projects:
        lines.append("- No active projects promoted yet.")
    else:
        for item in active_projects:
            lines.append(f"- {item.get('name', '')}: {item.get('status_text', '')} (`{item.get('id', '')}`)")

    return "\n".join(lines) + "\n"


def _render_principles_current(rows: List[Dict[str, Any]]) -> str:
    active = [
        item
        for item in rows
        if item.get("type") == "principle" and bool(item.get("best_known")) and str(item.get("status")) == "active"
    ]
    superseded = [item for item in rows if item.get("type") == "principle" and str(item.get("status")) == "superseded"]

    lines: List[str] = ["# Principles Current", "", "Generated from canonical MemoryOS NDJSON.", "", "## Active", ""]
    if not active:
        lines.append("- No active principles promoted yet.")
    else:
        for item in active:
            lines.append(f"- {item.get('principle', item.get('notes', ''))} (`{item.get('id', '')}`)")

    lines.extend(["", "## Superseded", ""])
    if not superseded:
        lines.append("- None.")
    else:
        for item in sorted(superseded, key=lambda x: (str(x.get("captured_at", "")), str(x.get("id", ""))), reverse=True)[:20]:
            lines.append(f"- {item.get('principle', item.get('notes', ''))} (`{item.get('id', '')}`)")

    return "\n".join(lines) + "\n"


def _archive_processed(
    root: Path,
    *,
    processed_rows: List[Dict[str, Any]],
    batch_id: str,
    stamp: str,
    inbox_rel: Path,
) -> Dict[str, str]:
    archive_dir = root / MEMORY_ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_file = archive_dir / f"{stamp}_{batch_id}.ndjson"
    manifest_file = archive_dir / f"{stamp}_{batch_id}_MANIFEST.json"

    clean_rows: List[Dict[str, Any]] = []
    entries: List[Dict[str, Any]] = []
    for idx, row in enumerate(processed_rows, start=1):
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        clean_rows.append(clean)
        encoded = json.dumps(clean, sort_keys=True, ensure_ascii=False)
        entries.append(
            {
                "line_no": idx,
                "sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
                "size": len(encoded.encode("utf-8")),
                "id": clean.get("id", ""),
                "type": clean.get("type", ""),
            }
        )

    with archive_file.open("w", encoding="utf-8") as f:
        for row in clean_rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")

    manifest = {
        "archive_file": archive_file.resolve().relative_to(root.resolve()).as_posix(),
        "batch_id": batch_id,
        "created_at": utc_now_iso(),
        "entry_count": len(clean_rows),
        "entries": entries,
        "inbox_path": inbox_rel.as_posix(),
        "version": 1,
    }
    _save_json(manifest_file, manifest)

    return {
        "archive_file": archive_file.resolve().relative_to(root.resolve()).as_posix(),
        "manifest": manifest_file.resolve().relative_to(root.resolve()).as_posix(),
    }


def memory_status(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    ensure_memory_layout(canonical_root)

    inbox = canonical_root / MEMORY_INBOX_PATH
    inbox_rows, inbox_errors = read_ndjson(inbox)
    pending_count = len(inbox_rows) + len(inbox_errors)

    state = _load_json(canonical_root / STATE_PATH)
    index_state = _load_json(canonical_root / "state/memory_index.json")

    best_known_totals: Dict[str, int] = {}
    for rel in sorted(set(path.as_posix() for path in MEMORY_STREAMS.values())):
        rows, _ = read_ndjson(canonical_root / rel)
        for row in rows:
            if bool(row.get("best_known")) and str(row.get("status", "")) == "active":
                t = str(row.get("type", "unknown"))
                best_known_totals[t] = best_known_totals.get(t, 0) + 1

    return {
        "canonical_root": str(canonical_root.resolve()),
        "inbox_pending": pending_count,
        "last_compact": str(state.get("last_run_utc", "")),
        "last_index": str(index_state.get("updated_at", "")),
        "best_known_totals": dict(sorted(best_known_totals.items())),
    }


def run_memory_compact(root: str | Path, *, inbox_rel: str = MEMORY_INBOX_PATH.as_posix(), apply: bool = True) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_memory_policy(canonical_root, create_if_missing=True)
    ensure_memory_layout(canonical_root)

    now_iso = utc_now_iso()
    inbox_path = canonical_root / inbox_rel
    raw_lines = _read_raw_lines(inbox_path)

    inbox_rows, inbox_parse_errors = read_ndjson(inbox_path)
    existing_rows, existing_errors = _load_existing_records(canonical_root, policy, now_iso)

    invalid: List[Dict[str, Any]] = []
    for item in inbox_parse_errors:
        invalid.append(
            {
                "line_no": int(item.get("line_no", 0)),
                "error": str(item.get("error", "invalid_json")),
                "raw": str(item.get("raw", "")),
            }
        )

    normalized_incoming: List[Dict[str, Any]] = []
    for row in inbox_rows:
        normalized, err = _normalize_record(row, policy=policy, default_now=now_iso, source_kind="inbox")
        if normalized is None:
            invalid.append(
                {
                    "line_no": int(row.get("_line_no", 0)),
                    "error": err,
                    "raw": str(row.get("_raw", "")),
                }
            )
            continue
        normalized_incoming.append(normalized)

    seen_by_key_hash: set[tuple[str, str]] = set()
    deduped_incoming: List[Dict[str, Any]] = []
    duplicate_count = 0
    for row in sorted(normalized_incoming, key=lambda x: (str(x.get("key", "")), str(x.get("_content_hash", "")), str(x.get("id", "")))):
        marker = (str(row["key"]), str(row["_content_hash"]))
        if marker in seen_by_key_hash:
            duplicate_count += 1
            continue
        seen_by_key_hash.add(marker)
        deduped_incoming.append(row)

    grouped_incoming: Dict[str, set[str]] = {}
    for row in deduped_incoming:
        grouped_incoming.setdefault(str(row["key"]), set()).add(str(row["_content_hash"]))
    high_impact_keys = sorted([key for key, hashes in grouped_incoming.items() if len(hashes) > 100])

    merged = list(existing_rows) + deduped_incoming
    final_rows = _rebuild_best_known(merged, policy)

    by_stream: Dict[str, List[Dict[str, Any]]] = {}
    for row in final_rows:
        rel = _stream_for_type(str(row.get("type", "timeline"))).as_posix()
        by_stream.setdefault(rel, []).append(row)

    for rel in by_stream:
        by_stream[rel].sort(key=lambda item: (str(item.get("key", "")), str(item.get("captured_at", "")), str(item.get("id", ""))))

    summary = {
        "incoming_total": len(inbox_rows),
        "incoming_valid": len(normalized_incoming),
        "incoming_invalid": len(invalid),
        "incoming_deduped": len(deduped_incoming),
        "incoming_duplicates": duplicate_count,
        "existing_records": len(existing_rows),
        "final_records": len(final_rows),
        "best_known_active": sum(1 for row in final_rows if bool(row.get("best_known")) and str(row.get("status")) == "active"),
    }

    errors: List[str] = []
    errors.extend(existing_errors)
    if high_impact_keys:
        errors.append(f"high_impact_conflicts:{len(high_impact_keys)}")

    status = "plan"
    archive_paths: Dict[str, str] = {}
    written_streams: List[str] = []

    if apply and not high_impact_keys:
        for rel, rows in sorted(by_stream.items()):
            write_ndjson(canonical_root / rel, rows)
            written_streams.append(rel)

        (canonical_root / DERIVED_FILES["profile_current"]).write_text(_render_profile_current(final_rows), encoding="utf-8")
        (canonical_root / DERIVED_FILES["principles_current"]).write_text(_render_principles_current(final_rows), encoding="utf-8")

        processed_rows = [row for row in normalized_incoming]
        if processed_rows:
            batch_basis = "\n".join(f"{item.get('id','')}:{item.get('_line_no',0)}" for item in processed_rows)
            batch_id = hashlib.sha1(batch_basis.encode("utf-8")).hexdigest()[:10]
            stamp = utc_stamp()
            archive_paths = _archive_processed(
                canonical_root,
                processed_rows=processed_rows,
                batch_id=batch_id,
                stamp=stamp,
                inbox_rel=Path(inbox_rel),
            )

        invalid_by_line = {int(item.get("line_no", 0)): item for item in invalid if int(item.get("line_no", 0)) > 0}
        retained_lines: List[str] = []
        for idx, line in enumerate(raw_lines, start=1):
            if idx in invalid_by_line:
                retained_lines.append(line)
        inbox_path.write_text(("\n".join(retained_lines) + ("\n" if retained_lines else "")), encoding="utf-8")

        status = "success"
    elif apply and high_impact_keys:
        status = "blocked"
    else:
        status = "plan"

    compactor_state = {
        "last_run_utc": now_iso,
        "last_status": status,
        "last_summary": summary,
        "last_errors": errors,
        "high_impact_keys": high_impact_keys,
        "archive_paths": archive_paths,
        "written_streams": written_streams,
        "version": 1,
    }
    if apply:
        _save_json(canonical_root / STATE_PATH, compactor_state)

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": now_iso,
        "status": status,
        "apply": apply,
        "errors": errors,
        "high_impact_keys": high_impact_keys,
        "summary": summary,
        "written_streams": written_streams,
        "archive": archive_paths,
        "invalid_entries": invalid,
        "version": 1,
    }

    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines = [
        "# Memory Compact Report",
        "",
        f"- Status: `{status}`",
        f"- Apply mode: `{apply}`",
        f"- Inbox path: `{inbox_rel}`",
        f"- Incoming total: {summary['incoming_total']}",
        f"- Incoming valid: {summary['incoming_valid']}",
        f"- Incoming invalid: {summary['incoming_invalid']}",
        f"- Incoming deduped: {summary['incoming_deduped']}",
        f"- Existing records: {summary['existing_records']}",
        f"- Final records: {summary['final_records']}",
        f"- Best known active: {summary['best_known_active']}",
        f"- Archive file: `{archive_paths.get('archive_file', '')}`",
        f"- Archive manifest: `{archive_paths.get('manifest', '')}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Written Streams",
        "",
    ]
    if written_streams:
        for rel in written_streams:
            lines.append(f"- `{rel}`")
    else:
        lines.append("- None.")

    lines.extend(["", "## Errors", ""])
    if errors:
        for err in errors:
            lines.append(f"- {err}")
    else:
        lines.append("- None.")

    lines.extend(["", "## Invalid Entries", ""])
    if invalid:
        for item in invalid[:50]:
            lines.append(f"- line={item.get('line_no', 0)} error={item.get('error', '')}")
    else:
        lines.append("- None.")

    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "report": report,
        "paths": {
            "json": REPORT_JSON.as_posix(),
            "markdown": REPORT_MD.as_posix(),
            "log": REPORT_LOG.as_posix(),
            "state": STATE_PATH.as_posix(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compact MemoryOS inbox into canonical streams")
    parser.add_argument("--root", default=".")
    parser.add_argument("--inbox", default=MEMORY_INBOX_PATH.as_posix())
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()

    if args.apply and args.plan:
        parser.error("Use either --apply or --plan")

    apply_mode = True
    if args.plan:
        apply_mode = False

    out = run_memory_compact(args.root, inbox_rel=args.inbox, apply=apply_mode)
    report = out["report"]
    print(
        json.dumps(
            {
                "canonical_root": report["canonical_root"],
                "status": report["status"],
                "summary": report["summary"],
                "paths": out["paths"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] in {"success", "plan"} else 3


if __name__ == "__main__":
    raise SystemExit(main())

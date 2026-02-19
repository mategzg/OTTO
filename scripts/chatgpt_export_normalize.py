#!/usr/bin/env python3
"""Detect and normalize ChatGPT exports from intake sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

SOURCES_ROOT = Path("vault/inbox_raw/sources")
STATE_PATH = Path("state/intake_state.json")

REPORT_JSON = Path("docs/_inbox/chatgpt_normalize_report_latest.json")
REPORT_MD = Path("docs/_inbox/chatgpt_normalize_report_latest.md")
REPORT_LOG = Path("logs/chatgpt_normalize_latest.json")

DEFAULT_MAX_MSGS_PER_SLICE = 1500
DEFAULT_MAX_CHARS_PER_SLICE = 250000

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


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


def _iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        current = Path(dirpath)
        for filename in sorted(filenames):
            fp = current / filename
            if fp.is_symlink():
                continue
            yield fp


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _parse_created_at(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
        except Exception:
            return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        try:
            return datetime.fromtimestamp(float(text), timezone.utc).isoformat()
        except Exception:
            return ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return ""


def _clean_text(value: str) -> str:
    text = unescape(value)
    text = TAG_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _source_dirs(root: Path) -> List[Path]:
    path = root / SOURCES_ROOT
    if not path.is_dir():
        return []
    return [item for item in sorted(path.iterdir(), key=lambda p: p.name) if item_is_source_dir(item)]


def item_is_source_dir(path: Path) -> bool:
    return path.is_dir() and (path / "source").exists()


def _source_id_from_dir(source_dir: Path) -> str:
    bits = source_dir.name.split("_")
    return bits[-1] if bits else source_dir.name


def _find_source_dir(root: Path, source_id: str) -> Optional[Path]:
    for source_dir in _source_dirs(root):
        if _source_id_from_dir(source_dir) == source_id or source_dir.name.endswith(f"_{source_id}"):
            return source_dir
    return None


def _detect_chatgpt(source_dir: Path) -> Dict[str, Any]:
    payload = source_dir / "source"
    file_paths = sorted(_iter_files(payload), key=lambda p: p.as_posix())
    lower_names = [p.name.lower() for p in file_paths]

    score = 0
    reasons: List[str] = []
    if "conversations.json" in lower_names:
        score += 8
        reasons.append("conversations_json")

    for fp in file_paths[:300]:
        name = fp.name.lower()
        if name.endswith(".json"):
            try:
                text = fp.read_text(encoding="utf-8")[:20000]
            except Exception:
                continue
            lowered = text.lower()
            if "conversation_id" in lowered:
                score += 3
                reasons.append(f"conversation_id:{name}")
            if "mapping" in lowered and "message" in lowered:
                score += 3
                reasons.append(f"mapping_message:{name}")
            if "create_time" in lowered:
                score += 1
                reasons.append(f"create_time:{name}")
        if name.endswith(".html"):
            try:
                html = fp.read_text(encoding="utf-8", errors="replace")[:20000]
            except Exception:
                continue
            h = html.lower()
            if "chatgpt" in h:
                score += 2
                reasons.append(f"html_chatgpt:{name}")
            if "conversation" in h and "message" in h:
                score += 2
                reasons.append(f"html_conversation:{name}")

    kind = "chatgpt_export" if score >= 6 else "generic_corpus"
    return {
        "suspected_kind": kind,
        "score": score,
        "reasons": sorted(set(reasons)),
        "file_count": len(file_paths),
    }


def _parse_conversations_json(path: Path, rel_base: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], [], []

    conversations: List[Dict[str, Any]] = []
    messages: List[Dict[str, Any]] = []
    attachments: List[Dict[str, Any]] = []

    conv_items = payload if isinstance(payload, list) else [payload]
    for conv_idx, conv in enumerate(conv_items, start=1):
        if not isinstance(conv, dict):
            continue
        conv_id = str(conv.get("id") or conv.get("conversation_id") or f"conv_{conv_idx}")
        title = str(conv.get("title", ""))
        mapping = conv.get("mapping")
        conv_source_ref = rel_base.as_posix()

        conversations.append(
            {
                "conv_id": conv_id,
                "title": title,
                "source_ref": conv_source_ref,
            }
        )

        nodes: List[Tuple[str, Dict[str, Any]]] = []
        if isinstance(mapping, dict):
            for node_id, node in mapping.items():
                if isinstance(node, dict):
                    nodes.append((str(node_id), node))

        ordered = sorted(
            nodes,
            key=lambda item: (
                _parse_created_at(item[1].get("message", {}).get("create_time") if isinstance(item[1].get("message"), dict) else item[1].get("create_time")) or "",
                item[0],
            ),
        )

        for node_id, node in ordered:
            message = node.get("message") if isinstance(node, dict) else {}
            if not isinstance(message, dict):
                continue

            author = message.get("author", {})
            role = str(author.get("role", "unknown")) if isinstance(author, dict) else "unknown"
            content = message.get("content", {})
            parts = content.get("parts", []) if isinstance(content, dict) else []
            text_parts = []
            for part in parts if isinstance(parts, list) else []:
                if isinstance(part, str):
                    clean = _clean_text(part)
                    if clean:
                        text_parts.append(clean)
            text = "\n".join(text_parts).strip()
            if not text:
                continue

            created_at = _parse_created_at(message.get("create_time") or node.get("create_time"))
            msg_id = str(message.get("id") or f"msg_{node_id}")
            stable_msg_id = f"{conv_id}:{msg_id}:{_sha1(text[:120])}"

            messages.append(
                {
                    "conv_id": conv_id,
                    "msg_id": stable_msg_id,
                    "role": role,
                    "created_at": created_at,
                    "text": text,
                    "parts_meta": {"part_count": len(text_parts)},
                    "source_ref": rel_base.as_posix(),
                }
            )

            meta = message.get("metadata", {})
            if isinstance(meta, dict):
                for key in ("attachments", "files"):
                    items = meta.get(key)
                    if not isinstance(items, list):
                        continue
                    for idx, att in enumerate(items, start=1):
                        attachments.append(
                            {
                                "conv_id": conv_id,
                                "msg_id": stable_msg_id,
                                "attachment_id": f"{stable_msg_id}:att:{idx}",
                                "raw": att,
                                "source_ref": rel_base.as_posix(),
                            }
                        )

    return conversations, messages, attachments


def _parse_html_bundle(html_path: Path, rel_ref: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    text = html_path.read_text(encoding="utf-8", errors="replace")
    cleaned = _clean_text(text)
    lines = [line.strip() for line in cleaned.split(".") if line.strip()]
    conv_id = f"html:{_sha1(rel_ref.as_posix())}"

    conversations = [{"conv_id": conv_id, "title": html_path.stem, "source_ref": rel_ref.as_posix()}]
    messages: List[Dict[str, Any]] = []

    for idx, line in enumerate(lines[:500], start=1):
        msg_id = f"{conv_id}:line:{idx}:{_sha1(line[:80])}"
        messages.append(
            {
                "conv_id": conv_id,
                "msg_id": msg_id,
                "role": "unknown",
                "created_at": "",
                "text": line,
                "parts_meta": {"part_count": 1},
                "source_ref": rel_ref.as_posix(),
            }
        )

    return conversations, messages


def _slice_messages(
    messages: List[Dict[str, Any]],
    *,
    max_msgs_per_slice: int,
    max_chars_per_slice: int,
) -> Tuple[List[Dict[str, Any]], List[List[Dict[str, Any]]]]:
    ordered = sorted(messages, key=lambda m: (str(m.get("created_at", "")), str(m.get("msg_id", ""))))

    slices: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    current_chars = 0
    current_bucket = ""

    for msg in ordered:
        created_at = str(msg.get("created_at", ""))
        bucket = created_at[:7] if len(created_at) >= 7 else "undated"
        msg_chars = len(str(msg.get("text", "")))

        need_split = False
        if current and len(current) >= max_msgs_per_slice:
            need_split = True
        if current and current_chars + msg_chars > max_chars_per_slice:
            need_split = True
        if current and bucket != current_bucket:
            need_split = True

        if need_split:
            slices.append(current)
            current = []
            current_chars = 0

        if not current:
            current_bucket = bucket

        current.append(msg)
        current_chars += msg_chars

    if current:
        slices.append(current)

    index_rows: List[Dict[str, Any]] = []
    for idx, items in enumerate(slices, start=1):
        first_ts = str(items[0].get("created_at", ""))
        last_ts = str(items[-1].get("created_at", ""))
        bucket = first_ts[:7] if len(first_ts) >= 7 else "undated"
        slice_id = f"slice_{bucket}_{idx:03d}"
        index_rows.append(
            {
                "slice_id": slice_id,
                "date_range": [first_ts, last_ts],
                "msg_count": len(items),
                "char_count": sum(len(str(m.get("text", ""))) for m in items),
            }
        )

    return index_rows, slices


def _write_ndjson(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _normalize_source(
    root: Path,
    source_dir: Path,
    *,
    max_msgs_per_slice: int,
    max_chars_per_slice: int,
) -> Dict[str, Any]:
    detection = _detect_chatgpt(source_dir)
    source_rel = source_dir.resolve().relative_to(root.resolve()).as_posix()

    normalized_root = source_dir / "normalized"
    slices_root = normalized_root / "slices"

    conversations: List[Dict[str, Any]] = []
    messages: List[Dict[str, Any]] = []
    attachments: List[Dict[str, Any]] = []
    used_files: List[str] = []

    payload = source_dir / "source"
    files = sorted(_iter_files(payload), key=lambda p: p.as_posix())

    if detection["suspected_kind"] == "chatgpt_export":
        for fp in files:
            rel_ref = fp.resolve().relative_to(source_dir.resolve())
            name = fp.name.lower()
            if name == "conversations.json":
                c_rows, m_rows, a_rows = _parse_conversations_json(fp, rel_ref)
                if m_rows:
                    conversations.extend(c_rows)
                    messages.extend(m_rows)
                    attachments.extend(a_rows)
                    used_files.append(rel_ref.as_posix())
            elif name.endswith(".html") and not messages:
                c_rows, m_rows = _parse_html_bundle(fp, rel_ref)
                if m_rows:
                    conversations.extend(c_rows)
                    messages.extend(m_rows)
                    used_files.append(rel_ref.as_posix())

    result = {
        "source_id": _source_id_from_dir(source_dir),
        "source_rel": source_rel,
        "suspected_kind": detection["suspected_kind"],
        "detector_score": detection["score"],
        "detector_reasons": detection["reasons"],
        "used_files": used_files,
        "normalized": False,
        "message_count": 0,
        "conversation_count": 0,
        "slice_count": 0,
        "paths": {},
    }

    if detection["suspected_kind"] != "chatgpt_export":
        hints = _load_json(source_dir / "HINTS.json")
        hints["suspected_kind"] = "generic_corpus"
        hints["normalized_at"] = _utc_now()
        hints["normalize_status"] = "skipped_generic"
        _save_json(source_dir / "HINTS.json", hints)
        return result

    normalized_root.mkdir(parents=True, exist_ok=True)
    slices_root.mkdir(parents=True, exist_ok=True)

    # Stable sort + dedupe by msg_id
    dedup: Dict[str, Dict[str, Any]] = {}
    for msg in messages:
        dedup[str(msg["msg_id"])] = msg
    messages = sorted(dedup.values(), key=lambda m: (str(m.get("created_at", "")), str(m.get("msg_id", ""))))

    conv_dedup: Dict[str, Dict[str, Any]] = {}
    for conv in conversations:
        conv_dedup[str(conv["conv_id"])] = conv
    conversations = sorted(conv_dedup.values(), key=lambda c: str(c.get("conv_id", "")))

    _write_ndjson(normalized_root / "conversations.ndjson", conversations)
    _write_ndjson(normalized_root / "messages.ndjson", messages)
    _write_ndjson(normalized_root / "attachments.ndjson", attachments)

    slices_index_rows, slices = _slice_messages(
        messages,
        max_msgs_per_slice=max_msgs_per_slice,
        max_chars_per_slice=max_chars_per_slice,
    )

    for idx, rows in enumerate(slices, start=1):
        slice_id = slices_index_rows[idx - 1]["slice_id"]
        slice_file = slices_root / f"{slice_id}.ndjson"
        _write_ndjson(slice_file, rows)
        slices_index_rows[idx - 1]["path"] = slice_file.resolve().relative_to(source_dir.resolve()).as_posix()

    slices_index = {
        "created_at": _utc_now(),
        "source_id": _source_id_from_dir(source_dir),
        "slice_count": len(slices_index_rows),
        "slices": slices_index_rows,
        "version": 1,
    }
    _save_json(normalized_root / "slices_index.json", slices_index)

    hints = _load_json(source_dir / "HINTS.json")
    hints["suspected_kind"] = "chatgpt_export"
    hints["normalized_at"] = _utc_now()
    hints["normalize_status"] = "ok"
    hints["normalized_paths"] = {
        "conversations": "normalized/conversations.ndjson",
        "messages": "normalized/messages.ndjson",
        "attachments": "normalized/attachments.ndjson",
        "slices_index": "normalized/slices_index.json",
    }
    _save_json(source_dir / "HINTS.json", hints)

    result.update(
        {
            "normalized": True,
            "message_count": len(messages),
            "conversation_count": len(conversations),
            "slice_count": len(slices_index_rows),
            "paths": {
                "conversations": (normalized_root / "conversations.ndjson").resolve().relative_to(root.resolve()).as_posix(),
                "messages": (normalized_root / "messages.ndjson").resolve().relative_to(root.resolve()).as_posix(),
                "attachments": (normalized_root / "attachments.ndjson").resolve().relative_to(root.resolve()).as_posix(),
                "slices_index": (normalized_root / "slices_index.json").resolve().relative_to(root.resolve()).as_posix(),
            },
        }
    )
    return result


def run_normalize(
    root: str | Path,
    *,
    source_id: str = "",
    scan_latest: bool = False,
    max_msgs_per_slice: int = DEFAULT_MAX_MSGS_PER_SLICE,
    max_chars_per_slice: int = DEFAULT_MAX_CHARS_PER_SLICE,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    source_dirs = _source_dirs(canonical_root)

    targets: List[Path] = []
    if source_id:
        found = _find_source_dir(canonical_root, source_id)
        if found:
            targets = [found]
    elif scan_latest and source_dirs:
        targets = [source_dirs[-1]]
    else:
        # normalize only sources not yet normalized
        for src in source_dirs:
            hints = _load_json(src / "HINTS.json")
            if str(hints.get("normalize_status", "")) != "ok":
                targets.append(src)

    normalized_results: List[Dict[str, Any]] = []
    for src in targets:
        normalized_results.append(
            _normalize_source(
                canonical_root,
                src,
                max_msgs_per_slice=max(10, max_msgs_per_slice),
                max_chars_per_slice=max(1000, max_chars_per_slice),
            )
        )

    state = _load_json(canonical_root / STATE_PATH)
    sources_state = state.get("sources", {}) if isinstance(state.get("sources", {}), dict) else {}
    for item in normalized_results:
        sid = item["source_id"]
        if sid in sources_state:
            sources_state[sid]["normalized"] = bool(item["normalized"])
            sources_state[sid]["suspected_kind"] = item["suspected_kind"]
            sources_state[sid]["normalized_at"] = _utc_now()
    state["sources"] = sources_state
    state["last_run_utc"] = _utc_now()
    state["last_status"] = "success"
    _save_json(canonical_root / STATE_PATH, state)

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "targets": [src.resolve().relative_to(canonical_root.resolve()).as_posix() for src in targets],
        "normalized_results": normalized_results,
        "summary": {
            "target_count": len(targets),
            "chatgpt_detected_count": sum(1 for r in normalized_results if r["suspected_kind"] == "chatgpt_export"),
            "normalized_count": sum(1 for r in normalized_results if r["normalized"]),
            "slice_count": sum(int(r.get("slice_count", 0)) for r in normalized_results),
            "message_count": sum(int(r.get("message_count", 0)) for r in normalized_results),
        },
        "version": 1,
    }

    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / REPORT_LOG, report)

    lines = [
        "# ChatGPT Normalize Report",
        "",
        f"- Target count: {report['summary']['target_count']}",
        f"- ChatGPT detected: {report['summary']['chatgpt_detected_count']}",
        f"- Normalized count: {report['summary']['normalized_count']}",
        f"- Slice count: {report['summary']['slice_count']}",
        f"- Message count: {report['summary']['message_count']}",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
        "",
        "## Sources",
        "",
    ]
    if not normalized_results:
        lines.append("- None.")
    else:
        for item in normalized_results:
            lines.append(
                f"- `{item['source_rel']}` kind={item['suspected_kind']} normalized={item['normalized']} slices={item['slice_count']} messages={item['message_count']}"
            )

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
    parser = argparse.ArgumentParser(description="Normalize potential ChatGPT exports")
    parser.add_argument("--root", default=".")
    parser.add_argument("--source-id", default="")
    parser.add_argument("--scan-latest", action="store_true")
    parser.add_argument("--max-msgs-per-slice", type=int, default=DEFAULT_MAX_MSGS_PER_SLICE)
    parser.add_argument("--max-chars-per-slice", type=int, default=DEFAULT_MAX_CHARS_PER_SLICE)
    args = parser.parse_args()

    out = run_normalize(
        args.root,
        source_id=args.source_id,
        scan_latest=args.scan_latest,
        max_msgs_per_slice=args.max_msgs_per_slice,
        max_chars_per_slice=args.max_chars_per_slice,
    )
    print(
        json.dumps(
            {
                "canonical_root": out["report"]["canonical_root"],
                "summary": out["report"]["summary"],
                "paths": out["paths"],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

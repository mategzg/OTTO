#!/usr/bin/env python3
"""Build deterministic MemoryOS search index."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set
from hashlib import sha1

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.memory_common import (
    MEMORY_STREAMS,
    ensure_memory_layout,
    get_canonical_root,
    load_memory_policy,
    read_ndjson,
    utc_now_iso,
)

INDEX_PATH = Path("state/memory_index.json")
REPORT_JSON = Path("docs/_inbox/memory_index_report_latest.json")
REPORT_MD = Path("docs/_inbox/memory_index_report_latest.md")
REPORT_LOG = Path("logs/memory_index_build_latest.json")

TOKEN_RE = re.compile(r"[a-z0-9_]+")
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "about",
    "into",
    "your",
    "what",
    "when",
    "where",
    "como",
    "para",
    "con",
    "sobre",
    "este",
    "esta",
    "todo",
    "otra",
}


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _tokenize(text: str) -> List[str]:
    out: List[str] = []
    for token in TOKEN_RE.findall(text.lower()):
        if len(token) <= 2:
            continue
        if token in STOPWORDS:
            continue
        out.append(token)
    return out


def _short_text(row: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("notes", "rule", "name", "decision", "event", "principle", "fact", "status_text", "topic"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    if not parts:
        parts.append(str(row.get("key", "")))
    text = " | ".join(parts)
    return text[:280]


def _collect_memory_markdown_paths(root: Path, policy: Dict[str, Any]) -> List[Path]:
    configured = policy.get("markdown_streams", [])
    rel_paths: List[str] = []
    if isinstance(configured, list):
        rel_paths.extend(str(item).strip() for item in configured if str(item).strip())
    if not rel_paths:
        rel_paths = [
            "memory/01_PROFILE_CURRENT.md",
            "memory/02_PRINCIPLES_CURRENT.md",
            "memory/profile/*.md",
            "memory/vision/*.md",
        ]

    out: List[Path] = []
    seen: Set[str] = set()
    for rel in rel_paths:
        if any(ch in rel for ch in "*?[]"):
            for match in sorted(root.glob(rel)):
                if match.is_file() and match.suffix.lower() == ".md":
                    key = match.resolve().as_posix()
                    if key not in seen:
                        seen.add(key)
                        out.append(match)
        else:
            candidate = root / rel
            if candidate.is_file() and candidate.suffix.lower() == ".md":
                key = candidate.resolve().as_posix()
                if key not in seen:
                    seen.add(key)
                    out.append(candidate)
    return out


def _markdown_short_text(text: str) -> str:
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        if ln.startswith("#"):
            ln = ln.lstrip("#").strip()
        return ln[:280]
    return ""


def build_memory_index(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_memory_policy(canonical_root, create_if_missing=True)
    ensure_memory_layout(canonical_root)

    records: Dict[str, Dict[str, Any]] = {}
    inverted: Dict[str, Set[str]] = {}
    parse_errors: List[str] = []

    stream_paths = sorted(set(str(path) for path in policy.get("ndjson_streams", {}).values()))
    for rel in stream_paths:
        rows, errors = read_ndjson(canonical_root / rel)
        for err in errors:
            parse_errors.append(f"{rel}:line={err.get('line_no', 0)}:{err.get('error', '')}")

        for row in rows:
            record_id = str(row.get("id", "")).strip()
            if not record_id:
                continue

            short_text = _short_text(row)
            payload = {
                "id": record_id,
                "type": str(row.get("type", "")),
                "key": str(row.get("key", "")),
                "tags": list(row.get("tags", [])) if isinstance(row.get("tags"), list) else [],
                "captured_at": str(row.get("captured_at", "")),
                "source_ref": str(row.get("source_ref", "")),
                "short_text": short_text,
                "best_known": bool(row.get("best_known", False)),
                "status": str(row.get("status", "")),
                "confidence": str(row.get("confidence", "medium")),
                "stream": rel,
            }
            records[record_id] = payload

            token_basis = " ".join(
                [
                    payload["short_text"],
                    payload["key"],
                    " ".join(payload["tags"]),
                    payload["type"],
                ]
            )
            for token in sorted(set(_tokenize(token_basis))):
                inverted.setdefault(token, set()).add(record_id)

    # Index curated markdown memory maps (profile/vision/current files)
    for md_path in _collect_memory_markdown_paths(canonical_root, policy):
        rel = md_path.resolve().relative_to(canonical_root.resolve()).as_posix()
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        record_id = f"memmd-{sha1(rel.encode('utf-8')).hexdigest()[:12]}"
        short_text = _markdown_short_text(text) or rel
        md_type = "vision_doc" if rel.startswith("memory/vision/") else "profile_doc" if rel.startswith("memory/profile/") else "memory_doc"
        payload = {
            "id": record_id,
            "type": md_type,
            "key": rel,
            "tags": ["markdown", "memory_map"],
            "captured_at": utc_now_iso(),
            "source_ref": f"{rel}#md",
            "short_text": short_text,
            "best_known": True,
            "status": "active",
            "confidence": "high",
            "stream": rel,
        }
        records[record_id] = payload

        token_basis = " ".join([short_text, rel, text[:4000], md_type])
        for token in sorted(set(_tokenize(token_basis))):
            inverted.setdefault(token, set()).add(record_id)

    index = {
        "schema_version": int(policy.get("schema_version", 1)),
        "updated_at": utc_now_iso(),
        "records": dict(sorted(records.items())),
        "inverted": {token: sorted(ids) for token, ids in sorted(inverted.items())},
        "summary": {
            "record_count": len(records),
            "token_count": len(inverted),
            "parse_error_count": len(parse_errors),
        },
        "parse_errors": parse_errors,
        "version": 1,
    }
    return index


def run_memory_index_build(root: str | Path) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    index = build_memory_index(canonical_root)

    _save_json(canonical_root / INDEX_PATH, index)
    _save_json(canonical_root / REPORT_JSON, index)
    _save_json(canonical_root / REPORT_LOG, index)

    lines = [
        "# Memory Index Report",
        "",
        f"- Record count: {index['summary']['record_count']}",
        f"- Token count: {index['summary']['token_count']}",
        f"- Parse errors: {index['summary']['parse_error_count']}",
        f"- Index path: `{INDEX_PATH.as_posix()}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
        f"- Log report: `{REPORT_LOG.as_posix()}`",
    ]
    (canonical_root / REPORT_MD).write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "index": index,
        "paths": {
            "index": INDEX_PATH.as_posix(),
            "json": REPORT_JSON.as_posix(),
            "markdown": REPORT_MD.as_posix(),
            "log": REPORT_LOG.as_posix(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build MemoryOS index")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    out = run_memory_index_build(args.root)
    print(
        json.dumps(
            {
                "canonical_root": get_canonical_root(args.root).as_posix(),
                "summary": out["index"]["summary"],
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

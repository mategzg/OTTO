#!/usr/bin/env python3
"""Bridge chat events into inbox raw pending drop packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from scripts.repo_root import get_canonical_root, is_within_root

PENDING_DROP = Path("vault/inbox_raw/_pending_drop")
LOG_PATH = Path("logs/chat_to_inbox_drop_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_event(raw: str) -> Dict[str, Any]:
    if not raw.strip():
        raise RuntimeError("event json is required")
    path = Path(raw)
    if path.is_file():
        parsed = json.loads(path.read_text(encoding="utf-8"))
    else:
        parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("event payload must be a JSON object")
    return parsed


def _source_id(session_id: str, source_label: str, text: str, attachments: Sequence[Dict[str, Any]]) -> str:
    names = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        names.append(str(item.get("name", "")))
        names.append(str(item.get("path", "")))
        names.append(str(item.get("url", "")))
    payload = "|".join([session_id, source_label, text[:2000], ",".join(sorted(names))])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _safe_target(base: Path, name: str) -> Path:
    candidate = base / name
    idx = 1
    while candidate.exists():
        candidate = base / f"{name}_{idx}"
        idx += 1
    return candidate


def _text_filename(text: str) -> str:
    lower = text.lower()
    if "```" in text or ("#" in text and "\n" in text) or ("- " in lower and "\n" in text):
        return "pasted.md"
    return "message.txt"


def _copy_attachment(root: Path, source_dir: Path, item: Dict[str, Any]) -> Dict[str, Any]:
    src_path_raw = str(item.get("path", "")).strip()
    if src_path_raw:
        src = Path(src_path_raw).expanduser()
        if not src.is_absolute():
            src = (root / src).resolve()
        else:
            src = src.resolve()
        if src.is_file() and is_within_root(src, root):
            name = str(item.get("name", "")).strip() or src.name
            target = _safe_target(source_dir, name)
            shutil.copy2(src, target)
            stat = target.stat()
            return {
                "kind": "copied_file",
                "name": target.name,
                "source_path": src.as_posix(),
                "target_path": target.as_posix(),
                "size": stat.st_size,
            }

    # Keep external or invalid refs as metadata only.
    return {
        "kind": "external_ref",
        "name": str(item.get("name", "")).strip(),
        "url": str(item.get("url", "")).strip(),
        "path": src_path_raw,
    }


def _build_manifest(source_dir: Path, origin_meta: Dict[str, Any]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for path in sorted(source_dir.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file():
            continue
        rel = path.resolve().relative_to(source_dir.resolve()).as_posix()
        content = path.read_bytes()
        entries.append(
            {
                "rel_path": rel,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "mtime": path.stat().st_mtime,
            }
        )
    return {
        "created_at": _utc_now(),
        "origin": origin_meta,
        "file_count": len(entries),
        "entries": entries,
        "version": 1,
    }


def run_chat_to_drop(
    root: str | Path,
    *,
    event: Dict[str, Any],
    session_id: str = "",
    source_label: str = "chat_runtime",
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    pending_root = canonical_root / PENDING_DROP
    pending_root.mkdir(parents=True, exist_ok=True)

    text = str(event.get("text", "")).strip()
    attachments = event.get("attachments", [])
    if not isinstance(attachments, list):
        attachments = []

    effective_session = session_id.strip() or str(event.get("session_id", "")).strip() or "unknown_session"
    source_id = _source_id(effective_session, source_label, text, attachments)
    package_name = f"{_stamp()}_{source_id}"
    package_dir = _safe_target(pending_root, package_name)
    source_dir = package_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    if text:
        filename = _text_filename(text)
        (source_dir / filename).write_text(text + "\n", encoding="utf-8")

    copied_attachments: List[Dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        copied_attachments.append(_copy_attachment(canonical_root, source_dir, item))

    meta = {
        "session_id": effective_session,
        "source_label": source_label,
        "channel": str(event.get("channel", "")),
        "channel_id": str(event.get("channel_id", "")),
        "channel_name": str(event.get("channel_name", "")),
        "domain_slug": str(event.get("domain_slug", "")),
        "recommended_domain": str(event.get("recommended_domain", "")),
        "peer_id": str(event.get("peer_id", "")),
        "thread_id": str(event.get("thread_id", "")),
        "message_id": str(event.get("message_id", "")),
        "timestamp": str(event.get("timestamp", "")) or _utc_now(),
        "attachments_count": len(attachments),
        "version": 1,
    }
    _save_json(source_dir / "EVENT_META.json", meta)

    if copied_attachments:
        _save_json(source_dir / "ATTACHMENTS.json", {"attachments": copied_attachments, "version": 1})

    readme_lines = [
        "# Chat Runtime Source Package",
        "",
        f"- source_id: `{source_id}`",
        f"- session_id: `{effective_session}`",
        f"- source_label: `{source_label}`",
        f"- channel: `{meta['channel']}`",
        f"- message_id: `{meta['message_id']}`",
        f"- created_at: `{_utc_now()}`",
        "",
        "Package generated automatically from runtime chat event.",
    ]
    (package_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    manifest = _build_manifest(source_dir, meta)
    _save_json(package_dir / "MANIFEST.json", manifest)

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "session_id": effective_session,
        "source_id": source_id,
        "package_rel": package_dir.resolve().relative_to(canonical_root.resolve()).as_posix(),
        "file_count": manifest["file_count"],
        "attachments_handled": len(copied_attachments),
        "status": "success",
        "version": 1,
    }
    _save_json(canonical_root / LOG_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Create inbox pending package from chat runtime event")
    parser.add_argument("--root", default=".")
    parser.add_argument("--event-json", required=True)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--source-label", default="chat_runtime")
    args = parser.parse_args()

    out = run_chat_to_drop(
        args.root,
        event=_load_event(args.event_json),
        session_id=args.session_id,
        source_label=args.source_label,
    )
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

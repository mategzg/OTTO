#!/usr/bin/env python3
"""Telegram owner notifier backed by append-only outbox queue."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root
from scripts.outbox_queue import enqueue_message, write_latest_snapshot

OUTBOX_PATH = Path("docs/_inbox/outbox_latest.md")
LOG_PATH = Path("logs/telegram_delivery_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def send_message(
    root: str | Path,
    text: str,
    *,
    token: str = "",
    chat_id: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    payload_text = text.strip()
    if not payload_text:
        raise RuntimeError("telegram message text is required")

    token_eff = token.strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_eff = chat_id.strip() or os.getenv("TELEGRAM_CHAT_ID", "").strip()

    report: Dict[str, Any] = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "channel": "telegram_owner",
        "dry_run": bool(dry_run),
        "message_preview": payload_text[:500],
        "sent": False,
        "queued": False,
        "queue_item_id": "",
        "queue_path": "",
        "fallback_outbox": "",
        "reason": "",
        "version": 1,
    }

    if dry_run:
        report["sent"] = False
        report["reason"] = "dry_run"
        report["fallback_outbox"] = write_latest_snapshot(canonical_root)
        _save_json(canonical_root / LOG_PATH, report)
        return report

    target = chat_eff or ""
    queued = enqueue_message(
        canonical_root,
        channel="telegram_owner",
        target=target,
        text=payload_text,
        purpose="notify",
        session_id="",
        source_ref="scripts/telegram_delivery.py",
        metadata={
            "token_configured": bool(token_eff),
            "chat_configured": bool(chat_eff),
            "target_source": "env_or_arg",
        },
    )
    report["queued"] = bool(queued.get("queued", False))
    report["queue_item_id"] = str(queued.get("item_id", ""))
    report["queue_path"] = str(queued.get("queue_path", ""))
    report["fallback_outbox"] = str(queued.get("snapshot_path", OUTBOX_PATH.as_posix()))
    report["sent"] = False
    report["reason"] = "queued_for_delivery"

    _save_json(canonical_root / LOG_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Send message via Telegram with outbox fallback")
    parser.add_argument("--root", default=".")
    parser.add_argument("--text", default="")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--token", default="")
    parser.add_argument("--chat-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    text = sys.stdin.read() if args.stdin else args.text
    out = send_message(
        args.root,
        text,
        token=args.token,
        chat_id=args.chat_id,
        dry_run=args.dry_run,
    )
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OpenClaw CLI wrapper for deterministic message delivery."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from typing import Any, Dict


def cli_available() -> bool:
    return bool(shutil.which("openclaw"))


def _normalize_channel(channel: str) -> str:
    value = str(channel).strip().lower()
    if value in {"telegram_owner", "telegram"}:
        return "telegram"
    if value.startswith("discord"):
        return "discord"
    if value.startswith("whatsapp"):
        return "whatsapp"
    return value or "telegram"


def send_message(channel: str, target: str, text: str, *, timeout_seconds: int = 10) -> Dict[str, Any]:
    clean_target = str(target).strip()
    clean_text = str(text).strip()
    if not clean_target:
        return {"ok": False, "reason": "missing_target", "cmd": []}
    if not clean_text:
        return {"ok": False, "reason": "missing_text", "cmd": []}
    if not cli_available():
        return {"ok": False, "reason": "openclaw_cli_not_found", "cmd": []}

    normalized_channel = _normalize_channel(channel)
    base = [
        "openclaw",
        "message",
        "send",
        "--channel",
        normalized_channel,
        "--target",
        clean_target,
    ]
    primary = base + ["--message", clean_text]

    def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
        )

    first = _run(primary)
    if first.returncode == 0:
        return {
            "ok": True,
            "reason": "sent",
            "channel": normalized_channel,
            "target": clean_target,
            "cmd": primary,
            "stdout": first.stdout[:2000],
            "stderr": first.stderr[:500],
            "returncode": first.returncode,
        }

    fallback = base + ["--text", clean_text]
    second = _run(fallback)
    if second.returncode == 0:
        return {
            "ok": True,
            "reason": "sent",
            "channel": normalized_channel,
            "target": clean_target,
            "cmd": fallback,
            "stdout": second.stdout[:2000],
            "stderr": second.stderr[:500],
            "returncode": second.returncode,
        }

    return {
        "ok": False,
        "reason": f"send_failed:{second.returncode}",
        "channel": normalized_channel,
        "target": clean_target,
        "cmd": fallback,
        "stdout": second.stdout[:2000],
        "stderr": second.stderr[:500] or first.stderr[:500],
        "returncode": second.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send message through OpenClaw CLI")
    parser.add_argument("--channel", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=10)
    args = parser.parse_args()
    out = send_message(args.channel, args.target, args.text, timeout_seconds=args.timeout_seconds)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if out.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())

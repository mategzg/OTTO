#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "state" / "skill_autocreate_queue.json"
OUT_MD = ROOT / "docs" / "_inbox" / "skill_autocreate_queue_latest.md"


def run() -> None:
    payload = json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.is_file() else {"items": []}
    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    lines = [
        "# Skill Autocreate Queue (latest)",
        "",
        f"Items: **{len(items)}**",
        "",
    ]
    if not items:
        lines.append("- No pending candidates.")
    else:
        for it in items:
            lines.append(
                f"- {it.get('selected_target','')} | prio={it.get('priority','')} | score={it.get('score','')} | repeat30d={it.get('repeat_count_30d','')} | status={it.get('status','pending')}"
            )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"api[_-]?key\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
    re.compile(r"token\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitize_detail(text: str) -> str:
    clean = text
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def append_activity(
    root: Path,
    event: str,
    detail: str,
    task_id: str = "",
    channel: str = "manual",
    level: str = "info",
) -> None:
    log_path = root.resolve() / "logs" / "activity.ndjson"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "channel": channel,
        "detail": sanitize_detail(detail),
        "event": event,
        "level": level,
        "task_id": task_id,
        "ts": utc_now_iso(),
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from scripts.dropbox_intake import run_apply
from scripts.repo_root import set_canonical_root

REPORT_JSON = Path("docs/_inbox/pending_ingest_trigger_latest.json")
PENDING_DROP = Path("vault/inbox_raw/_pending_drop")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _pending_count(root_path: Path) -> int:
    base = root_path / PENDING_DROP
    if not base.exists():
        return 0
    return len([p for p in base.iterdir() if p.is_dir() and p.name != "_ingested"])


def run_trigger(root: str | Path, *, max_entries: int = 25) -> Dict[str, Any]:
    root_path = Path(root).resolve()
    set_canonical_root(root_path, created_by="pending_ingest_trigger")
    started = time.monotonic()
    out = run_apply(root_path, max_entries=max_entries)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    pending_after = _pending_count(root_path)
    ingested = int(out.get("report", {}).get("apply", {}).get("ingested_count", 0))

    report = {
        "status": "success",
        "created_at": _utc_now(),
        "trigger_to_done_ms": elapsed_ms,
        "max_entries": int(max_entries),
        "ingested_count": ingested,
        "pending_after": pending_after,
        "backpressure": {
            "active": pending_after > 0,
            "remaining": pending_after,
        },
        "artifacts": {
            "dropbox_intake_report": out.get("paths", {}).get("json", "docs/_inbox/dropbox_intake_report_latest.json"),
            "state": out.get("paths", {}).get("state", "state/intake_state.json"),
        },
        "version": 1,
    }
    _save_json(root_path / REPORT_JSON, report)
    return {"report": report, "paths": {"json": REPORT_JSON.as_posix()}}


def main() -> int:
    p = argparse.ArgumentParser(description="Immediate trigger for pending ingest")
    p.add_argument("--root", default=".")
    p.add_argument("--max-entries", type=int, default=25)
    args = p.parse_args()
    out = run_trigger(args.root, max_entries=max(1, args.max_entries))
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

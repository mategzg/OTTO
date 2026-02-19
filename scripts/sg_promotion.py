#!/usr/bin/env python3
"""SG promotion queue: low auto-promote, medium/high approval required."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from scripts.repo_root import get_canonical_root
from scripts.sg_channel_policy import classify_sensitivity, load_sg_policy

QUEUE_PATH = Path("docs/_inbox/sg_promotion_queue.ndjson")
REPORT_JSON = Path("docs/_inbox/sg_promotion_report_latest.json")
REPORT_MD = Path("docs/_inbox/sg_promotion_report_latest.md")
LOG_PATH = Path("logs/sg_promotion_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_ndjson(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _write_ndjson(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _make_id(source_ref: str, text: str) -> str:
    raw = f"{source_ref}|{text[:400]}"
    return "sgp_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def enqueue_promotion(root: str | Path, item: Dict[str, Any]) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_sg_policy(canonical_root, create_if_missing=True)
    text = str(item.get("text", "")).strip()
    source_ref = str(item.get("source_ref", "")).strip() or "runtime:sg"
    sensitivity = str(item.get("sensitivity", "")).strip().lower() or classify_sensitivity(text, policy)
    promotion_id = str(item.get("promotion_id", "")).strip() or _make_id(source_ref, text)

    row = {
        "promotion_id": promotion_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "status": "pending",
        "target": str(item.get("target", "sg_global")).strip() or "sg_global",
        "sensitivity": sensitivity,
        "text": text[:1200],
        "source_ref": source_ref,
        "needs_approval": sensitivity in {"medium", "high"},
        "approved_by": "",
        "approved_at": "",
        "result": "",
        "version": 1,
    }
    queue = canonical_root / QUEUE_PATH
    existing = _read_ndjson(queue)
    if any(str(item.get("promotion_id", "")) == promotion_id for item in existing):
        return {
            "canonical_root": str(canonical_root.resolve()),
            "status": "duplicate",
            "promotion_id": promotion_id,
            "queue_path": QUEUE_PATH.as_posix(),
        }
    existing.append(row)
    _write_ndjson(queue, existing)
    return {
        "canonical_root": str(canonical_root.resolve()),
        "status": "enqueued",
        "promotion_id": promotion_id,
        "queue_path": QUEUE_PATH.as_posix(),
    }


def process_promotions(root: str | Path, *, approvals: Iterable[str] = ()) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    policy = load_sg_policy(canonical_root, create_if_missing=True)
    approval_set = {str(item).strip() for item in approvals if str(item).strip()}

    rows = _read_ndjson(canonical_root / QUEUE_PATH)
    promoted_auto = 0
    promoted_approved = 0
    pending_approval = 0
    changed = 0

    promotion_rules = policy.get("promotion_rules", {})
    now = _utc_now()

    for row in rows:
        if str(row.get("status", "")) != "pending":
            continue
        sensitivity = str(row.get("sensitivity", "low")).lower()
        mode = str(promotion_rules.get(sensitivity, "approval_required"))
        pid = str(row.get("promotion_id", ""))

        if mode == "auto" and sensitivity == "low":
            row["status"] = "promoted"
            row["result"] = "auto_promoted_low"
            row["updated_at"] = now
            changed += 1
            promoted_auto += 1
            continue

        if pid in approval_set:
            row["status"] = "promoted"
            row["result"] = "promoted_after_approval"
            row["approved_by"] = "telegram_owner"
            row["approved_at"] = now
            row["updated_at"] = now
            row["needs_approval"] = False
            changed += 1
            promoted_approved += 1
            continue

        row["needs_approval"] = True
        row["result"] = "waiting_owner_approval"
        row["updated_at"] = now
        pending_approval += 1

    _write_ndjson(canonical_root / QUEUE_PATH, rows)

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": now,
        "approval_delivery": "telegram_owner_only_via_approval_manager",
        "summary": {
            "total": len(rows),
            "pending": sum(1 for row in rows if str(row.get("status", "")) == "pending"),
            "promoted": sum(1 for row in rows if str(row.get("status", "")) == "promoted"),
            "promoted_auto": promoted_auto,
            "promoted_approved": promoted_approved,
            "pending_approval": pending_approval,
            "changed": changed,
        },
        "approvals": sorted(approval_set),
        "queue_path": QUEUE_PATH.as_posix(),
        "version": 1,
    }

    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / LOG_PATH, report)
    md_lines = [
        "# SG Promotion Report",
        "",
        f"- Total items: {report['summary']['total']}",
        f"- Pending: {report['summary']['pending']}",
        f"- Promoted: {report['summary']['promoted']}",
        f"- Auto promoted low: {report['summary']['promoted_auto']}",
        f"- Promoted by approval: {report['summary']['promoted_approved']}",
        f"- Pending approval: {report['summary']['pending_approval']}",
        f"- Queue path: `{QUEUE_PATH.as_posix()}`",
        f"- JSON report: `{REPORT_JSON.as_posix()}`",
    ]
    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return report


def approve_promotion(root: str | Path, promotion_id: str) -> Dict[str, Any]:
    clean = promotion_id.strip()
    if not clean:
        raise RuntimeError("promotion_id is required")
    return process_promotions(root, approvals=[clean])


def main() -> int:
    parser = argparse.ArgumentParser(description="SG promotion queue manager")
    parser.add_argument("--root", default=".")
    parser.add_argument("--enqueue", action="store_true")
    parser.add_argument("--item-json", default="")
    parser.add_argument("--process", action="store_true")
    parser.add_argument("--approve", default="")
    args = parser.parse_args()

    if args.enqueue:
        if not args.item_json:
            parser.error("--enqueue requires --item-json")
        item_path = Path(args.item_json)
        if item_path.is_file():
            item = json.loads(item_path.read_text(encoding="utf-8"))
        else:
            item = json.loads(args.item_json)
        if not isinstance(item, dict):
            parser.error("--item-json must be object")
        out = enqueue_promotion(args.root, item)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.approve:
        out = approve_promotion(args.root, args.approve)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    if args.process:
        out = process_promotions(args.root)
        print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    parser.error("Use --enqueue or --process or --approve <id>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

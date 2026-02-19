from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from hq_logging import append_activity

ROOT = Path(__file__).resolve().parent
STATUS_CHOICES = ("idle", "thinking", "working", "offline")
PRIORITY_CHOICES = ("low", "normal", "high", "urgent")
COLUMNS = ("todo", "in_progress", "done", "archive")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _status_default() -> dict[str, Any]:
    return {
        "status": "idle",
        "task": "",
        "updated_at": "",
    }


def _kanban_default() -> dict[str, list[dict[str, Any]]]:
    return {
        "archive": [],
        "done": [],
        "in_progress": [],
        "todo": [],
    }


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path, default_factory: Any) -> Any:
    default = default_factory()
    if not path.exists():
        _write_json(path, default)
        return deepcopy(default)

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"warning: using defaults for {path.name}: {exc}", file=sys.stderr)
        _write_json(path, default)
        return deepcopy(default)

    return parsed


def _append_log(root: Path, event: str, payload: dict[str, Any]) -> None:
    task_id = str(payload.get("id", payload.get("task_id", "")))
    append_activity(
        root=root,
        event=event,
        detail=json.dumps(payload, sort_keys=True, ensure_ascii=False),
        task_id=task_id,
        channel="manual",
        level="info",
    )


def _sort_kanban(kanban: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    sorted_kanban: dict[str, list[dict[str, Any]]] = {}
    for column in COLUMNS:
        items = list(kanban.get(column, []))
        items.sort(key=lambda item: (item.get("created_at", ""), item.get("id", "")))
        sorted_kanban[column] = items
    # Persist in alphabetical key order for deterministic JSON output.
    return {
        "archive": sorted_kanban["archive"],
        "done": sorted_kanban["done"],
        "in_progress": sorted_kanban["in_progress"],
        "todo": sorted_kanban["todo"],
    }


def set_status(root: Path, status: str, task: str) -> dict[str, Any]:
    root = root.resolve()
    if status not in STATUS_CHOICES:
        raise ValueError(f"invalid status: {status}")

    status_data = _load_json(root / "state" / "status.json", _status_default)
    status_data["status"] = status
    status_data["task"] = task
    status_data["updated_at"] = utc_now_iso()

    _write_json(root / "state" / "status.json", status_data)
    _append_log(root, "set_status", {"status": status, "task": task})
    return status_data


def add_task(root: Path, title: str, detail: str, priority: str) -> dict[str, Any]:
    root = root.resolve()
    if priority not in PRIORITY_CHOICES:
        raise ValueError(f"invalid priority: {priority}")

    kanban = _load_json(root / "state" / "kanban.json", _kanban_default)
    for column in COLUMNS:
        kanban.setdefault(column, [])

    now = utc_now_iso()
    task = {
        "created_at": now,
        "detail": detail,
        "id": f"task-{now.replace(':', '').replace('-', '').replace('T', '').replace('Z', '')}-{uuid4().hex[:8]}",
        "priority": priority,
        "title": title,
        "updated_at": now,
    }

    kanban["todo"].append(task)
    normalized = _sort_kanban(kanban)

    _write_json(root / "state" / "kanban.json", normalized)
    _append_log(root, "add_task", task)
    return task


def move_task(root: Path, task_id: str, to_column: str) -> dict[str, Any] | None:
    root = root.resolve()
    if to_column not in COLUMNS:
        raise ValueError(f"invalid column: {to_column}")

    kanban = _load_json(root / "state" / "kanban.json", _kanban_default)
    for column in COLUMNS:
        kanban.setdefault(column, [])

    found: dict[str, Any] | None = None
    source_column: str | None = None

    for column in COLUMNS:
        remaining: list[dict[str, Any]] = []
        for task in kanban[column]:
            if task.get("id") == task_id and found is None:
                found = dict(task)
                source_column = column
            else:
                remaining.append(task)
        kanban[column] = remaining

    if found is None:
        _append_log(root, "move_task_missing", {"task_id": task_id, "to": to_column})
        return None

    found["updated_at"] = utc_now_iso()
    kanban[to_column].append(found)
    normalized = _sort_kanban(kanban)

    _write_json(root / "state" / "kanban.json", normalized)
    _append_log(
        root,
        "move_task",
        {
            "from": source_column,
            "task_id": task_id,
            "to": to_column,
        },
    )
    return found


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OTTO HQ state manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("set-status", help="set OTTO status")
    status_parser.add_argument("status", choices=STATUS_CHOICES)
    status_parser.add_argument("--task", default="", help="current task")

    add_parser = subparsers.add_parser("add-task", help="add kanban task")
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--detail", required=True)
    add_parser.add_argument("--priority", choices=PRIORITY_CHOICES, default="normal")

    move_parser = subparsers.add_parser("move-task", help="move task between columns")
    move_parser.add_argument("task_id")
    move_parser.add_argument("--to", choices=COLUMNS, required=True)

    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="project root (default: script directory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "set-status":
        result = set_status(root=root, status=args.status, task=args.task)
    elif args.command == "add-task":
        result = add_task(
            root=root,
            title=args.title,
            detail=args.detail,
            priority=args.priority,
        )
    elif args.command == "move-task":
        moved = move_task(root=root, task_id=args.task_id, to_column=args.to)
        if moved is None:
            print(
                json.dumps(
                    {"ok": False, "reason": "task_not_found", "task_id": args.task_id},
                    sort_keys=True,
                    ensure_ascii=False,
                )
            )
            return 1
        result = moved
    else:
        parser.print_help()
        return 1

    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a recommended OpenClaw config patch report (no auto-apply)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.repo_root import get_canonical_root

REPORT_JSON = Path("docs/_inbox/openclaw_config_patch_latest.json")
REPORT_MD = Path("docs/_inbox/openclaw_config_patch_latest.md")
LOG_JSON = Path("logs/openclaw_config_patch_latest.json")


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


def run_patch_report(root: str | Path, *, config_path: str = "") -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    default_cfg = Path.home() / ".openclaw" / "openclaw.json"
    cfg_path = Path(config_path).expanduser().resolve() if config_path else default_cfg.resolve()
    current = _load_json(cfg_path)
    sessions = current.get("sessions", {}) if isinstance(current.get("sessions", {}), dict) else {}
    current_dm_scope = str(sessions.get("dmScope", ""))
    recommended = "per-account-channel-peer"
    needs_change = current_dm_scope != recommended
    patch = {"sessions": {"dmScope": recommended}}

    report = {
        "canonical_root": str(canonical_root.resolve()),
        "created_at": _utc_now(),
        "status": "report_only",
        "inspected_config_path": str(cfg_path),
        "config_exists": cfg_path.is_file(),
        "current_dm_scope": current_dm_scope,
        "recommended_patch": patch,
        "needs_change": needs_change,
        "note": "No se aplicaron cambios automaticamente.",
        "paths": {
            "json": REPORT_JSON.as_posix(),
            "markdown": REPORT_MD.as_posix(),
            "log": LOG_JSON.as_posix(),
        },
        "version": 1,
    }
    _save_json(canonical_root / REPORT_JSON, report)
    _save_json(canonical_root / LOG_JSON, report)
    md_lines = [
        "# OpenClaw Config Patch (Report Only)",
        "",
        f"- Config path: `{report['inspected_config_path']}`",
        f"- Exists: `{report['config_exists']}`",
        f"- Current sessions.dmScope: `{current_dm_scope or '(missing)'}`",
        f"- Recommended sessions.dmScope: `{recommended}`",
        f"- Needs change: `{needs_change}`",
        "",
        "## Recommended patch",
        "```json",
        json.dumps(patch, indent=2, sort_keys=True, ensure_ascii=False),
        "```",
    ]
    (canonical_root / REPORT_MD).parent.mkdir(parents=True, exist_ok=True)
    (canonical_root / REPORT_MD).write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return {"report": report, "paths": report["paths"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate recommended OpenClaw config patch report")
    parser.add_argument("--root", default=".")
    parser.add_argument("--config-path", default="")
    args = parser.parse_args()
    out = run_patch_report(args.root, config_path=args.config_path)
    print(json.dumps(out["report"], indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

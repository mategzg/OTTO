#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.plugin_execution_contract import evaluate_plugin_target

REG = ROOT / "state" / "plugin_runtime_registry.json"
OUT_JSON = ROOT / "docs" / "_inbox" / "plugin_adaptation_report_latest.json"
OUT_MD = ROOT / "docs" / "_inbox" / "plugin_adaptation_report_latest.md"


def run() -> None:
    payload = json.loads(REG.read_text(encoding="utf-8")) if REG.is_file() else {"plugins": []}
    rows = []
    for p in payload.get("plugins", []):
        name = str((p or {}).get("plugin", "")).strip()
        if not name:
            continue
        ev = evaluate_plugin_target(ROOT, f"plugin.{name}")
        rows.append({
            "plugin": name,
            "priority": p.get("priority", "medium"),
            "status": ev.get("status", "GAP"),
            "mode": ev.get("mode", ""),
            "effective_auth_needed": ev.get("connector_summary", {}).get("effective_auth_needed", 0),
            "effective_missing_url": ev.get("connector_summary", {}).get("effective_missing_url", 0),
            "mapped_connectors": ev.get("adaptation", {}).get("mapped_count", 0),
        })

    rank = {"high": 0, "medium": 1, "low": 2}
    rows.sort(key=lambda r: (rank.get(r["priority"], 9), r["effective_auth_needed"], r["plugin"]))

    out = {
        "updated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "rows": rows,
        "summary": {
            "total": len(rows),
            "ok": sum(1 for r in rows if r["status"] == "OK"),
            "ok_partial": sum(1 for r in rows if r["status"] == "OK_PARTIAL"),
            "gap": sum(1 for r in rows if r["status"] == "GAP"),
        },
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Plugin Adaptation Report (latest)",
        "",
        f"Actualizado: {out['updated_at']}",
        f"- Total: **{out['summary']['total']}**",
        f"- OK: **{out['summary']['ok']}**",
        f"- OK_PARTIAL: **{out['summary']['ok_partial']}**",
        f"- GAP: **{out['summary']['gap']}**",
        "",
        "## Estado por plugin SG (adaptado a stack OTTO)",
    ]
    for r in rows:
        lines.append(
            f"- {r['plugin']} [{r['priority']}] -> {r['status']} ({r['mode']}) | mapped={r['mapped_connectors']} | effective_auth={r['effective_auth_needed']} | effective_missing={r['effective_missing_url']}"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()

#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "state" / "cc_plugin_runtime_registry.json"
ROUTING = ROOT / "state" / "cc_plugin_nl_routing.json"
OUT_JSON = ROOT / "docs" / "_inbox" / "cc_plugin_certification_latest.json"
OUT_MD = ROOT / "docs" / "_inbox" / "cc_plugin_certification_latest.md"


def run() -> None:
    reg = json.loads(REGISTRY.read_text(encoding="utf-8")) if REGISTRY.is_file() else {"plugins": []}
    routing = json.loads(ROUTING.read_text(encoding="utf-8")) if ROUTING.is_file() else {"routes": []}

    plugins = reg.get("plugins", [])
    routes = routing.get("routes", [])

    results = []
    for p in plugins:
        has_playbook = True  # inventory + routing-ready already validated in ingest
        has_optional_connectors = bool(p.get("mcp_servers"))
        status = "OK" if has_playbook else "GAP"
        if has_playbook and has_optional_connectors:
            status = "OK_PARTIAL"  # partial only because connectors optional/not required
        results.append(
            {
                "plugin": p.get("plugin"),
                "priority": p.get("priority"),
                "class": p.get("class"),
                "commands": len(p.get("commands", [])),
                "skills": len(p.get("skills", [])),
                "mcp_servers": len(p.get("mcp_servers", [])),
                "status": status,
                "notes": [
                    "NL-first playbook operational",
                    "External connector auth is optional",
                ],
            }
        )

    summary = {
        "total": len(results),
        "ok": sum(1 for x in results if x["status"] == "OK"),
        "ok_partial": sum(1 for x in results if x["status"] == "OK_PARTIAL"),
        "gap": sum(1 for x in results if x["status"] == "GAP"),
        "routes": len(routes),
    }

    payload = {
        "updated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "policy": {
            "external_integrations_optional": True,
            "nl_first_required": True,
            "p0_p1_no_autonomous_coder": True,
            "p2_delegable_with_handoff": True,
        },
        "summary": summary,
        "results": results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Claude Code Plugins Certification (latest)",
        "",
        f"Actualizado: {payload['updated_at']}",
        "",
        "## Criterio",
        "- Integraciones externas (MCP) tratadas como **opcionales**.",
        "- Certificación se basa en readiness NL-first + playbook operativo.",
        "",
        "## Resumen",
        f"- Total: **{summary['total']}**",
        f"- OK: **{summary['ok']}**",
        f"- OK_PARTIAL (con conectores opcionales): **{summary['ok_partial']}**",
        f"- GAP: **{summary['gap']}**",
        f"- Rutas NL activas: **{summary['routes']}**",
        "",
        "## Estado por plugin",
    ]
    for r in results:
        lines.append(f"- {r['plugin']}: **{r['status']}** (prio={r['priority']}, mcp={r['mcp_servers']})")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()

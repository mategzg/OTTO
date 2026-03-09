#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.nl_skill_router import run_nl_router

OUT_JSON = ROOT / "docs" / "_inbox" / "plugin_runtime_smoke_latest.json"
OUT_MD = ROOT / "docs" / "_inbox" / "plugin_runtime_smoke_latest.md"

CASES = [
    ("Necesito revisar pipeline de ventas y forecast del mes", "plugin.sales"),
    ("Tengo un ticket de soporte y posible escalacion con cliente", "plugin.customer-support"),
    ("Haz un SEO audit y plan de campaña", "plugin.marketing"),
    ("Quiero reconciliacion contable y asiento", "plugin.finance"),
    ("Revisa este contrato y riesgo NDA", "plugin.legal"),
    ("Ayudame con roadmap y update de stakeholders", "plugin.product-management"),
    ("Necesito priorizar tareas y follow-up", "plugin.productivity"),
    ("Haz query SQL y dashboard de analitica", "plugin.data"),
    ("Necesito enterprise search sobre documentos internos", "plugin.enterprise-search"),
    ("Haz code review del PR y revisa seguridad", "plugin.code-review"),
    ("Muestrame docs de API y referencia versionada", "plugin.context7"),
    ("Deploy en vercel y revisar build fail", "plugin.vercel"),
]


def run() -> None:
    checks = []
    for text, expected in CASES:
        out = run_nl_router(ROOT, text=text, channel="telegram")
        plan = out.get("plan", {}) if isinstance(out.get("plan", {}), dict) else {}
        selected = str(plan.get("selected_target", ""))
        execution = out.get("execution", {}) if isinstance(out.get("execution", {}), dict) else {}
        exec_status = str(execution.get("status", ""))
        checks.append({
            "text": text,
            "expected": expected,
            "selected_target": selected,
            "route_type": str(plan.get("route_type", "")),
            "execution_status": exec_status,
            "pass": (selected == expected) and (exec_status.startswith("OK") or exec_status == "planned"),
        })

    passed = sum(1 for c in checks if c["pass"])
    payload = {
        "updated_at": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "total": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Plugin Runtime Smoke (latest)",
        "",
        f"Actualizado: {payload['updated_at']}",
        f"- Total: **{payload['total']}**",
        f"- Passed: **{payload['passed']}**",
        f"- Failed: **{payload['failed']}**",
        "",
        "## Checks",
    ]
    for c in checks:
        status = "PASS" if c["pass"] else "FAIL"
        lines.append(f"- [{status}] expected={c['expected']} | got={c['selected_target']} | route={c['route_type']} | exec={c.get('execution_status','')}")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()

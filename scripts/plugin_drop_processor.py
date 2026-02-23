#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import glob
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DROP = ROOT / "docs" / "_inbox" / "plugin_drop"
REGISTRY = ROOT / "state" / "plugin_runtime_registry.json"
REPORT = ROOT / "docs" / "_inbox" / "plugin_drop" / "activation_plan_latest.md"
ROUTING = ROOT / "state" / "plugin_nl_routing.json"


def _extract_commands_and_skills(readme: Path) -> tuple[list[str], list[str]]:
    commands: list[str] = []
    skills: list[str] = []
    txt = readme.read_text(encoding="utf-8", errors="ignore") if readme.is_file() else ""
    in_skills = False
    for line in txt.splitlines():
        m = re.match(r"\|\s*`(/[^`]+)`\s*\|", line)
        if m:
            commands.append(m.group(1))
        if line.strip().lower().startswith("## skills"):
            in_skills = True
            continue
        if in_skills and line.startswith("## "):
            in_skills = False
        if in_skills:
            m2 = re.match(r"\|\s*`([^`]+)`\s*\|", line)
            if m2 and not m2.group(1).startswith("/"):
                skills.append(m2.group(1))
    return sorted(set(commands)), sorted(set(skills))


def _fit(plugin: str) -> tuple[str, str]:
    if plugin in {"sales", "customer-support", "marketing"}:
        return "sg_ops", "high"
    if plugin in {"finance", "legal"}:
        return "sg_governance", "high"
    if plugin in {"product-management", "productivity"}:
        return "execution_system", "medium"
    return "knowledge_retrieval", "medium"


def run() -> None:
    plugins = []
    unique_servers: set[str] = set()

    for pdir in sorted([Path(p) for p in glob.glob(str(DROP / "*")) if Path(p).is_dir()]):
        name = pdir.name
        versions = sorted([d for d in pdir.iterdir() if d.is_dir()])
        if not versions:
            continue
        vdir = versions[-1]

        mcp_path = vdir / ".mcp.json"
        readme = vdir / "README.md"

        servers = []
        if mcp_path.is_file():
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = sorted((data.get("mcpServers") or {}).keys())
            unique_servers.update(servers)

        commands, skills = _extract_commands_and_skills(readme)
        domain_fit, priority = _fit(name)

        plugins.append(
            {
                "plugin": name,
                "version": vdir.name,
                "domain_fit": domain_fit,
                "priority": priority,
                "commands": commands,
                "skills": skills,
                "mcp_servers": servers,
                "status": "GAP_REQUIRES_CONNECTORS",
                "notes": [
                    "Standalone mode usable via docs/playbooks",
                    "Supercharged mode requires MCP auth per connector",
                ],
            }
        )

    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ROUTING.parent.mkdir(parents=True, exist_ok=True)

    registry = {
        "updated_at": now,
        "source_dir": str(DROP.relative_to(ROOT)),
        "policy": {
            "nl_first": True,
            "p0_p1_no_autonomous_coder": True,
            "p2_delegable_with_handoff": True,
        },
        "plugins": plugins,
        "unique_mcp_servers": sorted(unique_servers),
    }
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    routing = {
        "updated_at": now,
        "intent_routes": [
            {"intent": "ventas|pipeline|prospecto|outreach", "plugin": "sales"},
            {"intent": "ticket|soporte|cliente molesto|escalacion", "plugin": "customer-support"},
            {"intent": "campaña|contenido|seo|marketing", "plugin": "marketing"},
            {"intent": "cierre contable|asiento|reconciliacion|pnl", "plugin": "finance"},
            {"intent": "contrato|clausula|riesgo legal|nda", "plugin": "legal"},
            {"intent": "prd|roadmap|stakeholder|feature", "plugin": "product-management"},
            {"intent": "tareas|prioridades|briefing|follow-up", "plugin": "productivity"},
            {"intent": "query|sql|dashboard|analitica", "plugin": "data"},
            {"intent": "buscar en empresa|enterprise search|documento interno", "plugin": "enterprise-search"},
        ],
    }
    ROUTING.write_text(json.dumps(routing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Cowork Plugins Activation Plan (adaptado OTTO/SG)",
        "",
        f"Actualizado: {now}",
        "",
        "## Estado global",
        f"- Plugins importados: **{len(plugins)}**",
        f"- MCP servers únicos detectados: **{len(unique_servers)}**",
        "- Modo actual: **playbook listo + conectores pendientes**",
        "- Política: NL-first, P0/P1 sin coder autónomo, P2 delegable con handoff.",
        "",
        "## Priorización",
    ]
    for p in plugins:
        lines.append(f"- **{p['plugin']}** ({p['priority']}) -> {p['domain_fit']} | estado: {p['status']}")
    lines += [
        "",
        "## Próximo paso",
        "- Activar conectores por prioridad: sales -> customer-support -> finance/legal.",
        "- Correr smoke test NL por plugin y registrar OK/GAP.",
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run()

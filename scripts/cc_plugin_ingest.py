#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs" / "_inbox" / "plugin_drop" / "claude code plugins"
OUT_JSON = ROOT / "docs" / "_inbox" / "claude_code_plugins_inventory_latest.json"
OUT_MD = ROOT / "docs" / "_inbox" / "claude_code_plugins_inventory_latest.md"
REGISTRY = ROOT / "state" / "cc_plugin_runtime_registry.json"
ROUTING = ROOT / "state" / "cc_plugin_nl_routing.json"


def _choose_priority(name: str) -> str:
    high = {
        "coderabbit", "code-review", "pr-review-toolkit", "feature-dev", "semgrep", "security-guidance",
        "context7", "github", "playwright", "vercel", "superpowers", "serena", "greptile",
    }
    medium = {
        "gitlab", "sentry", "posthog", "firebase", "supabase", "pinecone", "stripe", "figma", "firecrawl",
        "plugin-dev", "hookify", "skill-creator", "claude-code-setup", "commit-commands",
    }
    if name in high:
        return "high"
    if name in medium:
        return "medium"
    if name.endswith("-lsp"):
        return "medium"
    return "low"


def _class(name: str) -> str:
    if name.endswith("-lsp"):
        return "language-intelligence"
    if any(k in name for k in ["review", "semgrep", "security", "coderabbit"]):
        return "quality-security"
    if name in {"context7", "serena", "greptile"}:
        return "code-understanding"
    if name in {"github", "gitlab", "vercel", "playwright", "firebase", "stripe", "pinecone", "posthog", "sentry", "figma", "firecrawl", "linear", "asana", "atlassian", "slack", "notion"}:
        return "integration-mcp"
    if name in {"feature-dev", "superpowers", "code-simplifier", "plugin-dev", "skill-creator", "claude-code-setup", "commit-commands", "hookify"}:
        return "workflow-automation"
    return "general"


def _scan_plugin(pdir: Path) -> dict:
    versions = sorted([d for d in pdir.iterdir() if d.is_dir()])
    if not versions:
        return {}
    vdir = versions[-1]
    # choose canonical numeric version if exists
    numeric = sorted([d for d in versions if re.match(r"^\d+\.\d+\.\d+$", d.name)])
    if numeric:
        vdir = numeric[-1]

    mcp_path = vdir / ".mcp.json"
    readme = vdir / "README.md"

    servers: list[str] = []
    commands: list[str] = []
    skills: list[str] = []

    if mcp_path.is_file():
        try:
            data = json.loads(mcp_path.read_text(encoding="utf-8"))
            servers = sorted((data.get("mcpServers") or {}).keys())
        except Exception:
            pass

    if readme.is_file():
        txt = readme.read_text(encoding="utf-8", errors="ignore")
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

    name = pdir.name
    return {
        "plugin": name,
        "selected_version": vdir.name,
        "versions_detected": [d.name for d in versions],
        "priority": _choose_priority(name),
        "class": _class(name),
        "commands": sorted(set(commands)),
        "skills": sorted(set(skills)),
        "mcp_servers": servers,
        "status": "READY_PLAYBOOK",
        "supercharged": "OPTIONAL_CONNECTORS",
    }


def run() -> None:
    plugins = []
    unique_servers = set()

    for p in sorted([Path(x) for x in glob.glob(str(BASE / "*")) if Path(x).is_dir()]):
        row = _scan_plugin(p)
        if not row:
            continue
        plugins.append(row)
        unique_servers.update(row["mcp_servers"])

    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    inventory = {
        "updated_at": now,
        "source": str(BASE.relative_to(ROOT)),
        "plugins_total": len(plugins),
        "unique_mcp_servers": sorted(unique_servers),
        "plugins": plugins,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    ROUTING.parent.mkdir(parents=True, exist_ok=True)

    OUT_JSON.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    registry = {
        "updated_at": now,
        "policy": {
            "nl_first": True,
            "p0_p1_no_autonomous_coder": True,
            "p2_delegable_with_handoff": True,
        },
        "plugins": plugins,
    }
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    curated_routes = [
        {"intent": "review|pr|pull request|bugs|seguridad", "plugin": "code-review"},
        {"intent": "docs version|api docs|reference", "plugin": "context7"},
        {"intent": "deploy|vercel|build fail", "plugin": "vercel"},
        {"intent": "browser test|e2e|playwright", "plugin": "playwright"},
        {"intent": "github|issue|workflow|actions", "plugin": "github"},
        {"intent": "refactor|simplify code", "plugin": "code-simplifier"},
        {"intent": "security scan|vulnerability", "plugin": "semgrep"},
        {"intent": "language server|types|lsp", "plugin": "typescript-lsp"},
    ]

    existing = {r["plugin"] for r in curated_routes}
    auto_routes = []
    for p in plugins:
        name = p["plugin"]
        if name in existing:
            continue
        tokens = [t for t in re.split(r"[-_]+", name) if t]
        if not tokens:
            continue
        pattern = r"\\b" + r"\\s*[-_ ]?\\s*".join(re.escape(t) for t in tokens) + r"\\b"
        auto_routes.append({"intent": pattern, "plugin": name})

    routing = {
        "updated_at": now,
        "routes": curated_routes + auto_routes,
        "meta": {
            "curated": len(curated_routes),
            "auto_generated": len(auto_routes),
            "total": len(curated_routes) + len(auto_routes),
            "note": "Auto routes match explicit plugin-name mentions in natural language.",
        },
    }
    ROUTING.write_text(json.dumps(routing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    high = [p["plugin"] for p in plugins if p["priority"] == "high"]
    med = [p["plugin"] for p in plugins if p["priority"] == "medium"]

    lines = [
        "# Claude Code Plugins Inventory (latest)",
        "",
        f"Actualizado: {now}",
        f"- Plugins detectados: **{len(plugins)}**",
        f"- MCP servers únicos: **{len(unique_servers)}**",
        "- Estado base: **READY_PLAYBOOK** (NL-first)",
        "",
        "## Prioridad alta",
    ]
    for x in high:
        lines.append(f"- {x}")
    lines += ["", "## Prioridad media"]
    for x in med:
        lines.append(f"- {x}")
    lines += ["", "## Nota", "- Conectores externos son opcionales; sin auth igual hay valor en playbooks/skills."]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()

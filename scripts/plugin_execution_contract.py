#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

PLUGIN_REG = Path("state/plugin_runtime_registry.json")
CC_PLUGIN_REG = Path("state/cc_plugin_runtime_registry.json")
CONNECTOR_PROBE = Path("docs/_inbox/plugin_drop/connector_probe_latest.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _by_plugin(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        name = str((row or {}).get("plugin", "")).strip()
        if name:
            out[name] = row
    return out


def evaluate_plugin_target(root: str | Path, selected_target: str) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    if not str(selected_target).startswith("plugin."):
        return {"applicable": False}

    plugin_name = str(selected_target).split(".", 1)[1].strip()
    reg_a = _load_json(canonical_root / PLUGIN_REG)
    reg_b = _load_json(canonical_root / CC_PLUGIN_REG)
    probe = _load_json(canonical_root / CONNECTOR_PROBE)

    idx = _by_plugin((reg_a.get("plugins") or []) + (reg_b.get("plugins") or []))
    p = idx.get(plugin_name, {})

    probe_idx = _by_plugin(probe.get("plugins") or [])
    probe_row = probe_idx.get(plugin_name, {})
    servers = probe_row.get("servers", {}) if isinstance(probe_row.get("servers"), dict) else {}

    total = len(servers)
    auth_needed = 0
    reachable = 0
    missing_url = 0
    for s in servers.values():
        if bool((s or {}).get("reachable")):
            reachable += 1
        status = (s or {}).get("status")
        if status in (401, 403):
            auth_needed += 1
        if (s or {}).get("note") == "missing_url":
            missing_url += 1

    standalone_ready = True
    supercharged_ready = total == 0 or (reachable == total and auth_needed == 0 and missing_url == 0)

    if standalone_ready and supercharged_ready:
        status = "OK"
    elif standalone_ready:
        status = "OK_PARTIAL"
    else:
        status = "GAP"

    return {
        "applicable": True,
        "plugin": plugin_name,
        "status": status,
        "mode": "standalone" if status != "OK" else "supercharged",
        "next_action": (
            "run_playbook" if status == "OK" else "run_playbook_and_activate_connectors"
        ),
        "connector_summary": {
            "total": total,
            "reachable": reachable,
            "auth_needed": auth_needed,
            "missing_url": missing_url,
        },
        "registry": {
            "priority": p.get("priority", ""),
            "class": p.get("class", ""),
            "domain_fit": p.get("domain_fit", ""),
            "commands": p.get("commands", []),
        },
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate plugin execution contract")
    parser.add_argument("--root", default=".")
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    out = evaluate_plugin_target(args.root, args.target)
    print(json.dumps(out, ensure_ascii=False, indent=2))

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from scripts.repo_root import get_canonical_root

PLUGIN_REG = Path("state/plugin_runtime_registry.json")
CC_PLUGIN_REG = Path("state/cc_plugin_runtime_registry.json")
CONNECTOR_PROBE = Path("docs/_inbox/plugin_drop/connector_probe_latest.json")
ADAPTERS_PATH = Path("state/plugin_connector_adapters.json")


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


def _adaptation_for(servers: Dict[str, Any], adapters: Dict[str, Any]) -> Dict[str, Any]:
    aliases = adapters.get("connector_aliases", {}) if isinstance(adapters.get("connector_aliases"), dict) else {}
    native = set(adapters.get("native_stack", [])) if isinstance(adapters.get("native_stack"), list) else set()

    mapped: Dict[str, str] = {}
    adapted_auth = 0
    adapted_missing = 0

    for cname, s in servers.items():
        alias = str(aliases.get(cname, "")).strip()
        if not alias and cname in native:
            alias = cname
        if not alias:
            continue
        mapped[cname] = alias
        if alias in native:
            status = (s or {}).get("status")
            note = (s or {}).get("note")
            if status in (401, 403):
                adapted_auth += 1
            if note == "missing_url":
                adapted_missing += 1

    return {
        "mapped": mapped,
        "mapped_count": len(mapped),
        "adapted_auth_connectors": adapted_auth,
        "adapted_missing_url_connectors": adapted_missing,
    }


def evaluate_plugin_target(root: str | Path, selected_target: str) -> Dict[str, Any]:
    canonical_root = get_canonical_root(root)
    if not str(selected_target).startswith("plugin."):
        return {"applicable": False}

    plugin_name = str(selected_target).split(".", 1)[1].strip()
    reg_a = _load_json(canonical_root / PLUGIN_REG)
    reg_b = _load_json(canonical_root / CC_PLUGIN_REG)
    probe = _load_json(canonical_root / CONNECTOR_PROBE)
    adapters = _load_json(canonical_root / ADAPTERS_PATH)

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

    adaptation = _adaptation_for(servers, adapters)
    effective_auth_needed = max(0, auth_needed - int(adaptation.get("adapted_auth_connectors", 0)))
    effective_missing_url = max(0, missing_url - int(adaptation.get("adapted_missing_url_connectors", 0)))

    standalone_ready = True
    adapted_missing = int(adaptation.get("adapted_missing_url_connectors", 0))
    effective_reachable = min(total, reachable + adapted_missing)
    supercharged_native = total == 0 or (effective_reachable == total and effective_auth_needed == 0 and effective_missing_url == 0)

    if standalone_ready and supercharged_native:
        status = "OK"
        mode = "supercharged_adapted"
        next_action = "run_playbook"
    elif standalone_ready:
        status = "OK_PARTIAL"
        mode = "standalone"
        next_action = "run_playbook_and_activate_connectors"
    else:
        status = "GAP"
        mode = "blocked"
        next_action = "fix_runtime_blockers"

    return {
        "applicable": True,
        "plugin": plugin_name,
        "status": status,
        "mode": mode,
        "next_action": next_action,
        "connector_summary": {
            "total": total,
            "reachable": reachable,
            "auth_needed": auth_needed,
            "missing_url": missing_url,
            "effective_reachable": effective_reachable,
            "effective_auth_needed": effective_auth_needed,
            "effective_missing_url": effective_missing_url,
        },
        "adaptation": adaptation,
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

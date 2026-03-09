#!/usr/bin/env python3
from __future__ import annotations

import glob
import json
from pathlib import Path
from urllib import request, error
import ssl
import datetime as dt

ROOT = Path(__file__).resolve().parents[1]
DROP = ROOT / "docs" / "_inbox" / "plugin_drop"
OUT_JSON = ROOT / "docs" / "_inbox" / "plugin_drop" / "connector_probe_latest.json"
OUT_MD = ROOT / "docs" / "_inbox" / "plugin_drop" / "connector_probe_latest.md"


def probe_url(url: str, timeout: float = 6.0) -> dict:
    req = request.Request(url, method="GET", headers={"User-Agent": "otto-connector-probe/1.0"})
    ctx = ssl.create_default_context()
    try:
        with request.urlopen(req, timeout=timeout, context=ctx) as resp:
            code = getattr(resp, "status", 200)
            return {"reachable": True, "status": int(code), "note": "ok"}
    except error.HTTPError as e:
        return {"reachable": True, "status": int(e.code), "note": "http_error"}
    except Exception as e:
        return {"reachable": False, "status": None, "note": f"{type(e).__name__}"}


def run() -> None:
    plugin_rows = []
    unique = {}

    for pdir in sorted([Path(p) for p in glob.glob(str(DROP / "*")) if Path(p).is_dir()]):
        versions = sorted([d for d in pdir.iterdir() if d.is_dir()])
        if not versions:
            continue
        vdir = versions[-1]
        mcp = vdir / ".mcp.json"
        if not mcp.is_file():
            continue
        data = json.loads(mcp.read_text(encoding="utf-8"))
        servers = data.get("mcpServers") or {}

        server_results = {}
        for sname, sval in servers.items():
            url = (sval or {}).get("url", "")
            if not url:
                server_results[sname] = {"url": url, "reachable": False, "status": None, "note": "missing_url"}
                continue
            if url in unique:
                result = unique[url]
            else:
                result = probe_url(url)
                unique[url] = result
            server_results[sname] = {"url": url, **result}

        plugin_rows.append({
            "plugin": pdir.name,
            "version": vdir.name,
            "servers": server_results,
        })

    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    payload = {
        "updated_at": now,
        "plugins": plugin_rows,
        "summary": {
            "plugins": len(plugin_rows),
            "unique_urls": len(unique),
            "reachable_urls": sum(1 for r in unique.values() if r.get("reachable")),
            "auth_or_access_required": sum(1 for r in unique.values() if r.get("status") in {401, 403}),
        },
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Connector Probe (latest)",
        "",
        f"Actualizado: {now}",
        f"- Plugins: **{payload['summary']['plugins']}**",
        f"- URLs únicas: **{payload['summary']['unique_urls']}**",
        f"- Reachables: **{payload['summary']['reachable_urls']}**",
        f"- Requieren auth/acceso (401/403): **{payload['summary']['auth_or_access_required']}**",
        "",
        "## Resultado por plugin",
    ]
    for p in plugin_rows:
        lines.append(f"### {p['plugin']} ({p['version']})")
        for sname, sres in sorted(p["servers"].items()):
            status = sres.get("status")
            reach = "reachable" if sres.get("reachable") else "unreachable"
            lines.append(f"- {sname}: {reach} | status={status} | {sres.get('url')}")
        lines.append("")

    lines += [
        "## Nota",
        "- Este probe valida reachability HTTP básica, no login completo OAuth.",
        "- Para modo supercharged faltan credenciales/sesiones por conector.",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run()

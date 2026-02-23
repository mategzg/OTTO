#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs" / "_inbox" / "agentmail_integration_latest.json"
OUT_MD = ROOT / "docs" / "_inbox" / "agentmail_integration_latest.md"


def run() -> int:
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    api_key = os.getenv("AGENTMAIL_API_KEY", "").strip()

    result = {
        "updated_at": now,
        "status": "GAP",
        "checks": {
            "env_key_present": bool(api_key),
            "sdk_installed": False,
            "inbox_create": False,
        },
        "notes": [],
    }

    try:
        from agentmail import AgentMail  # type: ignore
        result["checks"]["sdk_installed"] = True
    except Exception as e:  # pragma: no cover
        result["notes"].append(f"agentmail_sdk_missing: {type(e).__name__}")
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(
            "# AgentMail Integration\n\n"
            f"Actualizado: {now}\n\n"
            "- Estado: **GAP**\n"
            "- Motivo: SDK agentmail no instalado\n",
            encoding="utf-8",
        )
        return 1

    if not api_key:
        result["notes"].append("missing_env: AGENTMAIL_API_KEY")
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(
            "# AgentMail Integration\n\n"
            f"Actualizado: {now}\n\n"
            "- Estado: **GAP**\n"
            "- Motivo: falta variable `AGENTMAIL_API_KEY`\n",
            encoding="utf-8",
        )
        return 2

    try:
        client = AgentMail(api_key=api_key)
        inbox = client.inboxes.create()
        inbox_id = getattr(inbox, "inbox_id", None) or getattr(inbox, "inboxId", None) or str(inbox)

        result["checks"]["inbox_create"] = True
        result["status"] = "OK"
        result["created_inbox"] = str(inbox_id)
        result["notes"].append("inbox_created_successfully")

        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(
            "# AgentMail Integration\n\n"
            f"Actualizado: {now}\n\n"
            "- Estado: **OK**\n"
            f"- Inbox de prueba creado: `{inbox_id}`\n"
            "- Nota: API key no se persiste en archivos.\n",
            encoding="utf-8",
        )
        return 0
    except Exception as e:
        result["notes"].append(f"api_error: {type(e).__name__}: {e}")
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(
            "# AgentMail Integration\n\n"
            f"Actualizado: {now}\n\n"
            "- Estado: **GAP**\n"
            f"- Error API: `{type(e).__name__}`\n",
            encoding="utf-8",
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(run())

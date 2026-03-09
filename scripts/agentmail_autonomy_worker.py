#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from agentmail import AgentMail

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "agentmail_autonomy_state.json"
REPORT_JSON = ROOT / "docs" / "_inbox" / "agentmail_autonomy_latest.json"
REPORT_MD = ROOT / "docs" / "_inbox" / "agentmail_autonomy_latest.md"


RULES = [
    (re.compile(r"\b(cotiz|quote|presupuesto|price)\b", re.I), "sales_quote"),
    (re.compile(r"\b(factura|invoice|pago|payment|cobro)\b", re.I), "finance_billing"),
    (re.compile(r"\b(soporte|support|error|bug|problema|incidencia)\b", re.I), "support_issue"),
    (re.compile(r"\b(legal|contrato|nda|clausula|terms)\b", re.I), "legal_review"),
]


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.is_file():
        return {"processed": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"processed": []}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _classify(subject: str, preview: str) -> str:
    text = f"{subject}\n{preview}".strip()
    for rx, label in RULES:
        if rx.search(text):
            return label
    return "general"


def _build_reply(label: str, inbox: str) -> str:
    if label == "sales_quote":
        return "¡Gracias por escribir! Claro, te ayudo con la cotización. ¿Me compartes cantidades, medidas y ciudad de entrega para enviarte propuesta hoy?"
    if label == "finance_billing":
        return "Recibido, te ayudo con facturación/pagos. Envíame número de factura o RUC para ubicarlo y resolverlo rápido."
    if label == "support_issue":
        return "Gracias por reportarlo. Ya lo tengo en revisión. ¿Puedes compartir captura/pasos para reproducir y hora aproximada del error?"
    if label == "legal_review":
        return "Recibido. Puedo revisar el punto legal en detalle; por favor comparte el documento o cláusula exacta para responderte con precisión."
    return "¡Gracias por escribir! Recibido. Te respondo en breve con la información completa."


def run_once(inbox_id: str, auto_reply: bool = False) -> Dict[str, Any]:
    api_key = os.getenv("AGENTMAIL_API_KEY", "").strip()
    now = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    result: Dict[str, Any] = {
        "updated_at": now,
        "inbox_id": inbox_id,
        "auto_reply": auto_reply,
        "status": "OK",
        "processed_now": 0,
        "skipped": 0,
        "actions": [],
    }

    if not api_key:
        result["status"] = "GAP"
        result["error"] = "missing AGENTMAIL_API_KEY"
        return result

    client = AgentMail(api_key=api_key)
    state = _load_state()
    processed: set[str] = set(state.get("processed", []))

    listing = client.inboxes.messages.list(inbox_id=inbox_id, limit=25)
    messages = getattr(listing, "messages", []) or []

    # old to new for deterministic handling
    messages = sorted(messages, key=lambda m: getattr(m, "timestamp", dt.datetime.now(dt.timezone.utc)))

    for m in messages:
        message_id = str(getattr(m, "message_id", ""))
        if not message_id or message_id in processed:
            result["skipped"] += 1
            continue

        labels = [x.lower() for x in (getattr(m, "labels", None) or [])]
        from_addr = str(getattr(m, "from_", ""))
        subject = str(getattr(m, "subject", ""))
        preview = str(getattr(m, "preview", ""))

        # skip sent/self messages to avoid loops
        if "sent" in labels or inbox_id.lower() in from_addr.lower():
            processed.add(message_id)
            result["skipped"] += 1
            continue

        cls = _classify(subject, preview)
        draft_text = _build_reply(cls, inbox_id)

        action = {
            "message_id": message_id,
            "from": from_addr,
            "subject": subject,
            "class": cls,
            "reply_mode": "auto" if auto_reply else "draft_only",
            "reply_text": draft_text,
        }

        if auto_reply:
            try:
                client.inboxes.messages.reply(
                    inbox_id=inbox_id,
                    message_id=message_id,
                    text=draft_text,
                )
                action["reply_status"] = "sent"
            except Exception as e:
                action["reply_status"] = f"error:{type(e).__name__}"

        result["actions"].append(action)
        processed.add(message_id)
        result["processed_now"] += 1

    state["processed"] = sorted(processed)[-1000:]
    state["updated_at"] = now
    _save_state(state)
    return result


def _write_report(payload: Dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# AgentMail Autonomy Worker",
        "",
        f"Actualizado: {payload.get('updated_at')}",
        f"- Inbox: `{payload.get('inbox_id')}`",
        f"- Estado: **{payload.get('status')}**",
        f"- Auto-reply: **{payload.get('auto_reply')}**",
        f"- Procesados ahora: **{payload.get('processed_now', 0)}**",
        f"- Skipped: **{payload.get('skipped', 0)}**",
        "",
    ]
    if payload.get("error"):
        lines.append(f"- Error: `{payload['error']}`")
    if payload.get("actions"):
        lines += ["## Actions"]
        for a in payload["actions"]:
            lines.append(f"- {a['class']} | {a['subject']} | mode={a['reply_mode']}")

    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentMail autonomy worker")
    parser.add_argument("--inbox", default="sgacabados@agentmail.to")
    parser.add_argument("--auto-reply", action="store_true", default=True)
    parser.add_argument("--draft-only", action="store_true", help="disable auto-reply for this run")
    args = parser.parse_args()

    auto_reply = bool(args.auto_reply) and not bool(args.draft_only)
    payload = run_once(inbox_id=args.inbox, auto_reply=auto_reply)
    _write_report(payload)
    return 0 if payload.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())

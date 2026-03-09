from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .odoo_client import OdooClient


@dataclass
class OdooWorkflow:
    client: OdooClient
    root: Path
    dry_run: bool = True

    def __post_init__(self) -> None:
        self.state_path = self.root / "state" / "odoo" / "idempotency_store.json"
        self.audit_path = self.root / "logs" / "odoo_workflow_audit.jsonl"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.is_file():
            return {"keys": {}}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"keys": {}}
        if not isinstance(payload, dict):
            return {"keys": {}}
        payload.setdefault("keys", {})
        return payload

    def _save_state(self, payload: Dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    def _audit(self, event: str, **data: Any) -> None:
        row = {"ts": self._now(), "event": event, **data}
        self.audit_path.write_text("", encoding="utf-8") if not self.audit_path.exists() else None
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def _idempotent(self, operation: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        key = hashlib.sha256((operation + "|" + json.dumps(payload, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()
        state = self._load_state()
        hit = state["keys"].get(key)
        if hit:
            self._audit("idempotency_hit", operation=operation, key=key)
            return hit
        return None

    def _remember(self, operation: str, payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        key = hashlib.sha256((operation + "|" + json.dumps(payload, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()
        state = self._load_state()
        state["keys"][key] = {"operation": operation, "payload": payload, "result": result, "ts": self._now()}
        self._save_state(state)
        return result

    def odoo_read(self, model: str, domain: List[Any], fields: List[str], limit: int = 10) -> Dict[str, Any]:
        result = self.client.execute_kw(model, "search_read", [domain], {"fields": fields, "limit": int(limit)})
        out = {"ok": True, "model": model, "count": len(result), "records": result}
        self._audit("odoo_read", model=model, limit=limit, count=len(result))
        return out

    def odoo_write(self, model: str, values: Dict[str, Any], *, idempotency_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        p = idempotency_payload or {"model": model, "values": values}
        cached = self._idempotent("odoo_write", p)
        if cached:
            return {"ok": True, "idempotent": True, **cached["result"]}
        if self.dry_run:
            out = {"dry_run": True, "model": model, "values": values}
        else:
            rec_id = int(self.client.execute_kw(model, "create", [values]))
            out = {"dry_run": False, "model": model, "id": rec_id}
        self._audit("odoo_write", dry_run=self.dry_run, model=model)
        self._remember("odoo_write", p, out)
        return {"ok": True, "idempotent": False, **out}

    def quote_draft(self, *, partner_id: int, order_lines: List[Dict[str, Any]], client_ref: str) -> Dict[str, Any]:
        vals = {"partner_id": int(partner_id), "order_line": order_lines, "state": "draft", "client_order_ref": client_ref}
        return self.odoo_write("sale.order", vals, idempotency_payload={"type": "quote_draft", "client_ref": client_ref, "partner_id": partner_id, "order_lines": order_lines})

    def order_draft(self, *, quote_id: int, confirm: bool = False) -> Dict[str, Any]:
        payload = {"type": "order_draft", "quote_id": int(quote_id), "confirm": bool(confirm)}
        cached = self._idempotent("order_draft", payload)
        if cached:
            return {"ok": True, "idempotent": True, **cached["result"]}

        if confirm:
            out = {
                "handoff_required": True,
                "status": "blocked_until_human_confirmation",
                "quote_id": int(quote_id),
            }
            self._audit("order_draft_blocked", quote_id=quote_id)
        else:
            out = {"status": "draft_only", "quote_id": int(quote_id), "action": "no_confirm"}
            self._audit("order_draft_draft", quote_id=quote_id)
        self._remember("order_draft", payload, out)
        return {"ok": True, "idempotent": False, **out}

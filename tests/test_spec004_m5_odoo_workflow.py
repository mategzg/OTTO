from pathlib import Path

from scripts.odoo.odoo_workflow import OdooWorkflow
from scripts.odoo.odoo_client import OdooConfig, OdooClient


class StubModels:
    def __init__(self):
        self.calls = []

    def execute_kw(self, db, uid, password, model, method, args, kwargs):
        self.calls.append((model, method, args, kwargs))
        if method == "search_read":
            return [{"id": 11, "name": "Draft Quote"}]
        return 42


class StubCommon:
    def authenticate(self, *_args, **_kwargs):
        return 1


def _workflow(tmp_path: Path, dry_run: bool = True) -> OdooWorkflow:
    cfg = OdooConfig(url="https://x", db="d", username="u", password="p")
    client = OdooClient(cfg)
    client._common = StubCommon()
    client._models = StubModels()
    return OdooWorkflow(client=client, root=tmp_path, dry_run=dry_run)


def test_odoo_read_and_write_idempotency(tmp_path: Path):
    wf = _workflow(tmp_path)
    out = wf.odoo_read("sale.order", [["state", "=", "draft"]], ["name"], limit=3)
    assert out["ok"] is True
    assert out["count"] == 1

    first = wf.odoo_write("res.partner", {"name": "Cliente X"})
    second = wf.odoo_write("res.partner", {"name": "Cliente X"})
    assert first["idempotent"] is False
    assert second["idempotent"] is True


def test_quote_and_order_draft_handoff_gate(tmp_path: Path):
    wf = _workflow(tmp_path)
    q = wf.quote_draft(partner_id=7, order_lines=[{"name": "Losa", "price_unit": 10}], client_ref="Q-001")
    assert q["ok"] is True
    assert q["dry_run"] is True

    gated = wf.order_draft(quote_id=22, confirm=True)
    assert gated["handoff_required"] is True
    assert gated["status"] == "blocked_until_human_confirmation"

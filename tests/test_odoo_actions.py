from scripts.odoo.odoo_actions import OdooActions


class StubClient:
    def __init__(self):
        self.calls = []

    def execute_kw(self, model, method, args=None, kwargs=None, ensure_auth=True):
        self.calls.append((model, method, args, kwargs, ensure_auth))
        if method == "search_read":
            return [{"id": 1, "name": "Opp A"}]
        return 42


def test_create_contact_builds_values():
    client = StubClient()
    actions = OdooActions(client)
    rec_id = actions.create_contact(name="Ana", email="ana@example.com", phone="123")
    assert rec_id == 42
    model, method, args, *_ = client.calls[0]
    assert model == "res.partner"
    assert method == "create"
    assert args[0]["name"] == "Ana"


def test_create_lead_sets_type_lead():
    client = StubClient()
    actions = OdooActions(client)
    actions.create_lead(name="Lead X")
    model, method, args, *_ = client.calls[0]
    assert model == "crm.lead"
    assert args[0]["type"] == "lead"


def test_create_opportunity_sets_type_opportunity():
    client = StubClient()
    actions = OdooActions(client)
    actions.create_opportunity(name="Deal Y", expected_revenue=1000)
    model, method, args, *_ = client.calls[0]
    assert model == "crm.lead"
    assert args[0]["type"] == "opportunity"
    assert args[0]["expected_revenue"] == 1000.0


def test_schedule_activity_model():
    client = StubClient()
    actions = OdooActions(client)
    actions.schedule_activity(model="crm.lead", res_id=10, summary="Llamar", activity_type_id=2)
    model, method, args, *_ = client.calls[0]
    assert model == "mail.activity"
    assert method == "create"
    assert args[0]["res_model"] == "crm.lead"


def test_search_opportunities():
    client = StubClient()
    actions = OdooActions(client)
    out = actions.search_opportunities(limit=5)
    assert out[0]["name"] == "Opp A"
    model, method, args, kwargs, *_ = client.calls[0]
    assert model == "crm.lead"
    assert method == "search_read"
    assert kwargs["limit"] == 5

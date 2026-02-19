import logging

import pytest

from scripts.odoo.odoo_client import OdooAuthError, OdooClient, OdooConfig, OdooExecutionError, _mask_secret


class DummyCommon:
    def __init__(self, uid=7):
        self.uid = uid

    def authenticate(self, db, username, password, ctx):
        return self.uid


class DummyModels:
    def __init__(self):
        self.calls = []

    def execute_kw(self, db, uid, password, model, method, args, kwargs):
        self.calls.append((db, uid, password, model, method, args, kwargs))
        return {"ok": True}


def build_client(uid=7):
    cfg = OdooConfig(url="https://example.odoo.com", db="db", username="user", password="secret")
    c = OdooClient(cfg)
    c._common = DummyCommon(uid=uid)
    c._models = DummyModels()
    return c


def test_mask_secret():
    assert _mask_secret("supersecret").startswith("su***")
    assert _mask_secret("ab") == "**"


def test_authenticate_ok():
    client = build_client(uid=9)
    assert client.authenticate() == 9
    assert client.uid == 9


def test_authenticate_fail():
    client = build_client(uid=0)
    with pytest.raises(OdooAuthError):
        client.authenticate()


def test_execute_kw_calls_model():
    client = build_client(uid=2)
    result = client.execute_kw("res.partner", "search", [[("id", ">", 0)]], {"limit": 1})
    assert result["ok"] is True
    assert client._models.calls[0][3] == "res.partner"


def test_execute_kw_retries(monkeypatch):
    client = build_client(uid=2)

    attempts = {"n": 0}

    def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise OSError("temporary")
        return 123

    client._models.execute_kw = flaky
    monkeypatch.setattr("time.sleep", lambda *_: None)

    out = client.execute_kw("crm.lead", "create", [{"name": "x"}])
    assert out == 123
    assert attempts["n"] == 2


def test_execute_kw_exhausts_retries(monkeypatch):
    client = build_client(uid=2)
    client.config = OdooConfig(
        url=client.config.url,
        db=client.config.db,
        username=client.config.username,
        password=client.config.password,
        retries=2,
    )

    def fail(*args, **kwargs):
        raise OSError("boom")

    client._models.execute_kw = fail
    monkeypatch.setattr("time.sleep", lambda *_: None)

    with pytest.raises(OdooExecutionError):
        client.execute_kw("crm.lead", "write", [[1], {"name": "x"}])


def test_audit_masks_password(caplog):
    client = build_client(uid=4)
    with caplog.at_level(logging.INFO):
        client.authenticate(force=True)
    text = "\n".join(r.message for r in caplog.records)
    assert "secret" not in text
    assert "***" in text

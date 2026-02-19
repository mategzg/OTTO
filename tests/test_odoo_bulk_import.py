import csv
import json
from pathlib import Path

import pytest

from scripts.odoo.odoo_bulk_import import (
    OdooClient,
    dedupe_rows,
    run_pipeline,
    validate_and_prepare,
)


class FakeClient(OdooClient):
    def __init__(self, existing=None):
        super().__init__(enabled=True)
        self._existing = existing or {}
        self.created_payloads = []

    def find_existing_contacts(self, emails, phones):
        return self._existing

    def create_contacts(self, records):
        self.created_payloads.extend(records)
        return list(range(1000, 1000 + len(records)))



def write_csv(path: Path, rows):
    headers = [
        "name",
        "email",
        "phone",
        "mobile",
        "company_name",
        "street",
        "city",
        "state",
        "zip",
        "country",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(r)



def test_validation_and_dedupe():
    rows = [
        {"name": "Alice", "email": "a@x.com", "phone": "", "mobile": ""},
        {"name": "", "email": "bad", "phone": "", "mobile": ""},
        {"name": "Alice 2", "email": "a@x.com", "phone": "", "mobile": ""},
    ]
    ok, errs = validate_and_prepare(rows)
    assert len(ok) == 2
    assert len(errs) == 1
    unique, dupes = dedupe_rows(ok)
    assert len(unique) == 1
    assert len(dupes) == 1



def test_apply_requires_explicit_flag(tmp_path):
    csv_path = tmp_path / "in.csv"
    write_csv(csv_path, [{"name": "A", "email": "a@x.com", "phone": "", "mobile": ""}])

    with pytest.raises(SystemExit):
        run_pipeline(csv_path, "apply", False, FakeClient(), tmp_path / "reports")



def test_dry_run_does_not_create(tmp_path):
    csv_path = tmp_path / "in.csv"
    write_csv(csv_path, [{"name": "A", "email": "a@x.com", "phone": "", "mobile": ""}])
    client = FakeClient()

    run_pipeline(csv_path, "dry-run", False, client, tmp_path / "reports")
    assert client.created_payloads == []



def test_apply_creates_and_writes_rollback(tmp_path):
    csv_path = tmp_path / "in.csv"
    write_csv(
        csv_path,
        [
            {"name": "A", "email": "a@x.com", "phone": "", "mobile": ""},
            {"name": "B", "email": "", "phone": "+51 999 111 222", "mobile": ""},
        ],
    )
    client = FakeClient(existing={"email:already@x.com": 55})

    run_pipeline(csv_path, "apply", True, client, tmp_path / "reports")

    files = list((tmp_path / "reports").glob("bulk_import_rollback_*.json"))
    assert files, "rollback file should be created"
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert len(payload["created_ids"]) == 2

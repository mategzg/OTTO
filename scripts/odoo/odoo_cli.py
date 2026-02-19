"""Internal CLI for OTTO Odoo toolkit.

Not intended for end-users.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .odoo_actions import OdooActions
from .odoo_client import OdooClient, OdooConfig, configure_default_logging


def _json_print(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="odoo_cli", description="Internal OTTO Odoo CLI")
    parser.add_argument("--log-level", default="INFO")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping-auth", help="Authenticate and return UID")

    p = sub.add_parser("create-contact")
    p.add_argument("--name", required=True)
    p.add_argument("--email")
    p.add_argument("--phone")
    p.add_argument("--company-name")

    p = sub.add_parser("create-lead")
    p.add_argument("--name", required=True)
    p.add_argument("--contact-name")
    p.add_argument("--email")
    p.add_argument("--phone")

    p = sub.add_parser("schedule-activity")
    p.add_argument("--model", required=True)
    p.add_argument("--res-id", required=True, type=int)
    p.add_argument("--summary", required=True)
    p.add_argument("--activity-type-id", required=True, type=int)
    p.add_argument("--user-id", type=int)
    p.add_argument("--date-deadline")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_default_logging()

    config = OdooConfig.from_env()
    client = OdooClient(config)
    actions = OdooActions(client)

    if args.command == "ping-auth":
        uid = client.authenticate()
        _json_print({"ok": True, "uid": uid})
        return 0

    if args.command == "create-contact":
        rec_id = actions.create_contact(
            name=args.name,
            email=args.email,
            phone=args.phone,
            company_name=args.company_name,
        )
        _json_print({"ok": True, "model": "res.partner", "id": rec_id})
        return 0

    if args.command == "create-lead":
        rec_id = actions.create_lead(
            name=args.name,
            contact_name=args.contact_name,
            email_from=args.email,
            phone=args.phone,
        )
        _json_print({"ok": True, "model": "crm.lead", "id": rec_id})
        return 0

    if args.command == "schedule-activity":
        rec_id = actions.schedule_activity(
            model=args.model,
            res_id=args.res_id,
            summary=args.summary,
            activity_type_id=args.activity_type_id,
            user_id=args.user_id,
            date_deadline=args.date_deadline,
        )
        _json_print({"ok": True, "model": "mail.activity", "id": rec_id})
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

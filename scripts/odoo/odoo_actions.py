"""Atomic Odoo actions used by OTTO natural-language workflows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .odoo_client import OdooClient


@dataclass
class OdooActions:
    client: OdooClient

    # ---------- Contact ----------
    def create_contact(
        self,
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        company_name: Optional[str] = None,
        mobile: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        vals: Dict[str, Any] = {"name": name}
        if email:
            vals["email"] = email
        if phone:
            vals["phone"] = phone
        if mobile:
            vals["mobile"] = mobile
        if company_name:
            vals["company_name"] = company_name
        if extra:
            vals.update(extra)
        return int(self.client.execute_kw("res.partner", "create", [vals]))

    # ---------- Lead / Opportunity ----------
    def create_lead(
        self,
        name: str,
        contact_name: Optional[str] = None,
        email_from: Optional[str] = None,
        phone: Optional[str] = None,
        description: Optional[str] = None,
        expected_revenue: Optional[float] = None,
        probability: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        vals: Dict[str, Any] = {"name": name, "type": "lead"}
        if contact_name:
            vals["contact_name"] = contact_name
        if email_from:
            vals["email_from"] = email_from
        if phone:
            vals["phone"] = phone
        if description:
            vals["description"] = description
        if expected_revenue is not None:
            vals["expected_revenue"] = float(expected_revenue)
        if probability is not None:
            vals["probability"] = float(probability)
        if extra:
            vals.update(extra)
        return int(self.client.execute_kw("crm.lead", "create", [vals]))

    def create_opportunity(
        self,
        name: str,
        partner_id: Optional[int] = None,
        expected_revenue: Optional[float] = None,
        probability: Optional[float] = None,
        user_id: Optional[int] = None,
        stage_id: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        vals: Dict[str, Any] = {"name": name, "type": "opportunity"}
        if partner_id:
            vals["partner_id"] = int(partner_id)
        if expected_revenue is not None:
            vals["expected_revenue"] = float(expected_revenue)
        if probability is not None:
            vals["probability"] = float(probability)
        if user_id:
            vals["user_id"] = int(user_id)
        if stage_id:
            vals["stage_id"] = int(stage_id)
        if extra:
            vals.update(extra)
        return int(self.client.execute_kw("crm.lead", "create", [vals]))

    def convert_lead_to_opportunity(self, lead_id: int) -> bool:
        # Odoo CRM action for converting a lead in-place.
        result = self.client.execute_kw("crm.lead", "action_set_opportunity", [[int(lead_id)]])
        return bool(result)

    # ---------- Activity ----------
    def schedule_activity(
        self,
        model: str,
        res_id: int,
        summary: str,
        activity_type_id: int,
        user_id: Optional[int] = None,
        note: Optional[str] = None,
        date_deadline: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        vals: Dict[str, Any] = {
            "res_model": model,
            "res_id": int(res_id),
            "summary": summary,
            "activity_type_id": int(activity_type_id),
        }
        if user_id:
            vals["user_id"] = int(user_id)
        if note:
            vals["note"] = note
        if date_deadline:
            vals["date_deadline"] = date_deadline
        if extra:
            vals.update(extra)

        return int(self.client.execute_kw("mail.activity", "create", [vals]))

    # ---------- Helpers ----------
    def search_opportunities(
        self,
        domain: Optional[List[Any]] = None,
        fields: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        domain = domain or [["type", "=", "opportunity"]]
        fields = fields or ["name", "stage_id", "expected_revenue", "probability", "partner_id"]
        return list(
            self.client.execute_kw(
                "crm.lead",
                "search_read",
                [domain],
                {"fields": fields, "limit": int(limit)},
            )
        )

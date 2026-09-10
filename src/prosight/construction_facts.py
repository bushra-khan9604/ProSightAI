"""Tenant/project-scoped SQL reads for authoritative construction facts."""

from __future__ import annotations

import uuid
from contextlib import closing
from typing import Any


FACT_QUERIES = {
    "projects": """
        select p.id,p.code,p.name,p.description,p.project_type,p.delivery_method,
               p.contract_type,p.status,p.access_mode,p.country_code,p.location,
               p.currency_code,p.contract_value,p.original_budget,p.gross_floor_area,
               p.planned_start_date,p.planned_finish_date,p.actual_start_date,
               p.actual_finish_date,p.reporting_date,p.progress_percent,
               client.legal_name as client
        from construction.projects p
        left join construction.clients client
          on client.organization_id=p.organization_id and client.id=p.client_id
        where p.organization_id=%(organization_id)s::uuid
          and p.id=any(%(project_ids)s::uuid[])
        order by p.code
    """,
    "risks": """
        select r.id,r.project_id,r.risk_number,r.title,r.status,
               r.probability_score,r.impact_score,r.exposure_score,
               r.financial_exposure,r.currency_code,r.target_date
        from construction.risks r
        where r.organization_id=%(organization_id)s::uuid
          and r.project_id=any(%(project_ids)s::uuid[])
        order by r.project_id,r.risk_number
    """,
    "claims": """
        select c.id,c.project_id,c.claim_number,c.title,c.status,
               c.claimed_amount,c.assessed_amount,c.approved_amount,
               c.currency_code,c.claimed_days,c.approved_days
        from construction.claims c
        where c.organization_id=%(organization_id)s::uuid
          and c.project_id=any(%(project_ids)s::uuid[])
        order by c.project_id,c.claim_number
    """,
    "daily_reports": """
        select d.id,d.project_id,d.report_date,d.shift_code,d.status,
               d.work_completed,d.planned_work,d.delays_and_constraints
        from construction.daily_reports d
        where d.organization_id=%(organization_id)s::uuid
          and d.project_id=any(%(project_ids)s::uuid[])
        order by d.project_id,d.report_date desc
    """,
}


class ConstructionFacts:
    """Read structured facts only from the authoritative construction layer."""

    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    def query(self, fact: str, organization_id: str, allowed_project_ids: list[str]) -> list[dict[str, Any]]:
        try:
            uuid.UUID(organization_id)
            project_ids = [str(uuid.UUID(value)) for value in allowed_project_ids]
        except ValueError:
            raise ValueError("Organization and project scopes must be UUIDs") from None
        if fact not in FACT_QUERIES:
            raise ValueError("Unsupported structured fact")
        if not project_ids:
            return []
        with closing(self.connection_factory()) as connection:
            rows = connection.execute_native(
                FACT_QUERIES[fact],
                {"organization_id": organization_id, "project_ids": project_ids},
            ).fetchall()
        return [dict(row) for row in rows]

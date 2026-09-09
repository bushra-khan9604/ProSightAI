"""Canonical semantic schemas shared by workbook preview and import workflows."""

from __future__ import annotations

from typing import Any


SEMANTIC_SCHEMAS: dict[str, tuple[str, ...]] = {
    "employees": (
        "employee_id", "synthetic_name", "role", "department",
        "home_project_id", "employment_type", "join_date", "basic_aed",
        "allowance_aed", "gross_monthly_aed", "status", "data_origin",
    ),
    "training": (
        "training_id", "employee_id", "course", "completed_date",
        "expiry_date", "status", "evidence_id",
    ),
    "attendance": (
        "timesheet_id", "employee_id", "project_id", "work_date",
        "attendance_status", "regular_hours", "ot_hours", "total_hours",
    ),
    "payroll": (
        "payroll_id", "employee_id", "project_id", "month", "basic_aed",
        "allowance_aed", "ot_hours", "ot_rate_aed", "ot_pay_aed",
        "gross_aed", "employer_burden_aed", "total_cost_aed",
        "payment_date", "days_worked", "paid_leave_days",
    ),
    "direct_allocation": (
        "employee_id", "project_id", "month", "fte_allocation",
        "regular_hours", "ot_hours", "payroll_cost_aed", "basis",
    ),
    "subcontract_crews": (
        "subcontract_id", "project_id", "vendor_id", "month", "trade",
        "planned_workers", "actual_workers", "worker_variance",
        "available_labor_hours", "definition",
    ),
    "deployment_forecast": (
        "project_id", "month", "direct_headcount", "subcontract_workers", "basis",
    ),
    "manpower": (
        "employee_id", "employee_name", "designation", "department",
        "project_code", "mobilized_project_code", "category", "allocation_percent",
        "allocation_hours", "status", "current_location", "effective_date",
        "leave_balance", "remarks",
    ),
    "schedule": (
        "project_code", "activity_id", "wbs_code", "activity_name",
        "baseline_start", "baseline_finish", "current_start", "current_finish",
        "actual_start", "actual_finish", "original_duration_days",
        "remaining_duration_days", "planned_percent", "actual_percent", "status",
        "predecessor_ids", "responsible_owner", "reporting_date",
    ),
    "invoice": (
        "project_code", "job_number", "invoice_id", "draft_invoice_number",
        "invoice_date", "purchase_order_number", "contract_reference",
        "work_description", "currency", "amount_excluding_tax", "tax_amount",
        "amount_including_tax", "submission_date", "approval_status", "payment_status",
        "payment_terms_days", "expected_remittance_date", "client_reference",
        "risk_profile", "rejection_reason", "remarks",
    ),
}


def normalize_header(value: Any) -> str:
    """Normalize labels so spelling, punctuation, and spacing do not matter."""
    text = str(value or "").casefold()
    return "".join(character for character in text if character.isalnum())


def semantic_match_headers(
    actual_headers: list[Any], expected_headers: list[str], aliases: dict[str, set[str]]
) -> tuple[list[str], dict[str, Any]]:
    """Map source labels to expected labels and report confidence/provenance.

    Only high-confidence synonym or exact matches are applied automatically.
    Missing or ambiguous fields remain visible to the caller for Admin review;
    this prevents a guessed column from silently changing project data.
    """
    normalized_aliases = {
        expected: {normalize_header(expected), *(normalize_header(alias) for alias in values)}
        for expected, values in aliases.items()
    }
    mapped: list[str] = []
    matches: dict[str, dict[str, Any]] = {}
    used: set[str] = set()
    for raw in actual_headers:
        label = str(raw or "").strip()
        normalized = normalize_header(label)
        candidates = [
            expected for expected in expected_headers
            if expected not in used and normalized in normalized_aliases.get(expected, {normalize_header(expected)})
        ]
        if len(candidates) == 1:
            expected = candidates[0]
            used.add(expected)
            mapped.append(expected)
            matches[expected] = {"source": label, "confidence": 1.0}
        else:
            mapped.append(label)
    missing = [expected for expected in expected_headers if expected not in used]
    return mapped, {
        "matches": matches,
        "missing": missing,
        "confidence": round(len(matches) / max(len(expected_headers), 1), 3),
        "mapping_required": bool(missing),
    }

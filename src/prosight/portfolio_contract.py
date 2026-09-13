"""Stable database and API field contracts for portfolio workbook imports."""

from __future__ import annotations


MANPOWER_DB_COLUMNS = (
    "serial_number", "emp_code", "name", "designation", "department",
    "mobilized_project", "current_project", "category", "current_location",
    "allocation", "status", "leave_balance", "remarks",
    "current_project_code", "mobilized_project_code",
)

INVOICE_DB_COLUMNS = (
    "serial_number", "proforma_date", "draft_invoice_number", "job_number",
    "sap_po_number", "po_line_number", "contract_number", "coo_number",
    "icv_percent", "icv_five_percent_usd", "invoice_value_usd",
    "invoice_value_aed", "invoice_value_excl_tax_icv_usd",
    "invoice_value_excl_tax_icv_aed", "tax_invoice_reference",
    "ps_job_officer", "client_job_officer", "work_description", "avl_status",
    "work_year", "asset", "icv_claim_year", "last_discussion_month", "mm_yy",
    "status", "submission_date", "approval_current_date",
    "days_pending_approval", "reason_for_rejection", "aging_reference",
    "approval_status", "payment_status", "client_reference", "payment_terms_days",
    "days_pending_remittance", "payment_current_date", "expected_remittance_date",
    "outstanding_status", "project", "levels", "tax_invoice_taken_outstanding",
    "aging_of_approval", "risk_profile", "remarks", "project_code",
)

# Older API consumers received these generated keys from data_json. Keep them as
# read aliases while using valid, explicit database column names internally.
INVOICE_LEGACY_ALIASES = {
    "sap_po_nono": "sap_po_number",
    "po_lineno": "po_line_number",
    "contract": "contract_number",
    "coo": "coo_number",
    "icv_%": "icv_percent",
    "icv_@_5%_(usd)": "icv_five_percent_usd",
    "invoice_value_excl_tax_&_icv_(usd)": "invoice_value_excl_tax_icv_usd",
    "invoice_value_excl_tax_&_icv_(aed)": "invoice_value_excl_tax_icv_aed",
    "tax_invoice__inv_ref": "tax_invoice_reference",
    "avl__non-avl": "avl_status",
    "year_of_work_done": "work_year",
    "last_disc_month": "last_discussion_month",
    "current_date": "approval_current_date",
    "days_pending_approval_action": "days_pending_approval",
    "aging_(ref)": "aging_reference",
    "client_ref": "client_reference",
    "payment_terms_(days)": "payment_terms_days",
    "days_pending_for_remittance": "days_pending_remittance",
    "current_date_(payment)": "payment_current_date",
}


def with_invoice_legacy_aliases(item: dict) -> dict:
    """Return an invoice response that preserves pre-migration JSON keys."""
    result = dict(item)
    for legacy, canonical in INVOICE_LEGACY_ALIASES.items():
        result.setdefault(legacy, result.get(canonical))
    return result

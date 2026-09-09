"""Canonical multi-project manpower and invoice workbook parsing."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from openpyxl import Workbook, load_workbook

from .schemas import normalize_header, semantic_match_headers


MANPOWER_HEADERS = [
    "Sr.no", "EMP Code", "Name", "Designation", "Department",
    "Mobilized Project", "Current Project", "Category", "Current Location",
    "Allocation", "Status", "Leave Balance", "Remarks",
]
MANPOWER_OPTIONAL_HEADERS = [
    "Period Start", "Period End", "Capacity Hours", "Planned Hours",
    "Actual Hours", "Billable Hours", "Leave Hours", "Allocation Percent",
    "Billing Rate", "Cost Rate", "Revision",
]
SCHEDULE_HEADERS = [
    "Activity ID", "Activity Name", "Start", "Finish", "Original Duration",
]
INVOICE_HEADERS = [
    "S/N", "Prof. Date", "Draft/ Prof. INV no.", "Job No", "SAP PO No#",
    "PO Line#", "Contract", "COO", "ICV %", "ICV @ 5% (USD)",
    "Invoice Value Excl. VAT (USD)", "Invoice Value Excl. VAT (AED)",
    "Invoice Value Excl. Tax & ICV (USD)", "Invoice Value Excl. Tax & ICV (AED)",
    "Tax Invoice/ Inv Ref", "P.S Job Officer", "Client Job Officer",
    "Work Description", "AVL/ NON-AVL", "Year of Work Done", "Asset",
    "ICV Claim Year", "Last Disc. Month", "MM/YY", "INVOICE STATUS",
    "Submission Date/ Status Change Date", "Current Date",
    "Days Pending Approval/Action", "Reason for Rejection", "Aging (Ref)",
    "INVOICE Approval STATUS", "Invoice PAYMENT Status (Ref)", "Client Ref",
    "Payment Terms (Days)", "Days Pending for Remittance", "Current Date (Payment)",
    "Expected Remittance Date", "Outstanding Status", "Project", "Levels",
    "Tax Invoice Taken Outstanding", "Aging of Approval", "Risk Profile", "Remarks",
]
INVOICE_DATE_HEADERS = {
    "Prof. Date", "Submission Date/ Status Change Date", "Current Date",
    "Current Date (Payment)", "Expected Remittance Date",
}
INVOICE_NUMBER_HEADERS = {
    "ICV %", "ICV @ 5% (USD)", "Invoice Value Excl. VAT (USD)",
    "Invoice Value Excl. VAT (AED)", "Invoice Value Excl. Tax & ICV (USD)",
    "Invoice Value Excl. Tax & ICV (AED)", "Days Pending Approval/Action",
    "Payment Terms (Days)", "Days Pending for Remittance",
}

INVOICE_FIELD_MAP = {
    header: {
        "S/N": "serial_number",
        "Prof. Date": "proforma_date",
        "Draft/ Prof. INV no.": "draft_invoice_number",
        "Job No": "job_number",
        "Project": "project",
        "Levels": "levels",
        "INVOICE STATUS": "status",
        "INVOICE Approval STATUS": "approval_status",
        "Invoice PAYMENT Status (Ref)": "payment_status",
        "Risk Profile": "risk_profile",
        "Invoice Value Excl. VAT (USD)": "invoice_value_usd",
        "Invoice Value Excl. VAT (AED)": "invoice_value_aed",
        "Submission Date/ Status Change Date": "submission_date",
        "Expected Remittance Date": "expected_remittance_date",
    }.get(header, header.lower().replace(" ", "_").replace("/", "_").replace(".", "").replace("#", "no"))
    for header in INVOICE_HEADERS
}
MANPOWER_FIELD_MAP = {
    "Sr.no": "serial_number", "EMP Code": "emp_code", "Name": "name",
    "Designation": "designation", "Department": "department",
    "Mobilized Project": "mobilized_project", "Current Project": "current_project",
    "Category": "category", "Current Location": "current_location",
    "Allocation": "allocation", "Status": "status",
    "Leave Balance": "leave_balance", "Remarks": "remarks",
}

# The importer accepts common construction/finance labels while preserving
# the existing canonical template. Ambiguous or genuinely missing fields are
# reported for Admin mapping review rather than guessed.
PORTFOLIO_HEADER_ALIASES = {
    "EMP Code": {"employee id", "employee code", "staff id", "person id"},
    "Name": {"employee name", "full name", "staff name"},
    "Mobilized Project": {"mobilized project code", "mobilized to", "mobilized project"},
    "Current Project": {"current project code", "assigned project", "project code"},
    "Current Location": {"location", "work location"},
    "Allocation": {"allocation percent", "allocation percentage", "allocation hours"},
    "Leave Balance": {"leave days", "remaining leave", "leave balance"},
    "Period Start": {"start date", "period start", "week start", "month start"},
    "Period End": {"end date", "period end", "week end", "month end"},
    "Capacity Hours": {"capacity", "capacity hrs", "available hours", "working hours"},
    "Planned Hours": {"planned hours", "planned hrs", "forecast hours", "budgeted hours"},
    "Actual Hours": {"actual hours", "actual hrs", "worked hours", "timesheet hours"},
    "Billable Hours": {"billable hours", "billable hrs", "chargeable hours"},
    "Leave Hours": {"leave hours", "absence hours"},
    "Allocation Percent": {"allocation %", "allocation percent", "allocation percentage"},
    "Billing Rate": {"billing rate", "bill rate", "charge rate"},
    "Cost Rate": {"cost rate", "labor cost rate"},
    "Revision": {"revision", "version"},
    "Activity ID": {"activity id", "activity code", "task id", "task code"},
    "Activity Name": {"activity", "task", "task name", "description"},
    "Start": {"start date", "planned start", "baseline start", "current start"},
    "Finish": {"finish date", "end date", "planned finish", "baseline finish", "current finish"},
    "Original Duration": {"duration", "duration days", "original duration days"},
    "Draft/ Prof. INV no.": {"draft invoice number", "proforma invoice number", "invoice number", "invoice id"},
    "Job No": {"job number", "job code", "work order", "work order number"},
    "SAP PO No#": {"po number", "purchase order", "purchase order number"},
    "Contract": {"contract reference", "contract number"},
    "Work Description": {"description", "scope", "work description"},
    "Invoice Value Excl. VAT (USD)": {"amount excluding tax usd", "amount excluding vat usd", "invoice amount usd", "net amount usd"},
    "Invoice Value Excl. VAT (AED)": {"amount excluding tax aed", "amount excluding vat aed", "invoice amount aed", "net amount aed"},
    "Submission Date/ Status Change Date": {"submission date", "status change date"},
    "Expected Remittance Date": {"expected payment date", "expected remittance date"},
    "INVOICE STATUS": {"invoice status", "status"},
    "INVOICE Approval STATUS": {"invoice approval status", "approval status"},
    "Invoice PAYMENT Status (Ref)": {"payment status", "invoice payment status"},
    "Client Ref": {"client reference", "client ref"},
    "Payment Terms (Days)": {"payment terms", "payment terms days"},
    "Risk Profile": {"risk", "risk profile"},
    "Reason for Rejection": {"rejection reason", "reason for rejection"},
    "Project": {"project code", "project name", "project"},
}


def _value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip()
    return value


def _decimal(value: Any, label: str, row: int, required: bool = False) -> float | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"{label} row {row}: value is required")
        return None
    try:
        return float(Decimal(str(value).replace(",", "").replace("%", "").strip()))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{label} row {row}: invalid number {value!r}") from error


def _date(value: Any, label: str, row: int) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d-%b-%y", "%d %B %Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"{label} row {row}: invalid date {value!r}")


def _semantic_headers(
    sheet: Any, expected: list[str], optional: list[str] | None = None
) -> tuple[list[str], int, dict[str, Any]]:
    """Find a likely header row and map equivalent labels to canonical names."""
    optional = optional or []
    all_expected = [*expected, *optional]
    best: tuple[int, list[str], int, dict[str, Any]] | None = None
    for row_number, values in enumerate(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row or 1, 10), values_only=True), start=1):
        actual = [str(value or "").strip() for value in values]
        mapped, mapping = semantic_match_headers(actual, all_expected, PORTFOLIO_HEADER_ALIASES)
        required_missing = [field for field in expected if field not in mapping["matches"]]
        mapping["missing"] = required_missing
        mapping["optional_missing"] = [field for field in optional if field not in mapping["matches"]]
        mapping["mapping_required"] = bool(required_missing)
        score = len(mapping["matches"])
        if best is None or score > best[0]:
            best = (score, mapped, row_number, mapping)
    if best is None or best[0] == 0:
        raise ValueError(f"{sheet.title} does not contain a recognizable header row")
    missing = best[3]["missing"]
    if missing:
        raise ValueError(
            f"{sheet.title} requires Admin mapping for missing fields: {', '.join(missing)}"
        )
    return best[1], best[2], best[3]


def _records(sheet: Any, headers: list[str], header_row: int) -> list[tuple[int, dict[str, Any]]]:
    rows = sheet.iter_rows(min_row=header_row + 1, values_only=True)
    return [
        (number, {header: _value(value) for header, value in zip(headers, values)})
        for number, values in enumerate(rows, start=2)
        if any(value not in (None, "") for value in values)
    ]


def parse_portfolio_workbook(
    path: Path,
    resolve_project: Callable[[str], str | None],
    dataset: str = "combined",
    project_code: str | None = None,
) -> dict[str, Any]:
    """Validate the canonical workbook and return transaction-ready records."""
    if dataset not in {"combined", "manpower", "invoices", "schedule"}:
        raise ValueError("Unsupported portfolio import dataset")
    workbook = load_workbook(path, read_only=False, data_only=True, keep_links=False)
    try:
        required_sheets = {
            "combined": {"Manpower", "Projects Invoices"},
            "manpower": {"Manpower"},
            "invoices": {"Projects Invoices"},
            "schedule": {"Project Schedule"},
        }[dataset]
        missing_sheets = required_sheets - set(workbook.sheetnames)
        if missing_sheets:
            raise ValueError(f"Workbook is missing sheets: {', '.join(sorted(missing_sheets))}")
        manpower_sheet = workbook["Manpower"] if dataset in {"combined", "manpower"} else None
        invoice_sheet = workbook["Projects Invoices"] if dataset in {"combined", "invoices"} else None
        schedule_sheet = workbook["Project Schedule"] if dataset == "schedule" else None
        mappings: dict[str, Any] = {}
        manpower_headers = invoice_headers = schedule_headers = None
        if manpower_sheet:
            manpower_headers, manpower_row, mappings["manpower"] = _semantic_headers(
                manpower_sheet, MANPOWER_HEADERS, MANPOWER_OPTIONAL_HEADERS
            )
        if invoice_sheet:
            invoice_headers, invoice_row, mappings["invoice"] = _semantic_headers(invoice_sheet, INVOICE_HEADERS)
        if schedule_sheet:
            schedule_headers, schedule_row, mappings["schedule"] = _semantic_headers(schedule_sheet, SCHEDULE_HEADERS)
            if not project_code or not resolve_project(project_code):
                raise ValueError("Project Schedule requires an authorized project")

        manpower, employee_keys = [], set()
        for row_number, source in _records(manpower_sheet, manpower_headers, manpower_row) if manpower_sheet else []:
            emp_code = str(source.get("EMP Code") or "").strip()
            if not emp_code:
                raise ValueError(f"Manpower row {row_number}: EMP Code is required")
            if emp_code.casefold() in employee_keys:
                raise ValueError(f"Manpower row {row_number}: duplicate EMP Code {emp_code}")
            employee_keys.add(emp_code.casefold())
            current = resolve_project(str(source.get("Current Project") or ""))
            mobilized_raw = str(source.get("Mobilized Project") or "")
            mobilized = resolve_project(mobilized_raw) if mobilized_raw else None
            if not current:
                raise ValueError(f"Manpower row {row_number}: unknown Current Project")
            if mobilized_raw and not mobilized:
                raise ValueError(f"Manpower row {row_number}: unknown Mobilized Project")
            record = {MANPOWER_FIELD_MAP[key]: source.get(key) for key in MANPOWER_HEADERS}
            record.update(
                emp_code=emp_code, current_project_code=current,
                mobilized_project_code=mobilized,
                allocation=str(source.get("Allocation") or source.get("Allocation Percent") or "").strip() or None,
                leave_balance=_decimal(source.get("Leave Balance"), "Leave Balance", row_number),
                employee_id=emp_code,
                period_start=_date(source.get("Period Start"), "Period Start", row_number),
                period_end=_date(source.get("Period End"), "Period End", row_number),
                capacity_hours=_decimal(source.get("Capacity Hours"), "Capacity Hours", row_number),
                planned_hours=_decimal(source.get("Planned Hours"), "Planned Hours", row_number),
                actual_hours=_decimal(source.get("Actual Hours"), "Actual Hours", row_number),
                billable_hours=_decimal(source.get("Billable Hours"), "Billable Hours", row_number),
                leave_hours=_decimal(source.get("Leave Hours"), "Leave Hours", row_number),
                allocation_percent=_decimal(
                    source.get("Allocation Percent") or source.get("Allocation"),
                    "Allocation Percent", row_number,
                ),
                billing_rate=_decimal(source.get("Billing Rate"), "Billing Rate", row_number),
                cost_rate=_decimal(source.get("Cost Rate"), "Cost Rate", row_number),
                revision=str(source.get("Revision") or "").strip() or None,
                source_sheet=manpower_sheet.title, source_row=row_number,
            )
            manpower.append(record)

        invoices, invoice_keys = [], set()
        for row_number, source in _records(invoice_sheet, invoice_headers, invoice_row) if invoice_sheet else []:
            job_number = str(source.get("Job No") or "").strip()
            draft_number = str(source.get("Draft/ Prof. INV no.") or "").strip()
            if not job_number or not draft_number:
                raise ValueError(
                    f"Projects Invoices row {row_number}: Job No and Draft/ Prof. INV no. are required"
                )
            invoice_key = (job_number.casefold(), draft_number.casefold())
            if invoice_key in invoice_keys:
                raise ValueError(
                    f"Projects Invoices row {row_number}: duplicate invoice key "
                    f"{job_number} / {draft_number}"
                )
            invoice_keys.add(invoice_key)
            job_project = resolve_project(job_number)
            named_project = resolve_project(str(source.get("Project") or ""))
            if job_project and named_project and job_project != named_project:
                raise ValueError(f"Projects Invoices row {row_number}: Job No and Project conflict")
            project_code = job_project or named_project
            if not project_code:
                raise ValueError(f"Projects Invoices row {row_number}: project could not be resolved")
            record = {INVOICE_FIELD_MAP[key]: source.get(key) for key in INVOICE_HEADERS}
            for header in INVOICE_DATE_HEADERS:
                record[INVOICE_FIELD_MAP[header]] = _date(
                    source.get(header), header, row_number
                )
            for header in INVOICE_NUMBER_HEADERS:
                record[INVOICE_FIELD_MAP[header]] = _decimal(
                    source.get(header), header, row_number
                )
            record.update(
                job_number=job_number, draft_invoice_number=draft_number,
                project_code=project_code,
                invoice_value_usd=_decimal(
                    source.get("Invoice Value Excl. VAT (USD)"),
                    "Invoice Value Excl. VAT (USD)", row_number, True,
                ),
                invoice_value_aed=_decimal(
                    source.get("Invoice Value Excl. VAT (AED)"),
                    "Invoice Value Excl. VAT (AED)", row_number,
                ),
                source_sheet=invoice_sheet.title, source_row=row_number,
            )
            invoices.append(record)

        schedule, activity_keys = [], set()
        for row_number, source in _records(schedule_sheet, schedule_headers, schedule_row) if schedule_sheet else []:
            activity_id = str(source.get("Activity ID") or "").strip()
            activity_name = str(source.get("Activity Name") or "").strip()
            if not activity_id or not activity_name:
                raise ValueError(
                    f"Project Schedule row {row_number}: Activity ID and Activity Name are required"
                )
            key = activity_id.casefold()
            if key in activity_keys:
                raise ValueError(
                    f"Project Schedule row {row_number}: duplicate Activity ID {activity_id}"
                )
            activity_keys.add(key)
            start = _date(source.get("Start"), "Start", row_number)
            finish = _date(source.get("Finish"), "Finish", row_number)
            if not start or not finish:
                raise ValueError(f"Project Schedule row {row_number}: Start and Finish are required")
            if start > finish:
                raise ValueError(f"Project Schedule row {row_number}: Start must not be after Finish")
            duration = _decimal(
                source.get("Original Duration"), "Original Duration", row_number, True
            )
            if duration is None or duration < 0 or not duration.is_integer():
                raise ValueError(
                    f"Project Schedule row {row_number}: Original Duration must be a non-negative integer"
                )
            schedule.append({
                "project_code": project_code, "activity_id": activity_id,
                "activity_name": activity_name, "start": start, "finish": finish,
                "original_duration": int(duration),
                "source_sheet": schedule_sheet.title, "source_row": row_number,
            })

        return {
            "manpower": manpower,
            "invoices": invoices,
            "schedule": schedule,
            "counts": {"manpower": len(manpower), "invoices": len(invoices),
                       "schedule": len(schedule)},
            "semantic_mappings": mappings,
        }
    finally:
        workbook.close()


def generate_invoice_pivot(invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, float]] = {}
    for invoice in invoices:
        key = (str(invoice.get("levels") or ""), str(invoice.get("status") or ""))
        projects = grouped.setdefault(key, {})
        code = invoice["project_code"]
        projects[code] = round(projects.get(code, 0) + float(invoice["invoice_value_usd"]), 2)
    return [
        {
            "levels": levels, "status": status, "projects": projects,
            "grand_total": round(sum(projects.values()), 2),
        }
        for (levels, status), projects in sorted(grouped.items())
    ]


def create_portfolio_template(path: Path, dataset: str = "combined") -> Path:
    """Create a canonical combined or dataset-specific XLSX template."""
    if dataset not in {"combined", "manpower", "invoices", "schedule"}:
        raise ValueError("Unsupported portfolio template dataset")
    workbook = Workbook()
    first = workbook.active
    if dataset == "schedule":
        first.title = "Project Schedule"
        first.append(SCHEDULE_HEADERS)
        first.append(["A1001", "Receive PO", "30-Mar-26", "06-Apr-26", 6])
        first.append(["A1006", "Receive sketch from client", "06-Apr-26", "14-Apr-26", 7])
    elif dataset == "invoices":
        first.title = "Projects Invoices"
        first.append(INVOICE_HEADERS)
    else:
        first.title = "Manpower"
        first.append(MANPOWER_HEADERS)
        if dataset == "combined":
            invoices = workbook.create_sheet("Projects Invoices")
            invoices.append(INVOICE_HEADERS)
    workbook.save(path)
    return path

"""Canonical multi-project manpower and invoice workbook parsing."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from openpyxl import Workbook, load_workbook


MANPOWER_HEADERS = [
    "Sr.no", "EMP Code", "Name", "Designation", "Department",
    "Mobilized Project", "Current Project", "Category", "Current Location",
    "Allocation", "Status", "Leave Balance", "Remarks",
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
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"{label} row {row}: invalid date {value!r}")


def _headers(sheet: Any, expected: list[str]) -> None:
    actual = [str(cell.value or "").strip() for cell in next(sheet.iter_rows(max_row=1))]
    missing = [header for header in expected if header not in actual]
    if missing:
        raise ValueError(f"{sheet.title} is missing columns: {', '.join(missing)}")


def _records(sheet: Any) -> list[tuple[int, dict[str, Any]]]:
    rows = sheet.iter_rows(values_only=True)
    headers = [str(value or "").strip() for value in next(rows)]
    return [
        (number, {header: _value(value) for header, value in zip(headers, values)})
        for number, values in enumerate(rows, start=2)
        if any(value not in (None, "") for value in values)
    ]


def parse_portfolio_workbook(
    path: Path,
    resolve_project: Callable[[str], str | None],
) -> dict[str, Any]:
    """Validate the canonical workbook and return transaction-ready records."""
    workbook = load_workbook(path, read_only=False, data_only=True, keep_links=False)
    try:
        required_sheets = {"Manpower", "Projects Invoices"}
        missing_sheets = required_sheets - set(workbook.sheetnames)
        if missing_sheets:
            raise ValueError(f"Workbook is missing sheets: {', '.join(sorted(missing_sheets))}")
        manpower_sheet = workbook["Manpower"]
        invoice_sheet = workbook["Projects Invoices"]
        _headers(manpower_sheet, MANPOWER_HEADERS)
        _headers(invoice_sheet, INVOICE_HEADERS)

        manpower, employee_keys = [], set()
        for row_number, source in _records(manpower_sheet):
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
                allocation=str(source.get("Allocation") or "").strip() or None,
                leave_balance=_decimal(source.get("Leave Balance"), "Leave Balance", row_number),
            )
            manpower.append(record)

        invoices, invoice_keys = [], set()
        for row_number, source in _records(invoice_sheet):
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
            )
            invoices.append(record)

        return {
            "manpower": manpower,
            "invoices": invoices,
            "counts": {"manpower": len(manpower), "invoices": len(invoices)},
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


def create_portfolio_template(path: Path) -> Path:
    """Create the canonical two-sheet XLSX template."""
    workbook = Workbook()
    manpower = workbook.active
    manpower.title = "Manpower"
    manpower.append(MANPOWER_HEADERS)
    invoices = workbook.create_sheet("Projects Invoices")
    invoices.append(INVOICE_HEADERS)
    workbook.save(path)
    return path

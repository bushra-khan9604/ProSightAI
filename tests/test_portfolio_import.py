"""Canonical combined manpower and invoice import tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from prosight.ingestion.portfolio import (
    INVOICE_HEADERS,
    MANPOWER_HEADERS,
    SCHEDULE_HEADERS,
    create_portfolio_template,
    parse_portfolio_workbook,
)
from prosight.agents.database_manager import DatabaseManagerAgent
from prosight.repository import DEFAULT_DATA, ProjectRepository


class PortfolioImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = ProjectRepository(Path(self.temporary.name) / "portfolio.db")
        self.repository.initialize(DEFAULT_DATA)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def workbook(self, include_legacy_pivot: bool = False) -> Path:
        path = Path(self.temporary.name) / "portfolio.xlsx"
        workbook = Workbook()
        manpower = workbook.active
        manpower.title = "Manpower"
        manpower.append(MANPOWER_HEADERS)
        manpower.append([
            1, "EMP-001", "Aisha Khan", "Planner", "Planning",
            "Al Noor", "Marina Heights", "Staff", "Dubai", "Allocated",
            "Active", 18, "Mobilized",
        ])
        invoices = workbook.create_sheet("Projects Invoices")
        invoices.append(INVOICE_HEADERS)
        row = {header: None for header in INVOICE_HEADERS}
        row.update({
            "S/N": 1,
            "Draft/ Prof. INV no.": "INV-001",
            "Job No": "PRJ-2025-004",
            "Invoice Value Excl. VAT (USD)": 1250,
            "Invoice Value Excl. VAT (AED)": 4590,
            "Project": "Al Noor",
            "Levels": "Level 3",
            "INVOICE STATUS": "Submitted",
            "Tax Invoice Taken Outstanding": "Tax Invoice yet to prepare",
            "Aging of Approval": "Above 121 Days",
            "Aging (Ref)": "Above 121 Days",
        })
        invoices.append([row[header] for header in INVOICE_HEADERS])
        if include_legacy_pivot:
            pivot = workbook.create_sheet("Pivot Projects Invoice")
            pivot.append(["Levels", "INVOICE STATUS", "Al Noor", "Grand Total"])
            pivot.append(["Wrong Level", "Wrong Status", 999999, 999999])
        workbook.save(path)
        return path

    def test_valid_workbook_is_parsed_and_atomically_upserted(self):
        parsed = parse_portfolio_workbook(
            self.workbook(), self.repository.resolve_project_reference
        )
        record = self.repository.create_portfolio_import(
            "portfolio.xlsx", "checksum", "portfolio.xlsx", "planning_engineer"
        )
        completed = self.repository.apply_portfolio_import(record["id"], parsed)
        self.assertEqual("completed", completed["status"])
        manpower = self.repository.list_manpower("PRJ-2024-001")
        self.assertEqual("EMP-001", manpower[0]["emp_code"])
        self.assertEqual("Allocated", manpower[0]["allocation"])
        invoices = self.repository.list_invoices("PRJ-2025-004")
        self.assertEqual("INV-001", invoices[0]["draft_invoice_number"])
        self.assertEqual(
            "Tax Invoice yet to prepare",
            invoices[0]["tax_invoice_taken_outstanding"],
        )
        self.assertEqual("Above 121 Days", invoices[0]["aging_of_approval"])
        self.assertEqual("Above 121 Days", invoices[0]["aging_(ref)"])
        self.assertEqual(1250, self.repository.invoice_pivot()[0]["grand_total"])

    def test_legacy_pivot_sheet_is_ignored(self):
        parsed = parse_portfolio_workbook(
            self.workbook(include_legacy_pivot=True),
            self.repository.resolve_project_reference,
        )
        self.assertEqual(1, len(parsed["invoices"]))

    def test_repeat_import_updates_stable_keys_without_duplicates(self):
        parsed = parse_portfolio_workbook(
            self.workbook(), self.repository.resolve_project_reference
        )
        first = self.repository.create_portfolio_import(
            "one.xlsx", "one", "one.xlsx", "project_manager"
        )
        self.repository.apply_portfolio_import(first["id"], parsed)
        parsed["manpower"][0]["name"] = "Aisha K."
        parsed["invoices"][0]["invoice_value_usd"] = 2500
        second = self.repository.create_portfolio_import(
            "two.xlsx", "two", "two.xlsx", "project_manager"
        )
        result = self.repository.apply_portfolio_import(second["id"], parsed)
        self.assertEqual({"inserted": 0, "updated": 1}, result["summary"]["manpower"])
        self.assertEqual(1, len(self.repository.list_manpower()))
        self.assertEqual(2500, self.repository.invoice_pivot()[0]["grand_total"])

    def test_download_template_contains_only_source_sheets(self):
        path = Path(self.temporary.name) / "template.xlsx"
        create_portfolio_template(path)
        workbook = load_workbook(path, read_only=True)
        try:
            self.assertEqual(["Manpower", "Projects Invoices"], workbook.sheetnames)
        finally:
            workbook.close()

    def test_dataset_specific_templates_and_parsing(self):
        manpower_path = Path(self.temporary.name) / "manpower-template.xlsx"
        invoice_path = Path(self.temporary.name) / "invoice-template.xlsx"
        create_portfolio_template(manpower_path, "manpower")
        create_portfolio_template(invoice_path, "invoices")
        manpower_book = load_workbook(manpower_path, read_only=True)
        invoice_book = load_workbook(invoice_path, read_only=True)
        try:
            self.assertEqual(["Manpower"], manpower_book.sheetnames)
            self.assertEqual(["Projects Invoices"], invoice_book.sheetnames)
        finally:
            manpower_book.close()
            invoice_book.close()

        source = self.workbook()
        parsed_manpower = parse_portfolio_workbook(
            source, self.repository.resolve_project_reference, "manpower"
        )
        parsed_invoices = parse_portfolio_workbook(
            source, self.repository.resolve_project_reference, "invoices"
        )
        self.assertEqual(1, len(parsed_manpower["manpower"]))
        self.assertEqual([], parsed_manpower["invoices"])
        self.assertEqual([], parsed_invoices["manpower"])
        self.assertEqual(1, len(parsed_invoices["invoices"]))

    def test_schedule_template_parsing_and_upsert_retains_omitted_activities(self):
        path = Path(self.temporary.name) / "schedule.xlsx"
        create_portfolio_template(path, "schedule")
        workbook = load_workbook(path)
        try:
            sheet = workbook["Project Schedule"]
            self.assertEqual(SCHEDULE_HEADERS, [cell.value for cell in sheet[1]])
            sheet.delete_rows(2, sheet.max_row)
            sheet.append(["A1001", "Receive PO", "30-Mar-26", "06-Apr-26", 6])
            sheet.append(["A1006", "Receive sketch", "06-Apr-26", "14-Apr-26", 7])
            workbook.save(path)
        finally:
            workbook.close()
        parsed = parse_portfolio_workbook(
            path, self.repository.resolve_project_reference, "schedule", "PRJ-2024-001"
        )
        self.assertEqual("2026-03-30", parsed["schedule"][0]["start"])
        first = self.repository.create_portfolio_import(
            "schedule.xlsx", "schedule-one", str(path), "planning_engineer",
            "schedule", "PRJ-2024-001",
        )
        result = self.repository.apply_portfolio_import(first["id"], parsed)
        self.assertEqual({"inserted": 2, "updated": 0}, result["summary"]["schedule"])

        parsed["schedule"] = [{**parsed["schedule"][0], "activity_name": "Receive updated PO"}]
        second = self.repository.create_portfolio_import(
            "schedule-two.xlsx", "schedule-two", str(path), "project_manager",
            "schedule", "PRJ-2024-001",
        )
        result = self.repository.apply_portfolio_import(second["id"], parsed)
        self.assertEqual({"inserted": 0, "updated": 1}, result["summary"]["schedule"])
        activities = self.repository.list_project_schedule("PRJ-2024-001")
        self.assertEqual(["A1001", "A1006"], [item["activity_id"] for item in activities])
        self.assertEqual("Receive updated PO", activities[0]["activity_name"])
        evidence = DatabaseManagerAgent(self.repository).read(
            "Show the project schedule", "PRJ-2024-001", "project_manager"
        )
        self.assertEqual(["A1001", "A1006"], [item["activity_id"] for item in evidence.records])

    def test_schedule_rejects_duplicate_ids_and_invalid_boundaries(self):
        path = Path(self.temporary.name) / "bad-schedule.xlsx"
        workbook = Workbook();sheet = workbook.active;sheet.title = "Project Schedule"
        sheet.append(SCHEDULE_HEADERS)
        sheet.append(["A1", "First", "10-Apr-26", "01-Apr-26", 2])
        workbook.save(path)
        with self.assertRaisesRegex(ValueError, "Start must not be after Finish"):
            parse_portfolio_workbook(
                path, self.repository.resolve_project_reference, "schedule", "PRJ-2024-001"
            )


if __name__ == "__main__":
    unittest.main()

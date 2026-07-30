"""Canonical combined manpower and invoice import tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from prosight.ingestion.portfolio import (
    INVOICE_HEADERS,
    MANPOWER_HEADERS,
    create_portfolio_template,
    parse_portfolio_workbook,
)
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


if __name__ == "__main__":
    unittest.main()

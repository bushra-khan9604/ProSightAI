"""Manpower dashboard normalization and secure export tests."""

from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from prosight.api import _excel_safe, _manpower_state, create_app
from prosight.repository import DEFAULT_DATA, ProjectRepository


class ManpowerDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = ProjectRepository(Path(self.temporary.name) / "portfolio.db")
        self.repository.initialize(DEFAULT_DATA)
        imported = self.repository.create_portfolio_import(
            "manpower.xlsx", "manpower-checksum", "manpower.xlsx", "project_manager"
        )
        self.repository.apply_portfolio_import(imported["id"], {
            "manpower": [{
                "serial_number": 1,
                "emp_code": "EMP-001",
                "name": "=Unsafe Name",
                "designation": "Planner",
                "department": "Planning",
                "mobilized_project": "Al Noor",
                "mobilized_project_code": "PRJ-2025-004",
                "current_project": "Marina Heights",
                "current_project_code": "PRJ-2024-001",
                "category": "Direct",
                "current_location": "Dubai",
                "allocation": "Allocated",
                "status": "Active",
                "leave_balance": 18,
                "remarks": "Current assignment",
            }],
            "invoices": [],
            "schedule": [],
        })
        self.client = TestClient(create_app(self.repository))

    def tearDown(self) -> None:
        self.client.close()
        self.temporary.cleanup()

    def test_normalizes_workforce_states_and_spreadsheet_values(self):
        self.assertEqual("allocated", _manpower_state({"current_project_code": "P1", "status": "Active"}))
        self.assertEqual("on_leave", _manpower_state({"current_project_code": "P1", "status": "On Leave"}))
        self.assertEqual("not_allocated", _manpower_state({"current_project_code": "P1", "allocation": "Bench"}))
        self.assertEqual("not_allocated", _manpower_state({"current_project_code": None}))
        self.assertEqual("'=SUM(A1:A2)", _excel_safe("=SUM(A1:A2)"))

    def test_exports_filtered_scenario_without_persisting_it(self):
        response = self.client.post("/api/portfolio/manpower/export?role=project_manager", json={
            "employee_codes": ["EMP-001", "EMP-001"],
            "scenario_changes": [{
                "emp_code": "EMP-001",
                "workforce_state": "allocated",
                "target_project_code": "PRJ-2025-004",
            }],
        })
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response.headers["content-type"],
        )
        workbook = load_workbook(BytesIO(response.content), data_only=False)
        try:
            register = workbook["Filtered Manpower"]
            self.assertEqual("'=Unsafe Name", register["B2"].value)
            self.assertEqual("PRJ-2025-004", register["G2"].value)
            self.assertEqual("Allocated", register["I2"].value)
            self.assertEqual("EMP-001", workbook["Scenario Changes"]["A2"].value)
            self.assertEqual(0, workbook["Scenario Summary"]["D3"].value)
        finally:
            workbook.close()
        self.assertEqual("PRJ-2024-001", self.repository.list_manpower()[0]["current_project_code"])

    def test_export_rejects_inaccessible_records_and_projects(self):
        missing_employee = self.client.post("/api/portfolio/manpower/export?role=employee", json={
            "employee_codes": ["EMP-404"], "scenario_changes": [],
        })
        self.assertEqual(403, missing_employee.status_code)
        missing_project = self.client.post("/api/portfolio/manpower/export?role=employee", json={
            "employee_codes": ["EMP-001"],
            "scenario_changes": [{
                "emp_code": "EMP-001", "workforce_state": "allocated",
                "target_project_code": "PRJ-404",
            }],
        })
        self.assertEqual(403, missing_project.status_code)


if __name__ == "__main__":
    unittest.main()

"""API tests for reviewed new-project creation."""

import json
import tempfile
import unittest
from contextlib import closing
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from prosight.api import create_app
from prosight.repository import DEFAULT_DATA, ProjectRepository


class ProjectCreationTests(unittest.TestCase):
    """Verify authorization, approval, and immediate project-list availability."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = ProjectRepository(Path(self.temporary.name) / "projects.db")
        self.repository.initialize(DEFAULT_DATA)
        self.client = TestClient(create_app(self.repository))
        self.draft = {
            "code": "PRJ-2027-010",
            "name": "Desert Horizon Solar Campus",
            "status": "future",
            "client": "Emirates Clean Energy Authority",
            "location": "Al Dhafra, Abu Dhabi, UAE",
            "contract_value_usd": 185000000,
            "planned_start": "2027-02-01",
            "planned_finish": "2029-06-30",
            "revised_finish": "2029-06-30",
            "reporting_date": "2026-07-24",
            "baseline_progress": 0,
            "revised_progress": 0,
            "actual_progress": 0,
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_admin_preview_and_approval_adds_project(self):
        preview = self.client.post(
            "/api/projects/change-preview?role=admin", json=self.draft
        )
        self.assertEqual(202, preview.status_code)
        change = preview.json()
        self.assertEqual("pending", change["status"])

        approved = self.client.post(
            f"/api/change-requests/{change['id']}/approve?role=admin"
        )
        self.assertEqual(200, approved.status_code)

        projects = self.client.get("/api/projects?role=admin").json()
        created = next(item for item in projects if item["code"] == self.draft["code"])
        self.assertEqual(self.draft["name"], created["name"])
        self.assertEqual(self.draft["contract_value_usd"], created["contract_value_usd"])

    def test_project_manager_can_prepare_project_preview(self):
        response = self.client.post(
            "/api/projects/change-preview?role=project_manager", json=self.draft
        )
        self.assertEqual(202, response.status_code)
        self.assertEqual("pending", response.json()["status"])

    def test_planning_engineer_cannot_create_project_preview(self):
        response = self.client.post(
            "/api/projects/change-preview?role=planning_engineer", json=self.draft
        )
        self.assertEqual(403, response.status_code)

    def test_project_manager_can_update_existing_project_immediately(self):
        existing = self.repository.list_projects(user_role="admin")[0]
        payload = {
            field: existing[field]
            for field in (
                "name", "status", "client", "location", "contract_value_usd",
                "planned_start", "planned_finish", "revised_finish", "reporting_date",
                "baseline_progress", "revised_progress", "actual_progress",
            )
        }
        payload["name"] = "Updated project name"
        response = self.client.patch(
            f"/api/projects/{existing['code']}?role=project_manager", json=payload
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("Updated project name", response.json()["name"])
        with closing(self.repository.connect()) as db:
            audit = db.execute(
                """SELECT * FROM audit_events WHERE action='project_update'
                   AND target_id=?""",
                (existing["code"],),
            ).fetchone()
        self.assertIsNotNone(audit)
        self.assertEqual(existing["name"], json.loads(audit["before_json"])["name"])
        self.assertEqual("Updated project name", json.loads(audit["after_json"])["name"])

    def test_planning_engineer_can_update_but_cannot_change_code(self):
        existing = self.repository.list_projects(user_role="admin")[0]
        payload = {
            field: existing[field]
            for field in (
                "name", "status", "client", "location", "contract_value_usd",
                "planned_start", "planned_finish", "revised_finish", "reporting_date",
                "baseline_progress", "revised_progress", "actual_progress",
            )
        }
        payload["actual_progress"] = 42
        response = self.client.patch(
            f"/api/projects/{existing['code']}?role=planning_engineer", json=payload
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual(100 if existing['status']=='completed' else 0 if existing['status']=='future' else 42, response.json()["actual_progress"])
        payload["code"] = "CHANGED-CODE"
        rejected = self.client.patch(
            f"/api/projects/{existing['code']}?role=planning_engineer", json=payload
        )
        self.assertEqual(422, rejected.status_code)
        self.assertIsNone(self.repository.find_project("CHANGED-CODE", "admin"))

    def test_project_update_rejects_invalid_schedule_without_mutation(self):
        existing = self.repository.list_projects(user_role="admin")[0]
        payload = {
            field: existing[field]
            for field in (
                "name", "status", "client", "location", "contract_value_usd",
                "planned_start", "planned_finish", "revised_finish", "reporting_date",
                "baseline_progress", "revised_progress", "actual_progress",
            )
        }
        payload["planned_finish"] = "2000-01-01"
        response = self.client.patch(
            f"/api/projects/{existing['code']}?role=admin", json=payload
        )
        self.assertEqual(422, response.status_code)
        unchanged = self.repository.find_project(existing["code"], "admin")
        self.assertEqual(existing["planned_finish"], unchanged["planned_finish"])

    def test_canonical_workbook_autofills_editable_project_preview(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Projects"
        sheet.append([
            "code", "name", "status", "client", "location", "contract_value_usd",
            "planned_start", "planned_finish", "revised_finish", "reporting_date",
            "baseline_progress", "revised_progress", "actual_progress",
        ])
        sheet.append(list(self.draft.values()))
        stream = BytesIO()
        workbook.save(stream)
        response = self.client.post(
            "/api/projects/import-preview",
            data={"role": "admin"},
            files={"file": ("new-project.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        self.assertEqual(202, response.status_code)
        change = response.json()
        self.assertEqual(self.draft["code"], change["payload"]["projects"][0]["code"])

        revised = {**self.draft, "name": "Edited Solar Campus"}
        updated = self.client.patch(
            f"/api/change-requests/{change['id']}?role=admin", json=revised
        )
        self.assertEqual(200, updated.status_code)
        self.assertEqual(
            "Edited Solar Campus", updated.json()["payload"]["projects"][0]["name"]
        )


if __name__ == "__main__":
    unittest.main()

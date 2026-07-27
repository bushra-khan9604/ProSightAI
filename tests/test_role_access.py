"""Transport-level tests for the portfolio role permission matrix."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from prosight.api import create_app
from prosight.repository import DEFAULT_DATA, ProjectRepository


class FakeIngestion:
    """Small ingestion boundary used to test authorization without OpenAI."""

    def submit(self, source, original_name, project_code, actor_role):
        return {
            "document": {
                "id": "document-1",
                "project_code": project_code,
                "uploaded_by": actor_role,
            },
            "job": {"id": "job-1", "status": "queued", "progress": 0},
        }

    def confirm_pdf_date(self, job_id, reporting_date, role):
        return {
            "id": job_id,
            "status": "processing",
            "reporting_date": reporting_date,
            "confirmed_by": role,
        }

    def delete_document(self, document_id, role):
        return {"id": document_id, "deleted_by": role}

    def close(self):
        return None


class RoleAccessTests(unittest.TestCase):
    """Verify recognized roles receive only their approved capabilities."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = ProjectRepository(Path(self.temporary.name) / "roles.db")
        self.repository.initialize(DEFAULT_DATA)
        with patch("prosight.api.RAGStore", side_effect=RuntimeError("offline")):
            self.app = create_app(self.repository)
        self.app.state.runtime.ingestion = FakeIngestion()
        self.client = TestClient(self.app)

    def tearDown(self):
        self.temporary.cleanup()

    def test_only_three_application_roles_are_accepted(self):
        for role in ("project_manager", "planning_engineer", "admin"):
            response = self.client.get(f"/api/projects?role={role}")
            self.assertEqual(200, response.status_code)
        for removed in ("employee", "executive", "bid_team"):
            response = self.client.get(f"/api/projects?role={removed}")
            self.assertEqual(400, response.status_code)

    def test_removed_role_is_rejected_by_query_endpoint(self):
        response = self.client.post(
            "/api/query",
            json={"query": "List active projects", "user_role": "executive"},
        )
        self.assertEqual(400, response.status_code)

    def test_planning_engineer_can_upload_pdf_and_xlsx(self):
        for filename, content_type, content in (
            ("report.pdf", "application/pdf", b"%PDF-test"),
            (
                "update.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                b"PK-test",
            ),
        ):
            response = self.client.post(
                "/api/uploads",
                data={
                    "project_code": "PRJ-2024-001",
                    "user_role": "planning_engineer",
                },
                files={"file": (filename, content, content_type)},
            )
            self.assertEqual(202, response.status_code)

    def test_planning_engineer_can_view_previews_but_not_edit_them(self):
        change = self.repository.create_change_request(
            "excel_import",
            "PRJ-2027-010",
            {"projects": []},
            {"before": None, "after": None},
            "project_manager",
        )
        viewed = self.client.get(
            f"/api/change-requests/{change['id']}?role=planning_engineer"
        )
        self.assertEqual(200, viewed.status_code)
        denied = self.client.patch(
            f"/api/change-requests/{change['id']}?role=planning_engineer",
            json={
                "code": "PRJ-2027-010",
                "name": "Test Project",
                "status": "future",
                "client": "Test Client",
                "location": "Dubai",
                "contract_value_usd": 1,
                "planned_start": "2027-01-01",
                "planned_finish": "2027-12-31",
                "revised_finish": "2027-12-31",
                "reporting_date": "2026-07-27",
                "baseline_progress": 0,
                "revised_progress": 0,
                "actual_progress": 0,
            },
        )
        self.assertEqual(403, denied.status_code)

    def test_only_admin_can_decide_changes_or_delete_documents(self):
        for role in ("planning_engineer", "project_manager"):
            change = self.repository.create_change_request(
                "contact_update",
                "PRJ-2024-001",
                {"project_role": "Planning Engineer"},
                {"before": None, "after": {}},
                role,
            )
            decision = self.client.post(
                f"/api/change-requests/{change['id']}/reject?role={role}"
            )
            deletion = self.client.delete(
                f"/api/documents/document-1?role={role}"
            )
            self.assertEqual(403, decision.status_code)
            self.assertEqual(403, deletion.status_code)

        change = self.repository.create_change_request(
            "contact_update",
            "PRJ-2024-001",
            {"project_role": "Planning Engineer"},
            {"before": None, "after": {}},
            "project_manager",
        )
        self.assertEqual(
            200,
            self.client.post(
                f"/api/change-requests/{change['id']}/reject?role=admin"
            ).status_code,
        )
        self.assertEqual(
            200,
            self.client.delete("/api/documents/document-1?role=admin").status_code,
        )


if __name__ == "__main__":
    unittest.main()

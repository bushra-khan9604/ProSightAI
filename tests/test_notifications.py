"""Persistent role notifications and the server-backed approval queue."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from prosight.api import create_app
from prosight.repository import DEFAULT_DATA, ProjectRepository


class NotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = ProjectRepository(Path(self.temporary.name) / "notifications.db")
        self.repository.initialize(DEFAULT_DATA)
        with patch("prosight.api.RAGStore", side_effect=RuntimeError("offline")):
            self.app = create_app(self.repository)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.client.close()
        self.temporary.cleanup()

    def create_pending(self, requested_by: str = "project_manager") -> dict:
        return self.repository.create_change_request(
            "contact_update",
            "PRJ-2024-001",
            {"project_role": "Planning Engineer", "mobile": "+971-50-111-2222"},
            {"before": None, "after": {"mobile": "+971-50-111-2222"}},
            requested_by,
        )

    def test_pending_request_is_persistent_and_visible_to_admin(self):
        change = self.create_pending()
        response = self.client.get("/api/approvals?role=admin&status=pending")
        self.assertEqual(200, response.status_code)
        self.assertEqual(change["id"], response.json()["items"][0]["id"])
        notifications = self.client.get("/api/notifications?role=admin&status=unread").json()
        self.assertEqual(1, notifications["unread_count"])
        self.assertEqual(change["id"], notifications["items"][0]["change_request_id"])

    def test_decision_resolves_admin_notice_and_notifies_requesting_role(self):
        change = self.create_pending("planning_engineer")
        response = self.client.post(
            f"/api/change-requests/{change['id']}/approve?role=admin"
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual([], self.client.get("/api/approvals?role=admin").json()["items"])
        self.assertEqual(
            0,
            self.client.get("/api/notifications?role=admin&status=unread").json()[
                "unread_count"
            ],
        )
        result = self.client.get(
            "/api/notifications?role=planning_engineer&status=unread"
        ).json()
        self.assertEqual("change_approved", result["items"][0]["event_type"])

    def test_role_cannot_read_another_roles_notification(self):
        self.create_pending()
        notification = self.client.get(
            "/api/notifications?role=admin&status=unread"
        ).json()["items"][0]
        response = self.client.post(
            f"/api/notifications/{notification['id']}/read?role=project_manager"
        )
        self.assertEqual(404, response.status_code)

    def test_opened_result_is_removed_from_unread_activity(self):
        change = self.create_pending()
        self.repository.decide_change_request(change["id"], "approved", "admin")
        result = self.client.get(
            "/api/notifications?role=project_manager&status=unread"
        ).json()["items"][0]
        self.client.post(
            f"/api/notifications/{result['id']}/read?role=project_manager"
        )
        activity = self.client.get(
            "/api/notifications?role=project_manager&status=unread"
        ).json()
        self.assertEqual([], activity["items"])

    def test_admin_self_approval_does_not_create_result_activity(self):
        change = self.create_pending("admin")
        self.repository.decide_change_request(change["id"], "approved", "admin")
        activity = self.client.get(
            "/api/notifications?role=admin&status=unread"
        ).json()
        self.assertEqual([], activity["items"])

    def test_non_admin_cannot_access_approval_queue(self):
        self.create_pending()
        response = self.client.get("/api/approvals?role=project_manager")
        self.assertEqual(403, response.status_code)


if __name__ == "__main__":
    unittest.main()

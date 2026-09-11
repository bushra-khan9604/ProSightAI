import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from prosight.api import create_app
from prosight.auth import AuthContext


class _Repository:
    def _ensure(self):
        return None


class _Verifier:
    def verify(self, authorization):
        if authorization != "Bearer valid-test-token":
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        return AuthContext(
            user_id="00000000-0000-0000-0000-000000000001",
            email="employee@example.test",
            display_name="Test Employee",
            role="employee",
            project_codes=("PRJ-2024-001",),
            access_token="valid-test-token",
        )


class SupabaseAuthApiTests(unittest.TestCase):
    def setUp(self):
        environment = {
            "PROSIGHT_DATA_BACKEND": "supabase",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "publishable-test-key",
            "SUPABASE_SERVICE_ROLE_KEY": "service-test-key",
        }
        patches = (
            patch.dict("os.environ", environment),
            patch("prosight.api.SupabaseProjectRepository", return_value=_Repository()),
            patch("prosight.api.SupabaseAuthVerifier", return_value=_Verifier()),
            patch("prosight.api.RAGStore", side_effect=RuntimeError("offline")),
        )
        self.cleanups = [item.start() for item in patches]
        for item in reversed(patches):
            self.addCleanup(item.stop)
        self.client = TestClient(create_app())

    def test_health_is_public_but_me_requires_a_session(self):
        self.assertEqual(200, self.client.get("/api/health").status_code)
        self.assertEqual(401, self.client.get("/api/me").status_code)

    def test_me_returns_verified_identity_and_memberships(self):
        response = self.client.get(
            "/api/me", headers={"Authorization": "Bearer valid-test-token"}
        )
        self.assertEqual(200, response.status_code)
        self.assertEqual("employee", response.json()["role"])
        self.assertEqual(["PRJ-2024-001"], response.json()["project_codes"])

    def test_invalid_token_is_rejected(self):
        response = self.client.get(
            "/api/me", headers={"Authorization": "Bearer expired"}
        )
        self.assertEqual(401, response.status_code)

    def test_query_rejects_role_spoofing_even_with_valid_session(self):
        response = self.client.post(
            "/api/query",
            headers={"Authorization": "Bearer valid-test-token"},
            json={"query": "List projects", "user_role": "admin"},
        )
        self.assertEqual(422, response.status_code)

    def test_cross_project_query_is_forbidden_before_retrieval(self):
        response = self.client.post(
            "/api/query",
            headers={"Authorization": "Bearer valid-test-token"},
            json={"query": "Show status", "project_code": "PRJ-OTHER"},
        )
        self.assertEqual(403, response.status_code)

    def test_openapi_exposes_no_client_role_fields(self):
        schema = self.client.get("/openapi.json").json()
        for operations in schema["paths"].values():
            for operation in operations.values():
                names = {item["name"] for item in operation.get("parameters", [])}
                self.assertNotIn("role", names)
                self.assertNotIn("user_role", names)


if __name__ == "__main__":
    unittest.main()

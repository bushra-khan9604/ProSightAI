"""Offline tests for legacy/compare/redesigned runtime selection and auth scope."""

from __future__ import annotations

import unittest
import uuid
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

from fastapi.testclient import TestClient

from prosight.redesign_runtime import (
    AuthenticatedScope,
    AuthorizationScopeResolver,
    ORGANIZATION_SCOPE_SQL,
    PROJECT_SCOPE_SQL,
    ThreeLayerRuntime,
)
from prosight.ingestion.publication import PublicationRequest
from prosight.repository import ProjectRepository


class TransitionRuntimeTests(unittest.TestCase):
    def test_project_import_analysis_distinguishes_creates_and_updates(self):
        with patch.dict(os.environ, {
            "PROSIGHT_SCHEMA_MODE": "legacy", "PROSIGHT_DATABASE_BACKEND": "sqlite",
            "PROSIGHT_AUTH_PROVIDER": "local", "PROSIGHT_AI_PROVIDER": "local",
        }):
            from prosight.api import _project_import_analysis
        result = _project_import_analysis([
            SimpleNamespace(entity_type="projects", values={"code": "P-001"}),
            SimpleNamespace(entity_type="projects", values={"code": "P-002"}),
            SimpleNamespace(entity_type="risks", values={"code": "R-1"}),
        ], [{"code": "p-001"}])

        self.assertEqual(2, result["project_row_count"])
        self.assertEqual(["P-002"], result["create_codes"])
        self.assertEqual(["P-001"], result["update_codes"])
        self.assertEqual("create_and_update_projects", result["suggested_action"])

    def test_first_upload_can_create_the_default_project_mapping(self):
        scope = AuthenticatedScope(
            str(uuid.uuid4()), str(uuid.uuid4()), (), "manager"
        )
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        runtime.mapping_profiles = Mock(return_value=[])
        runtime.register_mapping = Mock()

        record = runtime.ensure_default_project_mapping(scope)

        self.assertEqual("projects", record.mapping.sheets[0].entity_type)
        self.assertEqual(scope.organization_id, record.mapping.organization_id)
        self.assertEqual(1, record.mapping.catalog_version)
        runtime.register_mapping.assert_called_once_with(record, scope)

    def test_first_mapping_requires_an_organization_manager(self):
        scope = AuthenticatedScope(
            str(uuid.uuid4()), str(uuid.uuid4()), (), "member"
        )
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        runtime.mapping_profiles = Mock(return_value=[])
        runtime.register_mapping = Mock()

        with self.assertRaisesRegex(PermissionError, "owner, admin, or manager"):
            runtime.ensure_default_project_mapping(scope)

        runtime.register_mapping.assert_not_called()

    def test_runtime_activation_checks_redesign_without_initializing_legacy(self):
        repository = Mock(backend="postgres")
        repository._ensure.side_effect = AssertionError("legacy schema must not initialize")
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        with patch.dict(os.environ, {
            "PROSIGHT_SCHEMA_MODE": "redesigned",
            "PROSIGHT_AUTH_PROVIDER": "supabase",
            "PROSIGHT_AI_PROVIDER": "local",
        }):
            from prosight.api import Runtime
            activated = Runtime(repository, three_layer=runtime)
        self.assertIs(activated.three_layer, runtime)
        repository.ensure_redesign_schema.assert_called_once_with()
        repository._ensure.assert_not_called()

    def test_legacy_is_safe_default_and_does_not_instantiate_new_adapters(self):
        runtime = ThreeLayerRuntime(mode="legacy")
        self.assertEqual("legacy", runtime.mode)
        self.assertTrue(runtime.legacy_rollback_available)
        self.assertIsNone(runtime.authenticated_connection_factory)
        with self.assertRaisesRegex(RuntimeError, "legacy mode"):
            runtime.resolve_scope(uuid.uuid4())

    def test_scope_is_derived_from_authenticated_memberships(self):
        user_id, organization_id = str(uuid.uuid4()), str(uuid.uuid4())
        project_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        organization_cursor = Mock()
        organization_cursor.fetchall.return_value = [{"organization_id": organization_id}]
        project_cursor = Mock()
        project_cursor.fetchall.return_value = [{"id": value} for value in project_ids]
        connection = MagicMock()
        connection.execute_native.side_effect = [organization_cursor, project_cursor]
        connection_factory = Mock(return_value=connection)
        resolver = AuthorizationScopeResolver(connection_factory)
        scope = resolver.resolve(uuid.UUID(user_id))
        self.assertEqual(organization_id, scope.organization_id)
        self.assertEqual(tuple(project_ids), scope.allowed_project_ids)
        self.assertEqual(user_id, connection.execute_native.call_args_list[0].args[1]["user_id"])
        connection_factory.assert_called_once_with(uuid.UUID(user_id))
        self.assertNotIn("prosight.", ORGANIZATION_SCOPE_SQL + PROJECT_SCOPE_SQL)
        self.assertIn("construction.organization_members", ORGANIZATION_SCOPE_SQL)
        self.assertIn("construction.project_members", PROJECT_SCOPE_SQL)

    def test_redesigned_routes_only_to_new_services_with_exact_scope(self):
        legacy_facts, legacy_search = Mock(), Mock()
        authenticated_factory = Mock()
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=authenticated_factory,
            embedder=Mock(), projection_version=1,
            chunking_version="pdf-heading-pages-v1", legacy_fact_query=legacy_facts,
            legacy_semantic_search=legacy_search,
        )
        scope = AuthenticatedScope(
            str(uuid.uuid4()), str(uuid.uuid4()), (str(uuid.uuid4()), str(uuid.uuid4()))
        )
        facts_service = Mock()
        facts_service.query.return_value = [{"id": "new"}]
        search_service = Mock()
        search_service.search.return_value = [{"id": "chunk"}]
        with patch("prosight.redesign_runtime.ConstructionFacts", return_value=facts_service), \
             patch("prosight.redesign_runtime.SemanticSearch", return_value=search_service):
            facts = runtime.structured_facts("risks", scope)
            search = runtime.search("delay", scope, 7)
        facts_service.query.assert_called_once_with(
            "risks", scope.organization_id, list(scope.allowed_project_ids)
        )
        search_service.search.assert_called_once_with(
            "delay", scope.organization_id, list(scope.allowed_project_ids), 7
        )
        legacy_facts.assert_not_called()
        legacy_search.assert_not_called()
        self.assertEqual([{"id": "new"}], facts["results"])
        self.assertEqual([{"id": "chunk"}], search["results"])
        self.assertFalse(runtime.legacy_rollback_available)

    def test_compare_instantiates_all_new_adapters_and_retains_legacy_comparison(self):
        legacy_facts = Mock(return_value=[{"id": "legacy"}])
        legacy_search = Mock(return_value=[{"id": "legacy-chunk"}])
        runtime = ThreeLayerRuntime(
            mode="compare",
            authenticated_connection_factory=Mock(),
            embedder=Mock(),
            legacy_fact_query=legacy_facts,
            legacy_semantic_search=legacy_search,
        )
        self.assertIsNotNone(runtime.authenticated_connection_factory)
        scope = AuthenticatedScope(str(uuid.uuid4()), str(uuid.uuid4()), (str(uuid.uuid4()),))
        facts_service = Mock(); facts_service.query.return_value = []
        search_service = Mock(); search_service.search.return_value = []
        publication_service = Mock(); publication_service.publish.return_value = {"status": "published"}
        index_service = Mock(); index_service.upsert.return_value = 1
        publication = PublicationRequest(str(uuid.uuid4()), str(uuid.uuid4()), "idempotent")
        chunks = [{"id": str(uuid.uuid4())}]
        job_id = str(uuid.uuid4())
        with patch("prosight.redesign_runtime.ConstructionFacts", return_value=facts_service), \
             patch("prosight.redesign_runtime.SemanticSearch", return_value=search_service), \
             patch("prosight.redesign_runtime.AtomicPublicationAdapter", return_value=publication_service), \
             patch("prosight.redesign_runtime.SemanticIndexAdapter", return_value=index_service):
            self.assertEqual([{"id": "legacy"}], runtime.structured_facts("claims", scope)["legacy_comparison"])
            self.assertEqual([{"id": "legacy-chunk"}], runtime.search("claim", scope)["legacy_comparison"])
            self.assertEqual("published", runtime.publish(publication, scope)["status"])
            self.assertEqual(1, runtime.index(chunks, embedding_job_id=job_id, scope=scope))
        publication_service.publish.assert_called_once_with(publication)
        index_service.upsert.assert_called_once_with(chunks, embedding_job_id=job_id)
        self.assertTrue(runtime.legacy_rollback_available)

    def test_api_reaches_redesigned_services_without_client_project_scope(self):
        scope = AuthenticatedScope(str(uuid.uuid4()), str(uuid.uuid4()), (str(uuid.uuid4()),))
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        runtime.resolve_scope = Mock(return_value=scope)
        runtime.structured_facts = Mock(return_value={"mode": "redesigned", "results": []})
        runtime.search = Mock(return_value={"mode": "redesigned", "results": []})
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "api.db")
            repository._ensure = Mock(side_effect=AssertionError("legacy schema must not initialize"))
            verified_user = {
                "id": scope.user_id, "role": "admin", "username": "reviewer"
            }
            repository.get_session_user = Mock(
                side_effect=AssertionError("redesigned mode must not query legacy sessions")
            )
            repository.revoke_session = Mock(
                side_effect=AssertionError("redesigned mode must not mutate legacy sessions")
            )
            repository.record_auth_event = Mock(
                side_effect=AssertionError("redesigned mode must not write legacy auth events")
            )
            with patch.dict(os.environ, {
                "PROSIGHT_AUTH_PROVIDER": "supabase",
                "PROSIGHT_AUTH_REQUIRED": "1",
                "PROSIGHT_SCHEMA_MODE": "legacy",
                "PROSIGHT_AI_PROVIDER": "local",
                "PROSIGHT_DATABASE_BACKEND": "sqlite",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            }), patch("prosight.api.RAGStore", side_effect=RuntimeError("offline")), \
                 patch("prosight.api.get_supabase_user", new=AsyncMock(return_value=verified_user)):
                from prosight.api import create_app
                with TestClient(create_app(repository, three_layer=runtime)) as client:
                    headers = {"Authorization": "Bearer verified"}
                    facts = client.post("/api/three-layer/facts", json={"fact": "risks"}, headers=headers)
                    search = client.post(
                        "/api/three-layer/search", json={"query": "delay", "limit": 4},
                        headers=headers,
                    )
                    legacy = client.get("/api/projects", headers=headers)
            self.assertEqual(200, facts.status_code)
            self.assertEqual(200, search.status_code)
            self.assertEqual(409, legacy.status_code)
            self.assertIn("Legacy API paths are disabled", legacy.json()["detail"])
            runtime.resolve_scope.assert_has_calls([
                call(uuid.UUID(scope.user_id), None),
                call(uuid.UUID(scope.user_id), None),
            ])
            runtime.structured_facts.assert_called_once_with("risks", scope)
            runtime.search.assert_called_once_with("delay", scope, 4)
            repository._ensure.assert_not_called()
            repository.get_session_user.assert_not_called()

    def test_api_invalid_session_identity_fails_closed_before_scope_query(self):
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "api.db")
            invalid_user = {
                "id": "not-a-uuid", "role": "admin", "username": "reviewer"
            }
            repository.get_session_user = Mock(
                side_effect=AssertionError("redesigned mode must not query legacy sessions")
            )
            repository.revoke_session = Mock(
                side_effect=AssertionError("redesigned mode must not mutate legacy sessions")
            )
            repository.record_auth_event = Mock(
                side_effect=AssertionError("redesigned mode must not write legacy auth events")
            )
            with patch.dict(os.environ, {
                "PROSIGHT_AUTH_PROVIDER": "supabase", "PROSIGHT_AUTH_REQUIRED": "1",
                "PROSIGHT_SCHEMA_MODE": "legacy",
                "PROSIGHT_AI_PROVIDER": "local", "PROSIGHT_DATABASE_BACKEND": "sqlite",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            }), patch("prosight.api.get_supabase_user", new=AsyncMock(return_value=invalid_user)):
                from prosight.api import create_app
                with TestClient(create_app(repository, three_layer=runtime)) as client:
                    response = client.post(
                        "/api/three-layer/facts",
                        json={"fact": "risks"},
                        headers={"Authorization": "Bearer invalid"},
                    )
        self.assertEqual(401, response.status_code)
        runtime.scope_resolver.connection_factory.assert_not_called()
        repository.get_session_user.assert_not_called()

    def test_api_exposes_catalog_profiles_and_projects_without_legacy_access(self):
        scope = AuthenticatedScope(
            str(uuid.uuid4()), str(uuid.uuid4()), (str(uuid.uuid4()),), "admin"
        )
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        runtime.resolve_scope = Mock(return_value=scope)
        runtime.mapping_profiles = Mock(return_value=[])
        runtime.projects = Mock(return_value=[{"id": scope.allowed_project_ids[0], "code": "P-1"}])
        runtime.register_mapping = Mock()
        verified_user = {"id": scope.user_id, "role": "admin", "username": "reviewer"}
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "api.db")
            repository.get_session_user = Mock(
                side_effect=AssertionError("redesigned mode must not query legacy sessions")
            )
            with patch.dict(os.environ, {
                "PROSIGHT_AUTH_PROVIDER": "supabase", "PROSIGHT_AUTH_REQUIRED": "1",
                "PROSIGHT_SCHEMA_MODE": "legacy", "PROSIGHT_AI_PROVIDER": "local",
                "PROSIGHT_DATABASE_BACKEND": "sqlite",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            }), patch("prosight.api.get_supabase_user", new=AsyncMock(return_value=verified_user)):
                from prosight.api import create_app
                headers = {"Authorization": "Bearer verified"}
                with TestClient(create_app(repository, three_layer=runtime)) as client:
                    catalog = client.get("/api/three-layer/catalog", headers=headers)
                    mappings = client.get(
                        "/api/three-layer/mappings?entity_type=projects", headers=headers
                    )
                    projects = client.get("/api/three-layer/projects", headers=headers)
                    unsafe = client.post("/api/three-layer/mappings", headers=headers, json={
                        "mapping_profile_id": str(uuid.uuid4()),
                        "mapping_version_id": str(uuid.uuid4()),
                        "version_no": 1, "catalog_version": 1, "name": "Unsafe",
                        "sheets": [{"entity_type": "projects", "sheet_name": "Projects",
                                    "columns": {"code": "Code", "name": "Name",
                                                "organization_id": "Organization"}}],
                    })
        self.assertEqual(200, catalog.status_code)
        self.assertEqual(9, len(catalog.json()["catalog"]["entities"]))
        self.assertEqual("admin", catalog.json()["organization_role"])
        self.assertEqual([], mappings.json()["items"])
        self.assertEqual("P-1", projects.json()[0]["code"])
        self.assertEqual(400, unsafe.status_code)
        self.assertIn("not an organization-configurable", unsafe.json()["detail"])
        runtime.register_mapping.assert_not_called()
        repository.get_session_user.assert_not_called()

    def test_prepare_returns_json_when_default_mapping_creation_crashes(self):
        scope = AuthenticatedScope(
            str(uuid.uuid4()), str(uuid.uuid4()), (), "admin"
        )
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        runtime.resolve_scope = Mock(return_value=scope)
        runtime.ensure_default_project_mapping = Mock(
            side_effect=NameError("unexpected mapping bootstrap failure")
        )
        verified_user = {"id": scope.user_id, "role": "admin", "username": "reviewer"}
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "api.db")
            with patch.dict(os.environ, {
                "PROSIGHT_AUTH_PROVIDER": "supabase", "PROSIGHT_AUTH_REQUIRED": "1",
                "PROSIGHT_SCHEMA_MODE": "legacy", "PROSIGHT_AI_PROVIDER": "local",
                "PROSIGHT_DATABASE_BACKEND": "sqlite",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            }), patch("prosight.api.get_supabase_user", new=AsyncMock(return_value=verified_user)):
                from prosight.api import create_app
                with TestClient(create_app(repository, three_layer=runtime)) as client:
                    response = client.post(
                        "/api/three-layer/imports/prepare",
                        headers={"Authorization": "Bearer verified"},
                        files={"file": (
                            "projects.xlsx",
                            b"not-read-before-mapping-bootstrap",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )},
                    )

        self.assertEqual(500, response.status_code)
        self.assertEqual(
            "The server could not process this workbook. Please retry or contact support.",
            response.json()["detail"],
        )

    def test_api_exposes_membership_scoped_governed_lifecycle(self):
        scope = AuthenticatedScope(
            str(uuid.uuid4()), str(uuid.uuid4()), (str(uuid.uuid4()),)
        )
        batch_id, approval_id = str(uuid.uuid4()), str(uuid.uuid4())
        runtime = ThreeLayerRuntime(
            mode="redesigned", authenticated_connection_factory=Mock(), embedder=Mock()
        )
        runtime.resolve_scope = Mock(return_value=scope)
        runtime.submit_import = Mock()
        runtime.decide_import = Mock(return_value=SimpleNamespace(
            id=approval_id,
            batch_id=batch_id,
            decision="approved",
            validation_checksum="a" * 64,
            normalized_preview_checksum="b" * 64,
        ))
        runtime.publish_import = Mock(return_value={"status": "published"})
        verified_user = {"id": scope.user_id, "role": "admin", "username": "reviewer"}
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "api.db")
            repository.get_session_user = Mock(
                side_effect=AssertionError("redesigned mode must not query legacy sessions")
            )
            repository.revoke_session = Mock(
                side_effect=AssertionError("redesigned mode must not mutate legacy sessions")
            )
            repository.record_auth_event = Mock(
                side_effect=AssertionError("redesigned mode must not write legacy auth events")
            )
            with patch.dict(os.environ, {
                "PROSIGHT_AUTH_PROVIDER": "supabase",
                "PROSIGHT_AUTH_REQUIRED": "1",
                "PROSIGHT_SCHEMA_MODE": "legacy",
                "PROSIGHT_AI_PROVIDER": "local",
                "PROSIGHT_DATABASE_BACKEND": "sqlite",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
            }), patch(
                "prosight.api.get_supabase_user",
                new=AsyncMock(return_value=verified_user),
            ):
                from prosight.api import create_app
                headers = {"Authorization": "Bearer verified"}
                with TestClient(create_app(repository, three_layer=runtime)) as client:
                    submitted = client.post(
                        f"/api/three-layer/imports/{batch_id}/submit",
                        json={}, headers=headers,
                    )
                    decided = client.post(
                        f"/api/three-layer/imports/{batch_id}/decision",
                        json={"decision": "approved"}, headers=headers,
                    )
                    published = client.post(
                        f"/api/three-layer/imports/{batch_id}/publish",
                        json={}, headers=headers,
                    )
                    logged_out = client.post("/api/auth/logout", headers=headers)
        self.assertEqual(200, submitted.status_code)
        self.assertEqual(200, decided.status_code)
        self.assertEqual(200, published.status_code)
        self.assertEqual(200, logged_out.status_code)
        runtime.resolve_scope.assert_has_calls([
            call(uuid.UUID(scope.user_id), None),
            call(uuid.UUID(scope.user_id), None),
            call(uuid.UUID(scope.user_id), None),
        ])
        runtime.submit_import.assert_called_once_with(batch_id, scope)
        runtime.decide_import.assert_called_once_with(
            batch_id, scope, decision="approved", reason=None
        )
        runtime.publish_import.assert_called_once_with(batch_id, scope)
        repository.get_session_user.assert_not_called()
        repository.revoke_session.assert_not_called()
        repository.record_auth_event.assert_not_called()


if __name__ == "__main__":
    unittest.main()

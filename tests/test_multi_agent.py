"""Multi-agent routing, isolation, and approval workflow tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from prosight.agents.database_manager import DatabaseManagerAgent
from prosight.agents.orchestrator import MultiAgentOrchestrator
from prosight.config import get_settings
from prosight.contracts import ChangeOperation, EvidenceItem, RAGEvidence
from prosight.observability import RequestTrace
from prosight.repository import DEFAULT_DATA, ProjectRepository


class FakeRAGAgent:
    """Test double that proves the orchestrator passes project scope."""

    def retrieve(self, query: str, project_code: str) -> RAGEvidence:
        return RAGEvidence(
            query=query,
            project_code=project_code,
            evidence=[
                EvidenceItem(
                    text="The report records facade installation on zones 5–7.",
                    citation="Monthly Report.pdf, page 14",
                )
            ],
        )


class MultiAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repository = ProjectRepository(Path(self.temp.name) / "test.db")
        self.repository.initialize(DEFAULT_DATA)
        self.orchestrator = MultiAgentOrchestrator(self.repository, FakeRAGAgent())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_routes_database_only_query(self):
        plan = self.orchestrator.plan("Show project progress", "PRJ-2024-001")
        self.assertEqual(["database_manager", "writer"], plan.agents)

    def test_routes_rag_only_query(self):
        plan = self.orchestrator.plan("What does the PDF report say?", "PRJ-2024-001")
        self.assertEqual(["rag", "writer"], plan.agents)

    def test_routes_combined_query(self):
        plan = self.orchestrator.plan(
            "Compare project progress with the monthly report", "PRJ-2024-001"
        )
        self.assertEqual(["database_manager", "rag", "writer"], plan.agents)

    def test_write_query_requires_approval(self):
        plan = self.orchestrator.plan("Delete project PRJ-2024-001", "PRJ-2024-001")
        self.assertTrue(plan.requires_write_approval)

    def test_local_combined_run_has_citations_and_route(self):
        result = self.orchestrator.run(
            "Compare project progress with the monthly report",
            "project_manager",
            "PRJ-2024-001",
            RequestTrace(),
        )
        self.assertIn("database_manager", result["agent_route"])
        self.assertIn("rag", result["agent_route"])
        self.assertIn("writer", result["agent_route"])
        self.assertIn("Monthly Report.pdf, page 14", result["citations"])

    def test_hosted_agents_use_separate_explicit_reasoning_levels(self):
        created_agents = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                created_agents.append(self)

            def as_tool(self, **kwargs):
                return {"agent": self, **kwargs}

        plan = self.orchestrator.plan("Explain project progress", "PRJ-2024-001")
        with (
            patch("agents.Agent", FakeAgent),
            patch("agents.function_tool", side_effect=lambda function: function),
            patch(
                "agents.Runner.run_sync",
                return_value=SimpleNamespace(final_output="Evidence-grounded response"),
            ),
            patch.dict(
                "os.environ",
                {
                    "OPENAI_MODEL": "gpt-5.6-luna",
                    "OPENAI_ORCHESTRATOR_REASONING": "none",
                    "OPENAI_WRITER_REASONING": "low",
                },
                clear=False,
            ),
        ):
            self.orchestrator._run_openai(
                "Explain project progress", "project_manager", "PRJ-2024-001",
                plan, RequestTrace(), [],
            )

        writer, manager = created_agents
        self.assertEqual("gpt-5.6-luna", writer.kwargs["model"])
        self.assertEqual("low", writer.kwargs["model_settings"].reasoning.effort)
        self.assertEqual("gpt-5.6-luna", manager.kwargs["model"])
        self.assertEqual("none", manager.kwargs["model_settings"].reasoning.effort)

    def test_reasoning_configuration_rejects_unknown_effort(self):
        with patch.dict(
            "os.environ", {"OPENAI_WRITER_REASONING": "unsupported"}, clear=False
        ):
            with self.assertRaisesRegex(ValueError, "OPENAI_WRITER_REASONING"):
                get_settings()

    def test_database_manager_creates_pending_change(self):
        evidence = DatabaseManagerAgent(self.repository).propose_change(
            ChangeOperation(
                action="record_delete",
                project_code="PRJ-2024-001",
                payload={},
            ),
            requested_by="project_manager",
        )
        change = self.repository.get_change_request(evidence.change_request_id)
        self.assertEqual("pending", change["status"])

    def test_only_admin_can_approve_and_audit(self):
        change = self.repository.create_change_request(
            "record_delete", "PRJ-2024-001", {},
            {"before": {"code": "PRJ-2024-001"}, "after": None}, "project_manager",
        )
        with self.assertRaises(PermissionError):
            self.repository.decide_change_request(change["id"], "approved", "project_manager")
        decided = self.repository.decide_change_request(change["id"], "approved", "admin")
        self.assertEqual("approved", decided["status"])
        self.assertIsNone(self.repository.find_project("PRJ-2024-001", "admin"))

    def test_approved_contact_update_is_transactional(self):
        change = self.repository.create_change_request(
            "contact_update",
            "PRJ-2024-001",
            {"project_role": "Planning Engineer", "mobile": "+971-50-000-0000"},
            {"before": None, "after": {"mobile": "+971-50-000-0000"}},
            "project_manager",
        )
        self.repository.decide_change_request(change["id"], "approved", "admin")
        project = self.repository.find_project("PRJ-2024-001", "admin")
        planning = next(c for c in project["contacts"] if c["project_role"] == "Planning Engineer")
        self.assertEqual("+971-50-000-0000", planning["mobile"])


if __name__ == "__main__":
    unittest.main()

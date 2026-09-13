"""Multi-agent routing, isolation, and approval workflow tests."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from prosight.agents.database_manager import DatabaseManagerAgent
from prosight.agents.orchestrator import MultiAgentOrchestrator
from prosight.config import get_settings
from prosight.contracts import (
    ChangeOperation, DatabaseEvidence, EvidenceItem, RAGEvidence, WriterInput,
)
from prosight.observability import RequestTrace
from prosight.repository import DEFAULT_DATA, ProjectRepository
from prosight.supabase_gateway import current_access_token


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

    def test_project_scoped_unstructured_question_defaults_to_rag(self):
        plan = self.orchestrator.plan(
            "What fire rating is required for the service corridor?", "PRJ-2024-001"
        )
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

    def test_hosted_pipeline_creates_only_writer_with_configured_reasoning(self):
        created_agents = []

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                created_agents.append(self)

        with (
            patch("agents.Agent", FakeAgent),
            patch(
                "agents.Runner.run",
                new=AsyncMock(
                    return_value=SimpleNamespace(final_output="Evidence-grounded response")
                ),
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
            asyncio.run(self.orchestrator._write_openai(
                WriterInput(query="Explain project progress"), [], [], RequestTrace()
            ))

        self.assertEqual(1, len(created_agents))
        writer = created_agents[0]
        self.assertEqual("gpt-5.6-luna", writer.kwargs["model"])
        self.assertEqual("low", writer.kwargs["model_settings"].reasoning.effort)

    def test_combined_evidence_runs_concurrently_and_keeps_auth_context(self):
        database_started = threading.Event()
        rag_started = threading.Event()
        observed_tokens = []

        class Database:
            def read(self, *_args):
                observed_tokens.append(current_access_token.get())
                database_started.set()
                if not rag_started.wait(1):
                    raise AssertionError("RAG retrieval did not start concurrently")
                return DatabaseEvidence(summary="Database evidence")

        class RAG:
            def retrieve(self, query, project_code):
                observed_tokens.append(current_access_token.get())
                rag_started.set()
                if not database_started.wait(1):
                    raise AssertionError("Database retrieval did not start concurrently")
                return RAGEvidence(query=query, project_code=project_code)

        self.orchestrator.database = Database()
        self.orchestrator.rag = RAG()
        token = current_access_token.set("caller-jwt")
        try:
            with patch.dict("os.environ", {"PROSIGHT_AI_PROVIDER": "local"}):
                result = asyncio.run(self.orchestrator.run_async(
                    "Compare project progress with the monthly report",
                    "project_manager", "PRJ-2024-001", RequestTrace(),
                ))
        finally:
            current_access_token.reset(token)

        self.assertEqual(["caller-jwt", "caller-jwt"], sorted(observed_tokens))
        self.assertEqual(["database_manager", "rag", "writer"], result["agent_route"])

    def test_writer_stream_reconstructs_final_answer_from_text_deltas(self):
        from openai.types.responses import ResponseTextDeltaEvent

        def delta(text, sequence):
            return SimpleNamespace(
                type="raw_response_event",
                data=ResponseTextDeltaEvent(
                    content_index=0, delta=text, item_id="message-1", logprobs=[],
                    output_index=0, sequence_number=sequence,
                    type="response.output_text.delta",
                ),
            )

        class StreamResult:
            final_output = "Grounded response"

            async def stream_events(self):
                yield delta("Grounded ", 1)
                yield delta("response", 2)

            def cancel(self):
                return None

        async def collect():
            with (
                patch.object(self.orchestrator, "_writer_agent", return_value=object()),
                patch("agents.Runner.run_streamed", return_value=StreamResult()),
            ):
                return [event async for event in self.orchestrator._stream_openai_writer(
                    WriterInput(query="Question"), [], [], RequestTrace()
                )]

        events = asyncio.run(collect())
        streamed = "".join(payload["text"] for name, payload in events if name == "delta")
        final = next(payload for name, payload in events if name == "final")
        self.assertEqual("Grounded response", streamed)
        self.assertEqual(streamed, final["answer"])
        self.assertIsInstance(final["time_to_first_token_ms"], int)

    def test_stream_failure_after_delta_keeps_partial_answer_without_fallback(self):
        async def interrupted(*_args):
            yield "delta", {"text": "Partial answer"}
            raise RuntimeError("stream interrupted")

        self.orchestrator._stream_openai_writer = interrupted

        async def collect():
            with patch.dict("os.environ", {
                "PROSIGHT_AI_PROVIDER": "openai", "OPENAI_API_KEY": "test-key",
            }):
                return [event async for event in self.orchestrator.stream(
                    "hello", "project_manager", None, RequestTrace()
                )]

        events = asyncio.run(collect())
        self.assertEqual("Partial answer", next(
            payload["text"] for name, payload in events if name == "delta"
        ))
        error = next(payload for name, payload in events if name == "error")
        self.assertTrue(error["partial"])
        self.assertFalse(any(name == "final" for name, _ in events))

    def test_stream_failure_before_delta_uses_grounded_local_fallback(self):
        async def unavailable(*_args):
            if False:
                yield "delta", {"text": ""}
            raise RuntimeError("provider unavailable")

        self.orchestrator._stream_openai_writer = unavailable

        async def collect():
            with patch.dict("os.environ", {
                "PROSIGHT_AI_PROVIDER": "openai", "OPENAI_API_KEY": "test-key",
            }):
                return [event async for event in self.orchestrator.stream(
                    "Show project progress", "project_manager", "PRJ-2024-001",
                    RequestTrace(),
                )]

        events = asyncio.run(collect())
        final = next(payload for name, payload in events if name == "final")
        streamed = "".join(payload["text"] for name, payload in events if name == "delta")
        self.assertEqual(final["answer"], streamed)
        self.assertEqual("local", final["mode"])
        self.assertIn("deterministic evidence response", final["notice"])

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

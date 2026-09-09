"""Regression tests for evidence visibility, retrieval ranking, and agent scope."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from prosight.agents.database_manager import DatabaseManagerAgent
from prosight.agents.rag_agent import RAGAgent
from prosight.contracts import ChangeOperation, EvidenceItem, RAGEvidence
from prosight.rag.store import RAGStore


class DatabaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.repository = Mock()
        self.repository.find_project.return_value = {"code": "P1"}
        self.agent = DatabaseManagerAgent(self.repository)

    def test_unknown_role_cannot_read(self):
        with self.assertRaises(PermissionError):
            self.agent.read("invoices", "P1", "owner")
        self.repository.list_invoices.assert_not_called()

    def test_partial_project_reference_cannot_expand_scope(self):
        self.assertEqual([], self.agent.read("invoices", "P", "admin").records)
        self.repository.list_invoices.assert_not_called()

    def test_project_invoice_pivot_passes_scope_to_database(self):
        self.repository.invoice_pivot.return_value = []
        self.agent.read("invoice pivot", "P1", "project_manager")
        self.repository.invoice_pivot.assert_called_once_with("P1")
        self.repository.list_invoices.assert_not_called()

    def test_resource_rates_never_reach_nonadmin_evidence(self):
        record = {"name": "Example", "current_project_code": "P1",
                  "billing_rate": 101, "cost_rate": 79, "cost_value": 632}
        self.repository.list_manpower.return_value = [record]
        for role in ("project_manager", "planning_engineer", "employee"):
            result = self.agent.read("manpower", "P1", role)
            for field in ("billing_rate", "cost_rate", "cost_value"):
                self.assertNotIn(field, result.model_dump_json())
        result = self.agent.read("manpower", "P1", "admin")
        self.assertEqual(101, result.records[0]["billing_rate"])
        self.assertIn("billing_rate", record)

    def test_planner_cannot_propose_privileged_mutation(self):
        with self.assertRaises(PermissionError):
            self.agent.propose_change(ChangeOperation(
                action="record_delete", project_code="P1", payload={}
            ), "planning_engineer")
        self.repository.create_change_request.assert_not_called()


class DocumentVisibilityTests(unittest.TestCase):
    def test_only_ready_approved_documents_are_sent_to_store(self):
        repository, store = Mock(), Mock()
        ready = {"id": "ready", "kind": "pdf", "approval_status": "approved",
                 "index_status": "ready", "status": "ready"}
        repository.list_documents.return_value = [
            ready, {**ready, "id": "partial", "index_status": "indexing"},
            {**ready, "id": "pending", "approval_status": "pending"},
        ]
        store.search.return_value = RAGEvidence(query="progress", project_code="P1")
        RAGAgent(store, repository).retrieve("progress", "P1")
        store.search.assert_called_once_with("progress", "P1", document_ids=["ready"])

    def test_document_revoked_during_search_is_not_returned(self):
        repository, store = Mock(), Mock()
        repository.list_documents.side_effect = [[{
            "id": "D1", "kind": "pdf", "approval_status": "approved",
            "index_status": "ready", "status": "ready",
        }], []]
        store.search.return_value = RAGEvidence(query="progress", project_code="P1", evidence=[
            EvidenceItem(text="private", citation="Report.pdf, page 1", metadata={
                "document_id": "D1", "project_code": "P1", "approval_status": "approved"
            })
        ])
        self.assertEqual([], RAGAgent(store, repository).retrieve("progress", "P1").evidence)


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RAGStore(Path(self.temp.name) / "vectors", embedder=lambda texts: [
            [1.0, 0.0] if "commissioning" in text.casefold() else [0.0, 1.0]
            for text in texts
        ])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def chunk(self, identifier, text, **metadata):
        return {"id": identifier, "text": text, "metadata": {
            "document_id": identifier, "project_code": "P1", "filename": identifier + ".pdf",
            "page_number": 1, "chunk_number": 1, "approval_status": "approved", **metadata
        }}

    def test_unapproved_legacy_and_other_project_chunks_are_excluded(self):
        legacy = self.chunk("legacy", "commissioning")
        del legacy["metadata"]["approval_status"]
        self.store.add_chunks([
            self.chunk("good", "commissioning"), legacy,
            self.chunk("pending", "commissioning", approval_status="pending"),
            self.chunk("other", "commissioning", project_code="P2"),
        ])
        result = self.store.search("commissioning", "P1")
        self.assertEqual(["good"], [e.metadata["document_id"] for e in result.evidence])

    def test_newer_unrelated_document_does_not_outrank_relevant_evidence(self):
        self.store.add_chunks([
            self.chunk("old", "Commissioning requirements", effective_date="2025-01-01"),
            self.chunk("new", "Catering arrangements", effective_date="2026-08-01"),
        ])
        result = self.store.search("commissioning requirements", "P1")
        self.assertEqual("old", result.evidence[0].metadata["document_id"])

    def test_database_allowlist_limits_both_retrieval_sources(self):
        self.store.add_chunks([self.chunk("one", "commissioning"), self.chunk("two", "commissioning")])
        result = self.store.search("commissioning", "P1", document_ids=["two"])
        self.assertEqual(["two"], [e.metadata["document_id"] for e in result.evidence])
        self.assertEqual([], self.store.search("commissioning", "P1", document_ids=[]).evidence)

    def test_lexical_match_preserves_query_phrase_order(self):
        terms = self.store._terms("tower progress")
        self.assertGreater(
            self.store._lexical_score(terms, "Tower progress is 70%", "tower progress"),
            self.store._lexical_score(terms, "Progress on the tower", "tower progress"),
        )

    def test_lexical_candidates_are_filtered_and_bounded(self):
        collection = Mock()
        collection.query.return_value = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        collection.get.return_value = {"documents": [], "metadatas": []}
        original = self.store.collection
        try:
            self.store.collection = collection
            self.store.search("commissioning", "P1")
            arguments = collection.get.call_args.kwargs
            self.assertEqual(200, arguments["limit"])
            self.assertIn("where_document", arguments)
            self.assertEqual(collection.query.call_args.kwargs["where"], arguments["where"])
        finally:
            self.store.collection = original

    def test_invalid_scope_and_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.search("commissioning", "")
        with self.assertRaises(ValueError):
            self.store.search("commissioning", "P1", limit=10000)


class InvoiceAggregationTests(unittest.TestCase):
    def test_project_total_excludes_other_projects_in_sql(self):
        from contextlib import closing
        from prosight.repository import ProjectRepository, DEFAULT_DATA
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "invoices.db")
            repository.initialize(DEFAULT_DATA)
            repository.ensure_schema()
            with closing(repository.connect()) as connection:
                with connection:
                    connection.executemany(
                        """INSERT INTO project_invoices
                        (job_number,draft_invoice_number,project_code,levels,status,
                         invoice_value_usd,data_json,updated_at,import_id)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        [("J1", "I1", "PRJ-2024-001", "L1", "Pending", 125, "{}", "2026-09-07", "test"),
                         ("J2", "I2", "PRJ-2025-004", "L1", "Pending", 875, "{}", "2026-09-07", "test")],
                    )
            evidence = DatabaseManagerAgent(repository).read(
                "invoice pivot", "PRJ-2024-001", "project_manager"
            )
            self.assertEqual(125, evidence.records[0]["grand_total"])
            self.assertEqual({"PRJ-2024-001": 125}, evidence.records[0]["projects"])
            self.assertEqual(1000, repository.invoice_pivot()[0]["grand_total"])

if __name__ == "__main__":
    unittest.main()

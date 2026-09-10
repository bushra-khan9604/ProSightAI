"""Offline semantic projection, chunking, query-scope, and fact tests."""

from __future__ import annotations

import unittest
import uuid
import json
from unittest.mock import Mock, patch

from prosight.construction_facts import ConstructionFacts, FACT_QUERIES
from prosight.rag.semantic import (
    EMBEDDING_DIMENSIONS, INDEX_SQL, RevisionContext, SEMANTIC_HYBRID_SQL,
    SemanticIndexAdapter, SemanticSearch, extract_revision_chunks, project_entity,
    validate_embedding,
)


class FakePage:
    def __init__(self, text): self.text = text
    def extract_text(self): return self.text


class FakeReader:
    is_encrypted = False
    pages = [FakePage("1. COMMISSIONING\nInspection sequence and acceptance criteria")]


class SemanticTests(unittest.TestCase):
    def context(self, **changes):
        values = {
            "organization_id": str(uuid.uuid4()), "project_id": str(uuid.uuid4()),
            "semantic_document_id": str(uuid.uuid4()), "construction_document_id": str(uuid.uuid4()),
            "document_revision_id": str(uuid.uuid4()), "source_entity_id": str(uuid.uuid4()),
            "source_file_id": None, "import_batch_id": None,
            "storage_bucket": "prosight-pdfs", "storage_object_path": "existing/report.pdf",
            "approval_status": "approved", "projection_version_id": str(uuid.uuid4()),
            "projection_version": 1,
        }
        values.update(changes)
        return RevisionContext(**values)

    def test_projection_allowlist_excludes_structured_invoice_facts(self):
        record = {"id": str(uuid.uuid4()), "organization_id": str(uuid.uuid4()),
                  "project_id": str(uuid.uuid4()), "risk_number": "R-1", "title": "Delay",
                  "description": "Late material", "financial_exposure": "1000000.00",
                  "approval_status": "approved", "approved_at": "2026-09-10T00:00:00Z"}
        projection_id = str(uuid.uuid4())
        projection = project_entity(
            "risk", record, projection_version_id=projection_id, projection_version=1
        )
        self.assertIn("Late material", projection["body"])
        self.assertNotIn("1000000", projection["body"])
        self.assertEqual("en", projection["language_code"])
        self.assertEqual(projection_id, projection["projection_version_id"])
        self.assertEqual(1, projection["projection_version"])
        self.assertEqual("pending", projection["index_status"])
        self.assertIsNone(projection["construction_document_id"])
        with self.assertRaisesRegex(ValueError, "SQL-only"):
            project_entity("invoice", record, projection_version_id=projection_id, projection_version=1)
        with self.assertRaisesRegex(ValueError, "approved"):
            project_entity(
                "risk", {**record, "approval_status": "pending"},
                projection_version_id=projection_id, projection_version=1,
            )

    @patch("prosight.rag.semantic._reader", return_value=FakeReader())
    def test_chunk_ids_are_stable_and_provenance_is_complete(self, _reader):
        context = self.context()
        first = extract_revision_chunks(b"%PDF-fake", context)[0]
        second = extract_revision_chunks(b"%PDF-fake", context)[0]
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(context.document_revision_id, first["document_revision_id"])
        self.assertEqual(context.construction_document_id, first["construction_document_id"])
        self.assertNotIn("document_id", first)
        self.assertEqual(context.construction_document_id, first["metadata"]["document_id"])
        self.assertEqual("prosight-pdfs", first["metadata"]["storage_bucket"])
        self.assertEqual(1, first["page_start"])
        self.assertEqual(EMBEDDING_DIMENSIONS, first["embedding_dimensions"])
        changed = self.context(**{**context.__dict__, "chunking_version": "pdf-v2"})
        self.assertNotEqual(first["id"], extract_revision_chunks(b"%PDF-fake", changed)[0]["id"])

    def test_embedding_contract_rejects_wrong_nonfinite_and_zero_vectors(self):
        good = [1.0] + [0.0] * 1535
        self.assertEqual(1536, len(validate_embedding(good)))
        for vector in ([1.0], [0.0] * 1536, [float("inf")] + [0.0] * 1535):
            with self.assertRaises(ValueError): validate_embedding(vector)

    def test_unapproved_revision_cannot_be_chunked(self):
        with self.assertRaisesRegex(ValueError, "approved"):
            self.context(approval_status="in_review")

    def test_lineage_ids_are_both_null_for_legacy_or_both_present_for_ingestion(self):
        self.context(source_file_id=None, import_batch_id=None)
        self.context(source_file_id=str(uuid.uuid4()), import_batch_id=str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, "both be set or both be null"):
            self.context(source_file_id=str(uuid.uuid4()), import_batch_id=None)

    def test_hybrid_query_filters_tenant_project_and_state_in_every_branch(self):
        self.assertEqual(3, SEMANTIC_HYBRID_SQL.count("c.organization_id=%(organization_id)s::uuid"))
        self.assertEqual(3, SEMANTIC_HYBRID_SQL.count("c.project_id=any(%(project_ids)s::uuid[])"))
        self.assertEqual(3, SEMANTIC_HYBRID_SQL.count("c.approval_status='approved'"))
        self.assertEqual(3, SEMANTIC_HYBRID_SQL.count("c.index_status='ready'"))
        self.assertEqual(3, SEMANTIC_HYBRID_SQL.count("v.status='active'"))
        self.assertIn("semantic.semantic_projection_versions", SEMANTIC_HYBRID_SQL)
        self.assertIn("operator(extensions.<=>)", SEMANTIC_HYBRID_SQL)
        self.assertIn("c.search_vector", SEMANTIC_HYBRID_SQL)
        self.assertNotIn("search_text", SEMANTIC_HYBRID_SQL)
        self.assertNotIn("prosight.", SEMANTIC_HYBRID_SQL)
        connection = Mock(); connection.__enter__ = Mock(return_value=connection); connection.__exit__ = Mock(return_value=False)
        connection.execute_native.return_value.fetchall.return_value = []
        organization_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
        store = SemanticSearch(Mock(return_value=connection), lambda texts: [[1.0] + [0.0] * 1535],
                               projection_version=1, chunking_version="c1")
        store.search("commissioning", organization_id, [project_id])
        params = connection.execute_native.call_args.args[1]
        self.assertEqual(organization_id, params["organization_id"])
        self.assertEqual([project_id], params["project_ids"])

    @patch("prosight.rag.semantic._reader", return_value=FakeReader())
    def test_index_adapter_validates_and_publishes_one_idempotent_batch(self, _reader):
        chunk = extract_revision_chunks(b"%PDF-fake", self.context())[0]
        connection = Mock(); connection.__enter__ = Mock(return_value=connection); connection.__exit__ = Mock(return_value=False)
        connection.execute_native.return_value.fetchone.return_value = {"status": "succeeded"}
        adapter = SemanticIndexAdapter(
            Mock(return_value=connection), lambda texts: [[1.0] + [0.0] * 1535 for _ in texts]
        )
        job_id = str(uuid.uuid4())
        self.assertEqual(1, adapter.upsert([chunk], embedding_job_id=job_id))
        self.assertEqual(1, connection.execute_native.call_count)
        sql, params = connection.execute_native.call_args.args
        self.assertEqual(INDEX_SQL, sql)
        self.assertEqual({"org_id", "job_id", "chunks_jsonb", "idempotency_key"}, set(params))
        self.assertEqual(job_id, params["job_id"])
        payload = json.loads(params["chunks_jsonb"])
        self.assertEqual(chunk["construction_document_id"], payload[0]["chunk"]["construction_document_id"])
        self.assertEqual("pending", payload[0]["chunk"]["index_status"])
        self.assertEqual(1536, len(payload[0]["embedding"]))
        self.assertIn("semantic.publish_chunk_embeddings", INDEX_SQL)
        embedder = Mock()
        chunk["index_status"] = "ready"
        chunk["metadata"]["index_status"] = "ready"
        with self.assertRaisesRegex(ValueError, "pending"):
            SemanticIndexAdapter(Mock(), embedder).upsert([chunk])
        embedder.assert_not_called()

    @patch("prosight.rag.semantic._reader", return_value=FakeReader())
    def test_index_adapter_rejects_mixed_batch_scope_before_embedding(self, _reader):
        chunk = extract_revision_chunks(b"%PDF-fake", self.context())[0]
        cases = {
            "organization_id": str(uuid.uuid4()),
            "semantic_document_id": str(uuid.uuid4()),
            "project_id": str(uuid.uuid4()),
            "embedding_model": "different-model",
            "projection_version": 2,
            "chunking_version": "different-chunker",
        }
        for field, other_value in cases.items():
            with self.subTest(field=field):
                second = {**chunk, "id": str(uuid.uuid4()), "metadata": dict(chunk["metadata"])}
                second[field] = other_value
                metadata_field = field
                second["metadata"][metadata_field] = other_value
                embedder = Mock()
                with self.assertRaisesRegex(ValueError, "one "):
                    SemanticIndexAdapter(Mock(), embedder).upsert([chunk, second])
                embedder.assert_not_called()


class ConstructionFactsTests(unittest.TestCase):
    def test_structured_queries_use_only_construction_and_bound_scope(self):
        for query in FACT_QUERIES.values():
            self.assertIn("construction.", query)
            self.assertNotIn("prosight.", query)
            self.assertIn("organization_id=%(organization_id)s::uuid", query)
            self.assertIn("any(%(project_ids)s::uuid[])", query)
        self.assertIn("select p.id,p.code", FACT_QUERIES["projects"])
        self.assertNotIn("project_code", FACT_QUERIES["projects"])
        connection = Mock(); connection.execute_native.return_value.fetchall.return_value = [{"id": "x"}]
        connection.close = Mock()
        organization_id, project_id = str(uuid.uuid4()), str(uuid.uuid4())
        facts = ConstructionFacts(Mock(return_value=connection))
        self.assertEqual([{"id": "x"}], facts.query("risks", organization_id, [project_id]))
        params = connection.execute_native.call_args.args[1]
        self.assertEqual([project_id], params["project_ids"])

    def test_empty_project_scope_does_not_query(self):
        factory = Mock()
        facts = ConstructionFacts(factory)
        self.assertEqual([], facts.query("projects", str(uuid.uuid4()), []))
        factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()

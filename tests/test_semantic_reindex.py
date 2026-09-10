"""No-network tests for controlled legacy-to-semantic PDF reindexing."""

from __future__ import annotations

import hashlib
import unittest
import uuid
from unittest.mock import Mock, call, patch

from prosight.rag.reindex import (
    CutoverAcceptance, ReindexDocument, ReindexExecutor, ReindexPlanner,
    compare_rankings, require_cutover_acceptance,
)
from prosight.rag.semantic import RevisionContext


class FakePage:
    def extract_text(self): return "1. COMMISSIONING\nInspection sequence"


class FakeReader:
    is_encrypted = False
    pages = [FakePage()]


class ReindexTests(unittest.TestCase):
    def document(self, path="existing/a.pdf", **changes):
        values = dict(
            organization_id=str(uuid.uuid4()), project_id=str(uuid.uuid4()),
            semantic_document_id=str(uuid.uuid4()), construction_document_id=str(uuid.uuid4()),
            document_revision_id=str(uuid.uuid4()), source_entity_id=str(uuid.uuid4()),
            source_file_id=None, import_batch_id=None,
            storage_bucket="prosight-pdfs", storage_object_path=path,
            approval_status="approved", projection_version_id=str(uuid.uuid4()),
            projection_version=1,
        )
        values.update(changes)
        context = RevisionContext(**values)
        content = b"%PDF-existing"
        return ReindexDocument(context, hashlib.sha256(content).hexdigest()), content

    def test_plan_skips_duplicate_storage_objects_and_retains_legacy(self):
        document, _ = self.document()
        duplicate, _ = self.document(**document.context.__dict__)
        plan = ReindexPlanner().plan([document, duplicate])
        self.assertEqual(1, len(plan.documents))
        self.assertEqual(1, len(plan.skipped_duplicates))
        self.assertTrue(plan.dry_run)
        self.assertTrue(plan.legacy_index_retained)
        self.assertEqual(0, plan.uploads)

    def test_same_checksum_and_revision_at_different_path_is_duplicate(self):
        document, _ = self.document()
        duplicate, _ = self.document(
            **{**document.context.__dict__, "storage_object_path": "existing/copied.pdf"}
        )
        plan = ReindexPlanner().plan([document, duplicate])
        self.assertEqual((document,), plan.documents)
        self.assertEqual((document.context.document_revision_id,), plan.skipped_duplicates)

    def test_same_checksum_with_distinct_authoritative_revision_is_preserved(self):
        document, _ = self.document()
        second, _ = self.document(
            **{
                **document.context.__dict__,
                "semantic_document_id": str(uuid.uuid4()),
                "document_revision_id": str(uuid.uuid4()),
                "storage_object_path": "existing/revision-2.pdf",
            }
        )
        plan = ReindexPlanner().plan([document, second])
        self.assertEqual(2, len(plan.documents))
        self.assertEqual((), plan.skipped_duplicates)

    def test_same_storage_object_cannot_cross_organizations(self):
        document, _ = self.document()
        cross_tenant, _ = self.document(
            **{
                **document.context.__dict__,
                "organization_id": str(uuid.uuid4()),
                "semantic_document_id": str(uuid.uuid4()),
                "construction_document_id": str(uuid.uuid4()),
                "document_revision_id": str(uuid.uuid4()),
            }
        )
        with self.assertRaisesRegex(ValueError, "cannot be shared"):
            ReindexPlanner().plan([document, cross_tenant])

    def test_dry_run_does_not_download_or_write(self):
        document, _ = self.document()
        storage, sink = Mock(spec=["download"]), Mock(spec=["upsert"])
        result = ReindexExecutor(storage, sink).execute(ReindexPlanner().plan([document]))
        self.assertTrue(result["dry_run"])
        storage.download.assert_not_called(); sink.upsert.assert_not_called()

    @patch("prosight.rag.semantic._reader", return_value=FakeReader())
    def test_execution_downloads_existing_object_without_upload_or_legacy_delete(self, _reader):
        document, content = self.document()
        storage, sink = Mock(spec=["download"]), Mock(spec=["upsert"])
        storage.download.return_value = content
        sink.upsert.side_effect = lambda chunks: len(chunks)
        result = ReindexExecutor(storage, sink).execute(ReindexPlanner().plan([document]), dry_run=False)
        storage.download.assert_called_once_with("prosight-pdfs", document.context.storage_object_path)
        sink.upsert.assert_called_once()
        self.assertEqual(0, result["uploads"]); self.assertEqual(0, result["deletes"])
        self.assertTrue(result["legacy_index_retained"])

    @patch("prosight.rag.semantic._reader", return_value=FakeReader())
    def test_execution_publishes_each_semantic_document_and_job_separately(self, _reader):
        first, content = self.document(path="existing/one.pdf")
        second, _ = self.document(path="existing/two.pdf")
        first_job, second_job = str(uuid.uuid4()), str(uuid.uuid4())
        first = type(first)(first.context, first.checksum_sha256, first_job)
        second = type(second)(second.context, second.checksum_sha256, second_job)
        storage, sink = Mock(spec=["download"]), Mock(spec=["upsert"])
        storage.download.return_value = content
        sink.upsert.side_effect = lambda chunks, **_: len(chunks)

        result = ReindexExecutor(storage, sink).execute(
            ReindexPlanner().plan([first, second]), dry_run=False
        )

        self.assertEqual(2, sink.upsert.call_count)
        self.assertEqual(
            [first_job, second_job],
            [call.kwargs["embedding_job_id"] for call in sink.upsert.call_args_list],
        )
        self.assertNotEqual(
            sink.upsert.call_args_list[0].args[0][0]["semantic_document_id"],
            sink.upsert.call_args_list[1].args[0][0]["semantic_document_id"],
        )
        self.assertEqual(2, result["documents"])

    def test_retrieval_comparison_and_explicit_cutover_acceptance(self):
        comparison = compare_rankings(["delay"], lambda q, n: ["old", "shared"], lambda q, n: ["new", "shared"])
        self.assertFalse(comparison["cutover_accepted"])
        self.assertEqual(1, comparison["queries"][0]["overlap_count"])
        with self.assertRaises(PermissionError): require_cutover_acceptance(None)
        acceptance = CutoverAcceptance("CAB-1", "admin@example", "a" * 64)
        self.assertIs(acceptance, require_cutover_acceptance(acceptance))


if __name__ == "__main__":
    unittest.main()

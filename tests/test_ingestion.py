"""Deterministic Excel validation and job persistence tests."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from openpyxl import Workbook
from reportlab.pdfgen import canvas

from prosight.ingestion.excel import PROJECT_COLUMNS, preview_workbook
from prosight.ingestion.manager import IngestionManager
from prosight.ingestion.pdf import detect_reporting_date, extract_pdf_chunks
from prosight.rag.store import RAGStore
from prosight.repository import DEFAULT_DATA, ProjectRepository


class IngestionTests(unittest.TestCase):
    @staticmethod
    def fake_embeddings(texts):
        """Produce deterministic vectors without calling OpenAI."""
        return [[float("hospital" in text.lower()), float("tower" in text.lower()), 1.0] for text in texts]

    def test_canonical_excel_generates_validated_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "projects.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Projects"
            sheet.append(PROJECT_COLUMNS)
            sheet.append([
                "PRJ-TEST-001", "Test Project", "future", "Client", "Dubai", 1_000_000,
                "2027-01-01", "2027-12-31", "2027-12-31", "2026-12-01", 0, 0, 0,
            ])
            workbook.save(path)
            preview = preview_workbook(path, "PRJ-TEST-001")
        self.assertFalse(preview["mapping_required"])
        self.assertEqual("PRJ-TEST-001", preview["projects"][0]["code"])
        self.assertIn("projects.xlsx, Projects row 2", preview["projects"][0]["sources"])

    def test_noncanonical_excel_requires_mapping_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Data"
            sheet.append(["Project ID", "Finish"])
            sheet.append(["ABC", "2028-01-01"])
            workbook.save(path)
            preview = preview_workbook(path, "ABC")
        self.assertTrue(preview["mapping_required"])
        self.assertIn("Data", preview["suggested_mapping"])

    def test_interrupted_jobs_are_marked_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "test.db")
            repository.initialize(DEFAULT_DATA)
            document = repository.create_document(
                "PRJ-2024-001", "report.pdf", "pdf", "checksum", "report.pdf"
            )
            job = repository.create_job(document["id"])
            repository.recover_interrupted_jobs()
            self.assertEqual("failed", repository.get_job(job["id"])["status"])

    def test_failed_documents_are_hidden_but_jobs_remain_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "test.db")
            repository.initialize(DEFAULT_DATA)
            document = repository.create_document(
                "PRJ-2024-001", "broken.xlsx", "xlsx", "failed-checksum", "broken.xlsx"
            )
            job = repository.create_job(document["id"])
            repository.update_document_status(document["id"], "failed")
            repository.update_job(job["id"], "failed", 100, "Workbook is malformed")
            self.assertEqual([], repository.list_documents("PRJ-2024-001"))
            jobs = repository.list_jobs("PRJ-2024-001")
            self.assertEqual("failed", jobs[0]["status"])
            self.assertEqual("Workbook is malformed", jobs[0]["message"])

    def test_failed_job_cleanup_removes_artifacts_and_writes_audit(self):
        class FakeStore:
            def __init__(self):
                self.deleted = []

            def delete_document(self, document_id):
                self.deleted.append(document_id)

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = ProjectRepository(root / "test.db")
            repository.initialize(DEFAULT_DATA)
            stored = root / "broken.pdf"
            stored.write_bytes(b"%PDF-broken")
            document = repository.create_document(
                "PRJ-2024-001", "broken.pdf", "pdf", "cleanup-checksum", str(stored)
            )
            job = repository.create_job(document["id"])
            repository.update_document_status(document["id"], "failed")
            repository.update_job(job["id"], "failed", 100, "PDF parsing failed")
            store = FakeStore()
            manager = IngestionManager(repository, store, root / "uploads")
            try:
                cleared = manager.clear_failed_job(job["id"], "project_manager")
            finally:
                manager.close()
            self.assertEqual(job["id"], cleared["job_id"])
            self.assertEqual([document["id"]], store.deleted)
            self.assertFalse(stored.exists())
            self.assertIsNone(repository.get_job(job["id"]))
            self.assertIsNone(repository.get_document(document["id"]))
            with closing(repository.connect()) as db:
                audit = db.execute(
                    "SELECT * FROM audit_events WHERE action='failed_ingestion_cleared'"
                ).fetchone()
            self.assertIsNotNone(audit)
            self.assertNotIn("stored_path", audit["before_json"])

    def test_nonfailed_job_cannot_be_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "test.db")
            repository.initialize(DEFAULT_DATA)
            document = repository.create_document(
                "PRJ-2024-001", "queued.xlsx", "xlsx", "queued-checksum", "queued.xlsx"
            )
            job = repository.create_job(document["id"])
            with self.assertRaisesRegex(ValueError, "Only failed"):
                repository.delete_failed_ingestion_records(job["id"], "admin")
            self.assertIsNotNone(repository.get_job(job["id"]))

    def test_failed_job_with_pending_change_cannot_be_cleared(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "test.db")
            repository.initialize(DEFAULT_DATA)
            document = repository.create_document(
                "PRJ-2024-001", "pending.xlsx", "xlsx", "pending-checksum", "pending.xlsx"
            )
            job = repository.create_job(document["id"])
            change = repository.create_change_request(
                "excel_import", "PRJ-2024-001", {"projects": []},
                {"before": None, "after": {}}, "project_manager",
            )
            repository.update_document_status(document["id"], "failed")
            repository.update_job(
                job["id"], "failed", 100, "Import failed", change["id"]
            )
            with self.assertRaisesRegex(ValueError, "unresolved change request"):
                repository.delete_failed_ingestion_records(job["id"], "admin")
            self.assertIsNotNone(repository.get_job(job["id"]))

    def test_rag_search_is_project_scoped_and_document_can_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RAGStore(Path(directory) / "vectors", embedder=self.fake_embeddings)
            store.add_chunks([
                {
                    "id": "doc-a:1:1",
                    "text": "Hospital commissioning requirements",
                    "metadata": {
                        "document_id": "doc-a", "project_code": "PRJ-A",
                        "filename": "Hospital.pdf", "page_number": 2, "chunk_number": 1,
                    },
                },
                {
                    "id": "doc-b:1:1",
                    "text": "Tower facade requirements",
                    "metadata": {
                        "document_id": "doc-b", "project_code": "PRJ-B",
                        "filename": "Tower.pdf", "page_number": 9, "chunk_number": 1,
                    },
                },
            ])
            result = store.search("hospital", "PRJ-A")
            self.assertEqual(["Hospital.pdf, page 2"], [item.citation for item in result.evidence])
            store.delete_document("doc-a")
            self.assertEqual([], store.search("hospital", "PRJ-A").evidence)
            store.close()

    def test_newer_relevant_document_is_ranked_first(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RAGStore(Path(directory) / "vectors", embedder=self.fake_embeddings)
            store.add_chunks([
                {
                    "id": "old:1:1", "text": "Tower progress is 60 percent",
                    "metadata": {
                        "document_id": "old", "project_code": "PRJ-A",
                        "filename": "Old.pdf", "page_number": 1, "chunk_number": 1,
                        "effective_date": "2026-01-31", "date_status": "confirmed",
                    },
                },
                {
                    "id": "new:1:1", "text": "Tower progress is 72 percent",
                    "metadata": {
                        "document_id": "new", "project_code": "PRJ-A",
                        "filename": "New.pdf", "page_number": 1, "chunk_number": 1,
                        "effective_date": "2026-08-31", "date_status": "confirmed",
                    },
                },
            ])
            result = store.search("tower progress", "PRJ-A")
            self.assertEqual("New.pdf, page 1", result.evidence[0].citation)
            store.close()

    def test_pdf_reporting_date_is_detected_from_first_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            pdf = canvas.Canvas(str(path))
            pdf.drawString(72, 760, "Monthly Progress Report")
            pdf.drawString(72, 735, "Reporting date: 31 August 2026")
            pdf.save()
            self.assertEqual("2026-08-31", detect_reporting_date(path))

    def test_pdf_chunks_are_token_bounded_and_never_cross_pages(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pages.pdf"
            pdf = canvas.Canvas(str(path))
            pdf.drawString(30, 760, "FIRSTPAGE " * 1200)
            pdf.showPage()
            pdf.drawString(30, 760, "SECONDPAGE evidence")
            pdf.save()
            chunks = extract_pdf_chunks(path, {
                "id": "00000000-0000-0000-0000-000000000001",
                "project_code": "PRJ-2024-001", "filename": "pages.pdf",
                "effective_date": "2026-09-11", "date_status": "confirmed",
            })
            self.assertEqual({1, 2}, {item["metadata"]["page_number"] for item in chunks})
            self.assertTrue(all(item["token_count"] <= 800 for item in chunks))
            self.assertTrue(all(len(item["content_hash"]) == 64 for item in chunks))
            self.assertFalse(any(
                "FIRSTPAGE" in item["text"] and "SECONDPAGE" in item["text"]
                for item in chunks
            ))


if __name__ == "__main__":
    unittest.main()

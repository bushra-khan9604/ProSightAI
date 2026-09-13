"""Deterministic Excel validation and job persistence tests."""

from __future__ import annotations

import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook
from reportlab.pdfgen import canvas

from prosight.ingestion.excel import PROJECT_COLUMNS, preview_workbook
from prosight.ingestion.manager import IngestionManager
from prosight.ingestion.pdf import detect_reporting_date, extract_pdf_chunks
from prosight.rag.store import RAGStore
from prosight.repository import DEFAULT_DATA, ProjectRepository
from prosight.supabase_repository import SupabaseProjectRepository


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

    def test_supabase_job_responses_preserve_job_id_and_detected_date(self):
        class Gateway:
            def select(self, table, **_filters):
                if table == "documents":
                    return [{
                        "id": "document-id", "project_code": "PRJ-2024-001",
                        "kind": "pdf", "filename": "report.pdf", "checksum": "sum",
                        "reporting_date": "2026-06-30", "effective_date": "2026-06-30",
                        "date_status": "detected",
                    }]
                if table == "ingestion_jobs":
                    return [{
                        "id": "job-id", "document_id": "document-id",
                        "status": "awaiting_date_confirmation", "progress": 45,
                    }]
                return []

        repository = SupabaseProjectRepository.__new__(SupabaseProjectRepository)
        repository.user = repository.service = Gateway()
        job = repository.get_job("job-id")
        listed = repository.list_jobs("PRJ-2024-001")[0]
        self.assertEqual("job-id", job["id"])
        self.assertEqual("job-id", listed["id"])
        self.assertEqual("2026-06-30", job["detected_reporting_date"])
        self.assertEqual("2026-06-30", listed["detected_reporting_date"])

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

    def test_approved_excel_clears_completed_job_and_keeps_ready_document(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = ProjectRepository(Path(directory) / "test.db")
            repository.initialize(DEFAULT_DATA)
            document = repository.create_document(
                "PRJ-2024-001", "approved.xlsx", "xlsx", "approved-checksum",
                "approved.xlsx",
            )
            job = repository.create_job(document["id"])
            change = repository.create_change_request(
                "excel_import", "PRJ-2024-001", {"projects": []},
                {"before": None, "after": {}}, "project_manager",
            )
            repository.update_document_status(document["id"], "awaiting_approval")
            repository.update_job(
                job["id"], "awaiting_approval", 100, "Awaiting approval", change["id"]
            )

            repository.decide_change_request(change["id"], "approved", "admin")

            self.assertIsNone(repository.get_job(job["id"]))
            self.assertEqual("ready", repository.get_document(document["id"])["status"])

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

    def test_pdf_requires_admin_approval_before_indexing(self):
        class Store:
            def __init__(self):
                self.chunks = []

            def add_chunks(self, chunks):
                self.chunks.extend(chunks)

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "approval.pdf"
            pdf = canvas.Canvas(str(source))
            pdf.drawString(72, 760, "Monthly Progress Report")
            pdf.drawString(72, 735, "Reporting date: 31 August 2026")
            pdf.drawString(72, 710, "Approved evidence content")
            pdf.save()
            repository = ProjectRepository(root / "test.db")
            repository.initialize(DEFAULT_DATA)
            store = Store()
            manager = IngestionManager(repository, store, root / "uploads")
            try:
                submitted = manager.submit(
                    source, source.name, "PRJ-2024-001", "project_manager"
                )
                job_id = submitted["job"]["id"]
                for _ in range(100):
                    job = repository.get_job(job_id)
                    if job["status"] == "awaiting_date_confirmation":
                        break
                    time.sleep(0.02)
                self.assertEqual("awaiting_date_confirmation", job["status"])
                manager.confirm_pdf_date(job_id, "2026-08-31", "project_manager")
                job = repository.get_job(job_id)
                self.assertEqual("awaiting_approval", job["status"])
                self.assertEqual([], store.chunks)
                change = repository.get_change_request(job["change_request_id"])
                self.assertEqual("pdf_ingestion", change["action"])
                repository.decide_change_request(change["id"], "approved", "admin")
                manager.resume_approved_pdf(job_id)
                for _ in range(100):
                    job = repository.get_job(job_id)
                    if job is None:
                        break
                    time.sleep(0.02)
                self.assertIsNone(job)
                document = repository.get_document(submitted["document"]["id"])
                self.assertEqual("ready", document["status"])
                self.assertTrue(store.chunks)
            finally:
                manager.close()

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

    def test_pdf_chunks_remove_repeated_page_headers_and_footers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repeated.pdf"
            pdf = canvas.Canvas(str(path))
            for page_number in range(1, 4):
                pdf.drawString(72, 780, "Monthly Progress Report")
                pdf.drawString(72, 730, f"Unique progress evidence {page_number}")
                pdf.drawString(72, 40, "Confidential project record")
                pdf.showPage()
            pdf.save()
            chunks = extract_pdf_chunks(path, {
                "id": "00000000-0000-0000-0000-000000000001",
                "project_code": "PRJ-2024-001", "filename": "repeated.pdf",
                "effective_date": "2026-09-11", "date_status": "confirmed",
            })
        combined = "\n".join(item["text"] for item in chunks)
        self.assertNotIn("Monthly Progress Report", combined)
        self.assertNotIn("Confidential project record", combined)
        self.assertIn("Unique progress evidence 1", combined)
        self.assertTrue(all(item["metadata"]["section"] for item in chunks))

    def test_openai_embeddings_are_batched_and_retried(self):
        calls, sleeps, writes = [], [], []

        class Embeddings:
            def create(self, **payload):
                calls.append(payload["input"])
                if len(calls) == 1:
                    raise TimeoutError("temporary")
                return SimpleNamespace(data=[
                    SimpleNamespace(index=index, embedding=[0.1] * 1536)
                    for index in range(len(payload["input"]))
                ])

        class Service:
            def select(self, *_args, **_kwargs):
                return []

            select_all = select

            def request(self, _method, _path, payload, **_kwargs):
                writes.extend(payload)

            def update(self, *_args, **_kwargs):
                return []

            def delete(self, *_args, **_kwargs):
                return []

        store = RAGStore(embedder=self.fake_embeddings)
        store.embedder = None
        store.openai = SimpleNamespace(embeddings=Embeddings())
        store.service = Service()
        store.sleeper = sleeps.append
        store.settings = SimpleNamespace(
            embedding_retry_count=5, embedding_batch_size=64,
            embedding_model="text-embedding-3-small"
        )
        store.add_chunks([{
            "id": f"doc:1:{index}", "text": f"evidence {index}",
            "content_hash": f"hash-{index}", "token_count": 2,
            "metadata": {
                "document_id": "00000000-0000-0000-0000-000000000001",
                "project_code": "PRJ-2024-001", "filename": "report.pdf",
                "page_number": 1, "chunk_number": index,
                "effective_date": "2026-09-11", "date_status": "confirmed",
            },
        } for index in range(1, 66)])
        self.assertEqual([64, 64, 1], [len(batch) for batch in calls])
        self.assertEqual([1], sleeps)
        self.assertEqual(130, len(writes))  # 65 pending rows and 65 ready rows.
        self.assertEqual(1536, len(writes[-1]["embedding"]))


if __name__ == "__main__":
    unittest.main()

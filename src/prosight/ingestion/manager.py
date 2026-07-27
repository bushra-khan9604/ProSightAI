"""Bounded background ingestion with durable SQLite job state."""

from __future__ import annotations

import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..repository import ProjectRepository
from ..rag.store import RAGStore
from .excel import preview_mapped_workbook, preview_workbook
from .mapping import OpenAIColumnMapper
from .pdf import detect_reporting_date, extract_pdf_chunks


class IngestionManager:
    """Validate uploads, persist them safely, and process them in background jobs."""

    LIMITS = {"pdf": 20 * 1024 * 1024, "xlsx": 10 * 1024 * 1024}

    def __init__(
        self, repository: ProjectRepository, rag_store: RAGStore, upload_dir: str | Path,
        workers: int = 2,
    ):
        self.repository, self.rag_store = repository, rag_store
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.column_mapper = OpenAIColumnMapper()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prosight-ingest")
        self.repository.recover_interrupted_jobs()

    def submit(
        self, source: Path, original_name: str, project_code: str, actor_role: str
    ) -> dict:
        """Validate, copy, register, and enqueue one PDF or XLSX upload."""
        safe_name = Path(original_name).name
        if safe_name != original_name or safe_name in {"", ".", ".."}:
            raise ValueError("Invalid filename")
        extension = Path(safe_name).suffix.lower()
        if extension not in {".pdf", ".xlsx"}:
            raise ValueError("Only .pdf and .xlsx files are supported")
        kind = extension[1:]
        size = source.stat().st_size
        if not size or size > self.LIMITS[kind]:
            raise ValueError(f"{kind.upper()} file size is invalid or exceeds the configured limit")
        signature = source.read_bytes()[:5]
        if kind == "pdf" and signature != b"%PDF-":
            raise ValueError("File content is not a valid PDF")
        if kind == "xlsx" and not signature.startswith(b"PK"):
            raise ValueError("File content is not a valid XLSX workbook")
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        destination_dir = self.upload_dir / project_code
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{checksum[:12]}-{safe_name}"
        shutil.copy2(source, destination)
        try:
            document = self.repository.create_document(
                project_code, safe_name, kind, checksum, str(destination)
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        job = self.repository.create_job(document["id"])
        self.executor.submit(self._process, job["id"], document, actor_role)
        return {"document": document, "job": job}

    def _process(self, job_id: str, document: dict, actor_role: str) -> None:
        """Run type-specific ingestion and persist every lifecycle transition."""
        try:
            self.repository.update_job(job_id, "processing", 10, "Validating file")
            path = Path(document["stored_path"])
            if document["kind"] == "pdf":
                detected = detect_reporting_date(path)
                if detected:
                    self.repository.update_document_date(
                        document["id"], detected, detected, "detected"
                    )
                    self.repository.update_document_status(
                        document["id"], "awaiting_date_confirmation"
                    )
                    self.repository.update_job(
                        job_id,
                        "awaiting_date_confirmation",
                        45,
                        f"Confirm detected report date: {detected}",
                    )
                else:
                    fallback = document["created_at"][:10]
                    self.repository.update_document_date(
                        document["id"], None, fallback, "fallback"
                    )
                    self._index_pdf(job_id, self.repository.get_document(document["id"]))
            else:
                preview = preview_workbook(path, document["project_code"])
                if preview["mapping_required"]:
                    mapping = self.column_mapper.propose(path)
                    preview = preview_mapped_workbook(path, document["project_code"], mapping)
                change = self.repository.create_change_request(
                    "excel_import", document["project_code"], {"projects": preview["projects"]},
                    {"before": None, "after": preview, "warnings": preview["warnings"]},
                    actor_role,
                )
                self.repository.update_document_status(document["id"], "awaiting_approval")
                self.repository.update_job(
                    job_id, "awaiting_approval", 100, "Excel preview requires Admin approval", change["id"]
                )
        except Exception as error:
            self.repository.update_document_status(document["id"], "failed")
            self.repository.update_job(job_id, "failed", 100, str(error)[:500])

    def confirm_pdf_date(
        self, job_id: str, reporting_date: str, actor_role: str
    ) -> dict:
        """Confirm a detected PDF date and resume its background indexing."""
        if actor_role not in {"admin", "project_manager", "planning_engineer"}:
            raise PermissionError("This role cannot confirm document dates")
        job = self.repository.get_job(job_id)
        if not job or job["kind"] != "pdf":
            raise KeyError("PDF ingestion job not found")
        if job["status"] != "awaiting_date_confirmation":
            raise ValueError("This PDF is not awaiting date confirmation")
        document = self.repository.get_document(job["document_id"])
        self.repository.update_document_date(
            document["id"], reporting_date, reporting_date, "confirmed"
        )
        self.repository.update_document_status(document["id"], "processing")
        self.repository.update_job(job_id, "processing", 50, "Report date confirmed")
        self.executor.submit(
            self._index_pdf, job_id, self.repository.get_document(document["id"])
        )
        return self.repository.get_job(job_id)

    def _index_pdf(self, job_id: str, document: dict) -> None:
        """Extract, embed, and publish one date-resolved PDF."""
        try:
            chunks = extract_pdf_chunks(Path(document["stored_path"]), document)
            self.repository.update_job(
                job_id, "processing", 55, f"Embedding {len(chunks)} chunks"
            )
            self.rag_store.add_chunks(chunks)
            self.repository.update_document_status(document["id"], "ready")
            self.repository.update_job(
                job_id, "ready", 100, f"Indexed {len(chunks)} chunks"
            )
        except Exception as error:
            self.repository.update_document_status(document["id"], "failed")
            self.repository.update_job(job_id, "failed", 100, str(error)[:500])

    def delete_document(self, document_id: str, actor_role: str) -> dict:
        """Remove an indexed document after enforcing Admin authorization."""
        if actor_role != "admin":
            raise PermissionError("Admin approval is required")
        document = self.repository.get_document(document_id)
        if not document:
            raise KeyError("Document not found")
        if document["kind"] == "pdf":
            self.rag_store.delete_document(document_id)
        Path(document["stored_path"]).unlink(missing_ok=True)
        return self.repository.delete_document_record(document_id) or {}

    def close(self) -> None:
        """Stop accepting background work and release vector-store resources."""
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.rag_store.close()

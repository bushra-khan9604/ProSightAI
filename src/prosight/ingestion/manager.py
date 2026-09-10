"""Bounded background ingestion with durable SQLite job state."""

from __future__ import annotations

from functools import wraps
from ..project_locks import project_lock

import hashlib
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..repository import ProjectRepository
from ..rag.store import RAGStore
from .excel import preview_mapped_workbook, preview_workbook
from .mapping import OpenAIColumnMapper
from .pdf import detect_reporting_date, extract_pdf_chunks

logger = logging.getLogger("prosight.ingestion")


def _project_job(function):
    @wraps(function)
    def run(self, job_id, document, *args, **kwargs):
        with project_lock(self.repository, document["project_code"]):
            if not self.repository.get_document(document["id"]):
                return
            return function(self, job_id, document, *args, **kwargs)
    return run


def _project_upload(function):
    @wraps(function)
    def run(self, source, original_name, project_code, actor_role):
        with project_lock(self.repository, project_code):
            return function(self, source, original_name, project_code, actor_role)
    return run


class IngestionManager:
    """Validate uploads, persist them safely, and process them in background jobs."""

    LIMITS = {"pdf": 20 * 1024 * 1024, "xlsx": 10 * 1024 * 1024}

    @staticmethod
    def _failure_message(error: Exception) -> str:
        """Return a useful browser-safe reason without leaking internal details."""
        if isinstance(error, ValueError):
            return str(error)[:500]
        if isinstance(error, RuntimeError) and str(error).startswith("OPENAI_API_KEY"):
            return "This workbook needs column mapping, but the mapping service is unavailable."
        return "The file could not be processed. Check its format and contents, then try again."

    def __init__(
        self, repository: ProjectRepository, rag_store: RAGStore, upload_dir: str | Path,
        workers: int = 2, storage=None,
    ):
        self.repository, self.rag_store, self.storage = repository, rag_store, storage
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.column_mapper = OpenAIColumnMapper()
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="prosight-ingest")
        self.repository.recover_interrupted_jobs()

    @_project_upload
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

    @_project_job
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
                    self._request_document_approval(job_id, self.repository.get_document(document["id"]), actor_role)
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
            logger.exception(
                "ingestion_failed",
                extra={"job_id": job_id, "document_id": document["id"], "kind": document["kind"]},
            )
            self.repository.update_document_status(document["id"], "failed")
            self.repository.update_job(
                job_id, "failed", 100, self._failure_message(error)
            )

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
        self._request_document_approval(
            job_id, self.repository.get_document(document["id"]), actor_role
        )
        return self.repository.get_job(job_id)

    def _request_document_approval(
        self, job_id: str, document: dict | None, actor_role: str
    ) -> None:
        """Create a review request; embedding is deliberately deferred until approval."""
        if not document:
            raise KeyError("Document not found")
        preview = {
            "document_id": document["id"],
            "project_code": document["project_code"],
            "filename": document["filename"],
            "kind": document["kind"],
            "checksum": document["checksum"],
            "reporting_date": document.get("reporting_date"),
            "effective_date": document.get("effective_date"),
            "date_status": document.get("date_status"),
            "approval_status": "awaiting_approval",
            "index_status": "not_indexed",
            "warnings": [],
        }
        self.repository.create_document_approval_request(
            document, actor_role, job_id, {"before": None, "after": preview, "warnings": []}
        )

    def index_approved_document(self, change: dict) -> None:
        """Queue embedding only after an Admin-approved document change request."""
        payload = change.get("payload", {})
        document_id, job_id = payload.get("document_id"), payload.get("job_id")
        if not document_id or not job_id:
            raise ValueError("Document approval payload is incomplete")
        document = self.repository.get_document(document_id)
        if not document or document.get("approval_status") != "approved":
            raise ValueError("Document must be approved before indexing")
        self.executor.submit(self._index_pdf, job_id, document)

    def retry_indexing(self, job_id: str, actor_role: str) -> dict:
        """Retry a failed post-approval index operation without re-approving it."""
        if actor_role != "admin":
            raise PermissionError("Admin approval is required to retry document indexing")
        job = self.repository.get_job(job_id)
        if not job or job["kind"] != "pdf":
            raise KeyError("PDF ingestion job not found")
        if job["status"] != "failed":
            raise ValueError("Only failed indexing jobs can be retried")
        document = self.repository.get_document(job["document_id"])
        if not document or document.get("approval_status") != "approved":
            raise ValueError("Only an approved document can be re-indexed")
        self.repository.update_document_status(document["id"], "approved")
        self.repository.update_document_index_status(document["id"], "queued")
        self.executor.submit(self._index_pdf, job_id, document)
        return self.repository.get_job(job_id)

    @_project_job
    def _index_pdf(self, job_id: str, document: dict) -> None:
        """Extract, embed, and publish one date-resolved PDF."""
        try:
            self.repository.update_document_index_status(document["id"], "indexing")
            path = Path(document["stored_path"])
            if self.storage:
                self.repository.update_job(job_id, "processing", 40, "Saving approved PDF to private storage")
                bucket, object_path = self.storage.upload_pdf(document, path)
                self.repository.update_document_storage(document["id"], bucket, object_path)
                document = self.repository.get_document(document["id"])
            elif getattr(self.repository, "backend", "sqlite") == "postgres":
                raise RuntimeError("SUPABASE_SECRET_KEY is required for approved PDF Storage")
            chunks = extract_pdf_chunks(path, document)
            self.repository.update_job(
                job_id, "processing", 55, f"Embedding {len(chunks)} chunks"
            )
            self.rag_store.add_chunks(chunks)
            self.repository.update_document_status(document["id"], "ready")
            self.repository.update_document_index_status(document["id"], "ready")
            self.repository.update_job(
                job_id, "ready", 100, f"Indexed {len(chunks)} chunks"
            )
        except Exception as error:
            logger.exception(
                "pdf_indexing_failed",
                extra={"job_id": job_id, "document_id": document["id"], "kind": "pdf"},
            )
            # Upserted batches can fail part-way through. Remove the whole
            # document namespace so retries cannot expose partial evidence or
            # duplicate vectors.
            try:
                self.rag_store.delete_document(document["id"])
            except Exception:
                logger.exception(
                    "pdf_partial_index_cleanup_failed",
                    extra={"job_id": job_id, "document_id": document["id"]},
                )
            # Approval remains valid after an embedding failure. Keep the
            # document visible for a controlled Admin retry and never mark a
            # partial vector set as ready.
            self.repository.update_document_status(document["id"], "approved")
            self.repository.update_document_index_status(document["id"], "failed")
            self.repository.update_job(
                job_id, "failed", 100, self._failure_message(error)
            )

    def delete_document(self, document_id: str, actor_role: str) -> dict:
        """Remove an indexed document after enforcing Admin authorization."""
        if actor_role != "admin":
            raise PermissionError("Admin approval is required")
        document = self.repository.get_document(document_id)
        if not document:
            raise KeyError("Document not found")
        if document["kind"] == "pdf":
            self.rag_store.delete_document(document_id)
            if self.storage and document.get("storage_bucket"):
                self.storage.delete(document["storage_bucket"], document["storage_object_path"])
        Path(document["stored_path"]).unlink(missing_ok=True)
        return self.repository.delete_document_record(document_id) or {}

    def clear_failed_job(self, job_id: str, actor_role: str) -> dict:
        """Permanently remove a failed upload and its diagnostic records."""
        if actor_role not in {"admin", "project_manager", "planning_engineer"}:
            raise PermissionError("This role cannot clear failed ingestion jobs")
        job = self.repository.get_job(job_id)
        if not job:
            raise KeyError("Ingestion job not found")
        if job["status"] != "failed":
            raise ValueError("Only failed ingestion jobs can be cleared")
        if job.get("change_request_id"):
            change = self.repository.get_change_request(job["change_request_id"])
            if change and change["status"] == "pending":
                raise ValueError("This failed job still has an unresolved change request")
        document = self.repository.get_document(job["document_id"])
        if not document:
            raise KeyError("Failed upload metadata not found")
        if document["kind"] == "pdf":
            self.rag_store.delete_document(document["id"])
            if self.storage and document.get("storage_bucket"):
                self.storage.delete(document["storage_bucket"], document["storage_object_path"])
        Path(document["stored_path"]).unlink(missing_ok=True)
        return self.repository.delete_failed_ingestion_records(job_id, actor_role)

    def close(self) -> None:
        """Stop accepting background work and release vector-store resources."""
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.rag_store.close()
        if self.storage:
            self.storage.close()

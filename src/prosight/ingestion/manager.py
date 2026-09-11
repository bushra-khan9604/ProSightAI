"""Bounded background ingestion with durable, restart-safe job state."""

from __future__ import annotations

import hashlib
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from pathlib import Path

from ..repository import ProjectRepository
from ..rag.store import RAGStore
from .excel import preview_mapped_workbook, preview_workbook
from .mapping import OpenAIColumnMapper
from .pdf import detect_reporting_date, extract_pdf_chunks

logger = logging.getLogger("prosight.ingestion")


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
        workers: int = 2,
    ):
        self.repository, self.rag_store = repository, rag_store
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.column_mapper = OpenAIColumnMapper()
        self.executor = ThreadPoolExecutor(
            max_workers=min(max(workers, 1), 2), thread_name_prefix="prosight-ingest"
        )
        recovered = self.repository.recover_interrupted_jobs() or []
        for item in recovered:
            self._submit_background(
                self._process, item["job"]["id"], item["document"], "admin"
            )

    def _submit_background(self, function, *args) -> None:
        """Submit work while preserving the request identity when one exists."""
        context = copy_context()
        self.executor.submit(context.run, function, *args)

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
        store_file = getattr(self.repository, "store_document_file", None)
        if store_file:
            try:
                store_file(document, destination)
            except Exception:
                self.repository.delete_document_record(document["id"])
                destination.unlink(missing_ok=True)
                raise
        job = self.repository.create_job(document["id"])
        self._submit_background(self._process, job["id"], document, actor_role)
        return {"document": document, "job": job}

    def _process(self, job_id: str, document: dict, actor_role: str) -> None:
        """Run type-specific ingestion and persist every lifecycle transition."""
        try:
            claim = getattr(self.repository, "claim_job", None)
            if claim and not claim(job_id):
                return
            self.repository.update_job(job_id, "processing", 10, "Validating file")
            latest = self.repository.get_document(document["id"]) or document
            latest["stored_path"] = str(self._materialize(latest))
            document = latest
            path = Path(document["stored_path"])
            if document["kind"] == "pdf":
                current_job = self.repository.get_job(job_id) or {}
                if current_job.get("change_request_id"):
                    change = self.repository.get_change_request(
                        current_job["change_request_id"]
                    )
                    if change and change.get("status") == "approved":
                        self._index_pdf(job_id, document)
                        return
                    if change and change.get("status") == "pending":
                        self.repository.update_document_status(
                            document["id"], "awaiting_approval"
                        )
                        self.repository.update_job(
                            job_id, "awaiting_approval", 60,
                            "PDF validated and awaiting Admin approval",
                            current_job["change_request_id"],
                        )
                        return
                if document.get("date_status") in {"confirmed", "fallback"} and document.get(
                    "effective_date"
                ):
                    self._request_pdf_approval(job_id, document, actor_role)
                    return
                if document.get("date_status") == "detected" and document.get("reporting_date"):
                    self.repository.update_document_status(
                        document["id"], "awaiting_date_confirmation"
                    )
                    self.repository.update_job(
                        job_id, "awaiting_date_confirmation", 45,
                        f"Confirm detected report date: {document['reporting_date']}",
                    )
                    return
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
                    resolved = self.repository.get_document(document["id"])
                    resolved["stored_path"] = str(path)
                    self._request_pdf_approval(job_id, resolved, actor_role)
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
        document["stored_path"] = str(self._materialize(document))
        self.repository.update_document_date(
            document["id"], reporting_date, reporting_date, "confirmed"
        )
        resolved = self.repository.get_document(document["id"])
        resolved["stored_path"] = document["stored_path"]
        self._request_pdf_approval(job_id, resolved, actor_role)
        return self.repository.get_job(job_id)

    def _request_pdf_approval(
        self, job_id: str, document: dict, actor_role: str
    ) -> None:
        """Create the mandatory Admin gate before any PDF is embedded."""
        change = self.repository.create_pdf_approval(job_id, document, actor_role)
        self.repository.update_document_status(document["id"], "awaiting_approval")
        self.repository.update_job(
            job_id, "awaiting_approval", 60,
            "PDF validated and awaiting Admin approval", change["id"],
        )

    def resume_approved_pdf(self, job_id: str) -> dict:
        """Resume an approved PDF without requiring the approver request to stay open."""
        job = self.repository.get_job(job_id)
        if not job or job.get("kind") != "pdf":
            raise KeyError("PDF ingestion job not found")
        document = self.repository.get_document(job["document_id"])
        if not document:
            raise KeyError("PDF document not found")
        document["stored_path"] = str(self._materialize(document))
        self.repository.update_document_status(document["id"], "processing")
        self.repository.update_job(job_id, "processing", 65, "Admin approved PDF ingestion")
        self._submit_background(self._index_pdf, job_id, document)
        return self.repository.get_job(job_id)

    def _index_pdf(self, job_id: str, document: dict) -> None:
        """Extract, embed, and publish one date-resolved PDF."""
        try:
            chunks = extract_pdf_chunks(Path(document["stored_path"]), document)
            self.repository.update_document_status(document["id"], "embedding")
            self.repository.update_job(
                job_id, "embedding", 55, f"Embedding {len(chunks)} chunks"
            )
            self.rag_store.add_chunks(chunks)
            self.repository.complete_document_ingestion(
                document["id"], job_id, len(chunks)
            )
            Path(document["stored_path"]).unlink(missing_ok=True)
        except Exception as error:
            logger.exception(
                "pdf_indexing_failed",
                extra={"job_id": job_id, "document_id": document["id"], "kind": "pdf"},
            )
            self.repository.update_document_status(document["id"], "failed")
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
        self._cached_path(document).unlink(missing_ok=True)
        remove = getattr(self.repository, "delete_document_record_and_storage", None)
        if remove:
            return remove(document_id) or {}
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
        self._cached_path(document).unlink(missing_ok=True)
        return self.repository.delete_failed_ingestion_records(job_id, actor_role)

    def _cached_path(self, document: dict) -> Path:
        """Resolve the bounded local processing cache for a stored object."""
        if document.get("stored_path"):
            return Path(document["stored_path"])
        return (
            self.upload_dir / document["project_code"]
            / f"{document['checksum'][:12]}-{document['filename']}"
        )

    def _materialize(self, document: dict) -> Path:
        """Restore a source object from private Storage into the bounded local cache."""
        path = self._cached_path(document)
        if path.exists():
            return path
        loader = getattr(self.repository, "load_document_file", None)
        if not loader:
            raise ValueError("The uploaded source file is no longer available")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(loader(document))
        return path

    def close(self) -> None:
        """Stop accepting background work and release vector-store resources."""
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.rag_store.close()

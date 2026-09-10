"""Duplicate-safe bulk PDF registration and pgvector indexing for ProSight."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from prosight.config import get_settings
from prosight.db.postgres import PostgresRepository
from prosight.ingestion.pdf import detect_reporting_date, extract_pdf_chunks
from prosight.rag.pgvector_store import PgVectorStore
from prosight.storage import SupabaseStorage


MAX_PDF_BYTES = 20 * 1024 * 1024
COMPANY_FOLDER = "Company"
COMPANY_SCOPE = "COMPANY"


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def discover(root: Path) -> list[dict]:
    if not root.is_dir():
        raise ValueError(f"PDF root does not exist: {root}")
    rows = []
    for path in sorted(root.rglob("*.pdf")):
        relative = path.relative_to(root)
        if len(relative.parts) < 2:
            raise ValueError(f"Every PDF must be inside a project or Company folder: {relative}")
        if path.stat().st_size <= 0 or path.stat().st_size > MAX_PDF_BYTES:
            raise ValueError(f"PDF size is invalid or exceeds 20 MB: {relative}")
        if path.read_bytes()[:5] != b"%PDF-":
            raise ValueError(f"File content is not a PDF: {relative}")
        folder = relative.parts[0]
        rows.append({
            "path": path,
            "relative_path": relative.as_posix(),
            "project_code": COMPANY_SCOPE if folder.casefold() == COMPANY_FOLDER.casefold() else folder,
            "checksum": checksum(path),
        })
    return rows


def existing_checksums(repository: PostgresRepository) -> dict[str, dict]:
    with closing(repository.connect()) as db:
        rows = db.execute(
            """SELECT id,project_code,filename,checksum,status,approval_status,index_status
               FROM documents WHERE kind='pdf'"""
        ).fetchall()
    return {row["checksum"]: dict(row) for row in rows}


def project_codes(repository: PostgresRepository) -> set[str]:
    with closing(repository.connect()) as db:
        return {row["code"] for row in db.execute("SELECT code FROM projects").fetchall()}


def approval_preview(document: dict) -> dict:
    return {
        "before": None,
        "after": {
            "document_id": document["id"],
            "project_code": document["project_code"],
            "filename": document["filename"],
            "kind": "pdf",
            "checksum": document["checksum"],
            "reporting_date": document.get("reporting_date"),
            "effective_date": document.get("effective_date"),
            "date_status": document.get("date_status"),
            "approval_status": "awaiting_approval",
            "index_status": "not_indexed",
            "warnings": [],
        },
        "warnings": [],
    }


def index_one(
    repository: PostgresRepository,
    store: PgVectorStore,
    storage: SupabaseStorage,
    row: dict,
    upload_root: Path,
) -> dict:
    source = row["path"]
    destination_dir = upload_root / row["project_code"]
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{row['checksum'][:12]}-{source.name}"
    if destination.exists() and checksum(destination) != row["checksum"]:
        raise ValueError(f"Managed destination has unexpected content: {destination}")
    if not destination.exists():
        shutil.copy2(source, destination)

    document = repository.create_document(
        row["project_code"], source.name, "pdf", row["checksum"], str(destination.resolve())
    )
    job = repository.create_job(document["id"])
    try:
        reporting_date = detect_reporting_date(source)
        effective_date = reporting_date or datetime.now(timezone.utc).date().isoformat()
        repository.update_document_date(
            document["id"], reporting_date, effective_date,
            "detected" if reporting_date else "fallback",
        )
        document = repository.get_document(document["id"])
        change = repository.create_document_approval_request(
            document, "admin", job["id"], approval_preview(document)
        )
        repository.decide_change_request(change["id"], "approved", "admin")
        document = repository.get_document(document["id"])
        bucket, object_path = storage.upload_pdf(document, source)
        repository.update_document_storage(document["id"], bucket, object_path)
        document = repository.get_document(document["id"])
        repository.update_document_index_status(document["id"], "indexing")
        chunks = extract_pdf_chunks(source, document)
        repository.update_job(job["id"], "processing", 55, f"Embedding {len(chunks)} chunks")
        store.add_chunks(chunks)
        repository.update_document_status(document["id"], "ready")
        repository.update_document_index_status(document["id"], "ready")
        repository.update_job(job["id"], "ready", 100, f"Indexed {len(chunks)} chunks")
        return {"document_id": document["id"], "chunks": len(chunks)}
    except Exception:
        try:
            store.delete_document(document["id"])
            repository.update_document_status(document["id"], "approved")
            repository.update_document_index_status(document["id"], "failed")
            repository.update_job(job["id"], "failed", 100, "Bulk PDF indexing failed")
        finally:
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--upload-root", type=Path, default=Path("data/uploads"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url:
        parser.error("PROSIGHT_DATABASE_URL is required")
    rows = discover(args.root.resolve())
    if len({row["checksum"] for row in rows}) != len(rows):
        raise ValueError("The source tree contains duplicate PDF content")

    repository = PostgresRepository(settings.database_url)
    try:
        repository.ensure_schema()
        known_projects = project_codes(repository)
        unknown = sorted({row["project_code"] for row in rows} - known_projects - {COMPANY_SCOPE})
        if unknown:
            raise ValueError("Unknown project folders: " + ", ".join(unknown))
        existing = existing_checksums(repository)
        pending = [row for row in rows if row["checksum"] not in existing]
        summary = {
            "source_pdfs": len(rows),
            "existing_skipped": len(rows) - len(pending),
            "pending": len(pending),
            "company_scope": COMPANY_SCOPE,
            "apply": args.apply,
        }
        print(json.dumps(summary))
        if not args.apply:
            return

        store = PgVectorStore(repository)
        storage = SupabaseStorage(
            settings.supabase_url, settings.supabase_secret_key,
            settings.supabase_storage_bucket,
        )
        try:
            for position, row in enumerate(pending, start=1):
                # Recheck before every write so a concurrent importer cannot create
                # a second logical document with the same content in another scope.
                duplicate = existing_checksums(repository).get(row["checksum"])
                if duplicate:
                    print(json.dumps({"status": "skipped", "path": row["relative_path"]}))
                    continue
                result = index_one(repository, store, storage, row, args.upload_root.resolve())
                print(json.dumps({
                    "status": "indexed", "position": position, "total": len(pending),
                    "path": row["relative_path"], "project_code": row["project_code"], **result,
                }))
        finally:
            storage.close()
            store.close()
    finally:
        repository.close()


if __name__ == "__main__":
    main()

"""Upload approved ProSight PDFs to private Supabase Storage without overwrites."""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import closing
from pathlib import Path

from prosight.config import get_settings
from prosight.db.postgres import PostgresRepository
from prosight.storage import SupabaseStorage


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--verify", action="store_true",
        help="Download every referenced object and verify its SHA-256 checksum.",
    )
    args = parser.parse_args()
    settings = get_settings()
    repository = PostgresRepository(settings.database_url)
    storage = None
    try:
        repository.ensure_schema()
        with closing(repository.connect()) as db:
            documents = [dict(row) for row in db.execute(
                """SELECT * FROM documents
                   WHERE kind='pdf' AND approval_status='approved'
                   ORDER BY project_code,filename"""
            ).fetchall()]
        pending = [item for item in documents if not item.get("storage_object_path")]
        print(json.dumps({
            "approved_pdfs": len(documents),
            "already_stored": len(documents) - len(pending),
            "pending": len(pending),
            "apply": args.apply,
        }))
        if not args.apply and not args.verify:
            return
        storage = SupabaseStorage(
            settings.supabase_url, settings.supabase_secret_key,
            settings.supabase_storage_bucket,
        )
        if args.apply:
            for position, document in enumerate(pending, start=1):
                source = Path(document["stored_path"])
                if not source.is_file():
                    raise ValueError(f"Approved PDF original is unavailable: {document['id']}")
                bucket, object_path = storage.upload_pdf(document, source)
                repository.update_document_storage(document["id"], bucket, object_path)
                document.update(storage_bucket=bucket, storage_object_path=object_path)
                print(json.dumps({
                    "status": "stored", "position": position, "total": len(pending),
                    "document_id": document["id"], "project_code": document["project_code"],
                    "filename": document["filename"], "object_path": object_path,
                }))
        if args.verify:
            config = storage.bucket_config()
            verified = 0
            for document in documents:
                bucket = document.get("storage_bucket")
                object_path = document.get("storage_object_path")
                if not bucket or not object_path:
                    raise RuntimeError(f"Approved PDF has no Storage reference: {document['id']}")
                if bucket != settings.supabase_storage_bucket:
                    raise RuntimeError(f"Unexpected Storage bucket for document: {document['id']}")
                if object_path != storage.object_path(document):
                    raise RuntimeError(f"Unexpected Storage object path: {document['id']}")
                payload = storage.download(bucket, object_path)
                if hashlib.sha256(payload).hexdigest() != document["checksum"]:
                    raise RuntimeError(f"Storage checksum mismatch: {document['id']}")
                verified += 1
            print(json.dumps({
                "status": "verified",
                "documents": len(documents),
                "objects_downloaded": verified,
                "unique_object_paths": len({d["storage_object_path"] for d in documents}),
                "bucket": config.get("id"),
                "public": config.get("public"),
                "file_size_limit": config.get("file_size_limit"),
                "allowed_mime_types": config.get("allowed_mime_types"),
            }))
    finally:
        if storage:
            storage.close()
        repository.close()


if __name__ == "__main__":
    main()

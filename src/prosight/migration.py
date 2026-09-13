"""Idempotent migration from the legacy SQLite store to hosted Supabase."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .config import get_settings
from .repository import DEFAULT_DATA, DEFAULT_DB
from .supabase_gateway import SupabaseGateway


class SupabaseMigrator:
    """Copy legacy rows and files while retaining stable business identifiers."""

    TABLES = (
        "projects", "documents", "ingestion_jobs", "change_requests", "audit_events",
        "notifications", "portfolio_imports", "portfolio_import_jobs",
        "manpower_assignments", "project_invoices", "project_schedule_activities",
    )

    def __init__(self, sqlite_path: str | Path = DEFAULT_DB, dry_run: bool = False):
        self.sqlite_path = Path(sqlite_path)
        self.dry_run = dry_run
        self.settings = get_settings()
        self.gateway = None if dry_run else SupabaseGateway(service=True)
        self.admin_id: str | None = None
        self.pdf_document_ids: set[str] = set()
        self.ready_pdf_ids: set[str] = set()
        self.failed_pdf_ids: set[str] = set()

    @staticmethod
    def _decode(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value

    def run(self) -> dict[str, Any]:
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {self.sqlite_path}")
        with sqlite3.connect(self.sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            existing = {row[0] for row in connection.execute(
                "select name from sqlite_master where type='table'"
            )}
            source_counts = {
                table: connection.execute(f"select count(*) from {table}").fetchone()[0]
                for table in self.TABLES if table in existing
            }
            report: dict[str, Any] = {
                "dry_run": self.dry_run, "sqlite": str(self.sqlite_path.resolve()),
                "source_counts": source_counts, "migrated_counts": {}, "uploaded_files": 0,
                "file_checksums": {"checked": 0, "matched": 0, "mismatches": []},
                "rag_reindex": {"documents": 0, "chunks": 0, "skipped": 0, "errors": []},
                "missing_files": [],
            }
            if self.dry_run:
                report["checks"] = self._dry_checks(connection, existing)
                return report
            self.admin_id = self._bootstrap_admin()
            for table in self.TABLES:
                if table not in existing:
                    continue
                rows = [dict(row) for row in connection.execute(f"select * from {table}")]
                converted = [self._convert(table, row) for row in rows]
                if converted:
                    self.gateway.insert(table, converted, upsert=True)
                report["migrated_counts"][table] = len(converted)
                if table in {"documents", "portfolio_imports"}:
                    for old, new in zip(rows, converted):
                        source = Path(old.get("stored_path") or "")
                        if source.is_file():
                            self.gateway.upload(new["storage_bucket"], new["storage_key"],
                                                source.read_bytes(), upsert=True)
                            report["uploaded_files"] += 1
                            remote = self.gateway.download(new["storage_bucket"], new["storage_key"])
                            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                            remote_hash = hashlib.sha256(remote).hexdigest()
                            report["file_checksums"]["checked"] += 1
                            if source_hash == remote_hash:
                                report["file_checksums"]["matched"] += 1
                            else:
                                report["file_checksums"]["mismatches"].append(new["storage_key"])
                            if table == "documents" and new.get("kind") == "pdf":
                                self._reindex_pdf(source, new, report)
                        else:
                            report["missing_files"].append({
                                "table": table, "id": new["id"],
                                "source": str(source),
                            })
                            if table == "documents" and new.get("kind") == "pdf":
                                self.failed_pdf_ids.add(str(new["id"]))
                                self.gateway.update(
                                    "documents", {"status": "failed"}, id=f"eq.{new['id']}"
                                )
            self._ensure_pdf_jobs()
            report["target_counts"] = {
                table: self.gateway.count(table) for table in source_counts
            }
            report["verified"] = all(
                report["target_counts"].get(table, 0) >= count
                for table, count in source_counts.items()
            ) and not report["file_checksums"]["mismatches"] \
                and not report["rag_reindex"]["errors"] and not report["missing_files"]
            return report

    def _bootstrap_admin(self) -> str:
        email = self.settings.bootstrap_admin_email.strip().lower()
        if not email:
            raise RuntimeError("PROSIGHT_BOOTSTRAP_ADMIN_EMAIL is required")
        user = None
        for page in range(1, 101):
            users = self.gateway.request(
                "GET", f"/auth/v1/admin/users?per_page=1000&page={page}"
            ) or {}
            user = next((item for item in users.get("users", [])
                         if str(item.get("email", "")).lower() == email), None)
            if user or len(users.get("users", [])) < 1000:
                break
        if not user:
            raise RuntimeError(
                "Bootstrap administrator must sign up once before migration; no matching Auth user was found"
            )
        user_id = user["id"]
        self.gateway.update("profiles", {"role": "admin"}, id=f"eq.{user_id}")
        projects = self.gateway.select("projects", select="code")
        if projects:
            self.gateway.insert("project_memberships", [
                {"user_id": user_id, "project_code": item["code"]} for item in projects
            ], upsert=True)
        return user_id

    def _dry_checks(self, connection: sqlite3.Connection, tables: set[str]) -> list[str]:
        checks = ["Supabase credentials were not used"]
        if "projects" in tables:
            codes = [row[0] for row in connection.execute("select code from projects")]
            checks.append(f"{len(codes)} unique project codes")
        for table in ("documents", "portfolio_imports"):
            if table in tables:
                missing = sum(1 for row in connection.execute(f"select stored_path from {table}")
                              if not Path(row[0]).is_file())
                checks.append(f"{table}: {missing} missing source files")
        return checks

    def _convert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        result.pop("stored_path", None)
        result.pop("seed_migration", None)
        for key in ("payload", "preview", "before_json", "after_json", "summary_json", "data_json"):
            if key in result and result[key] is not None:
                result[key] = self._decode(result[key])
        if table == "documents":
            result.update(
                uploaded_by=self.admin_id, storage_bucket="project-documents",
                storage_key=f"{row['project_code']}/{row['id']}/{row['filename']}",
            )
            if result.get("kind") == "pdf":
                result["status"] = "embedding"
                self.pdf_document_ids.add(str(result["id"]))
        elif table == "ingestion_jobs" and str(result.get("document_id")) in self.pdf_document_ids:
            result.update(status="embedding", progress=60, message="Queued for pgvector re-indexing")
        elif table == "portfolio_imports":
            result.update(
                uploaded_by=self.admin_id, storage_bucket="portfolio-imports",
                storage_key=f"{self.admin_id}/{row['id']}/{row['filename']}",
            )
        elif table == "change_requests":
            legacy_role = row.get("requested_by")
            result.update(requested_by=self.admin_id, requested_role=(
                legacy_role if legacy_role in {"employee","project_manager","planning_engineer","admin"}
                else "employee"
            ))
            result["decided_by"] = self.admin_id if row.get("decided_by") else None
            result["decided_role"] = row.get("decided_by") if row.get("decided_by") in {
                "employee","project_manager","planning_engineer","admin"
            } else None
        elif table == "audit_events":
            result["actor_user_id"] = self.admin_id
        elif table == "notifications":
            result["recipient_user_id"] = self.admin_id
            result.pop("recipient_role", None)
        return result

    def _reindex_pdf(self, source: Path, document: dict[str, Any], report: dict[str, Any]) -> None:
        """Re-extract source text into pgvector without importing legacy vectors."""
        from .ingestion.pdf import extract_pdf_chunks
        from .rag import RAGStore

        try:
            chunks = extract_pdf_chunks(source, document)
            expected = {item["id"]: item["content_hash"] for item in chunks}
            existing = self.gateway.select(
                "document_chunks", select="id,content_hash,embedding_status",
                document_id=f"eq.{document['id']}",
            )
            actual = {item["id"]: item["content_hash"] for item in existing}
            if actual == expected:
                if existing and all(item["embedding_status"] == "ready" for item in existing):
                    self.ready_pdf_ids.add(str(document["id"]))
                    self.gateway.update(
                        "documents", {"status": "ready"}, id=f"eq.{document['id']}"
                    )
                report["rag_reindex"]["skipped"] += 1
                return
            if existing:
                self.gateway.delete("document_chunks", document_id=f"eq.{document['id']}")
            RAGStore().add_chunks(chunks)
            self.gateway.update(
                "documents", {"status": "embedding"}, id=f"eq.{document['id']}"
            )
            report["rag_reindex"]["documents"] += 1
            report["rag_reindex"]["chunks"] += len(chunks)
        except Exception as error:
            self.failed_pdf_ids.add(str(document["id"]))
            self.gateway.update(
                "documents", {"status": "failed"}, id=f"eq.{document['id']}"
            )
            report["rag_reindex"]["errors"].append({
                "document_id": document["id"], "error": str(error),
            })

    def _ensure_pdf_jobs(self) -> None:
        """Guarantee migrated PDFs expose an embedding lifecycle job."""
        for document_id in self.pdf_document_ids:
            if document_id in self.ready_pdf_ids:
                state = {"status": "ready", "progress": 100, "message": "Document ready"}
            elif document_id in self.failed_pdf_ids:
                state = {"status": "failed", "progress": 100, "message": "PDF re-indexing failed"}
            else:
                state = {"status": "embedding", "progress": 60,
                         "message": "Queued for pgvector re-indexing"}
            jobs = self.gateway.select(
                "ingestion_jobs", select="id", document_id=f"eq.{document_id}", limit="1"
            )
            if jobs:
                self.gateway.update("ingestion_jobs", state, id=f"eq.{jobs[0]['id']}")
                continue
            job_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"prosight-pgvector-reindex:{document_id}"))
            self.gateway.insert("ingestion_jobs", {
                "id": job_id, "document_id": document_id, **state,
            }, upsert=True)


def seed_projects_from_json(dry_run: bool = False) -> dict[str, Any]:
    """Seed canonical projects when no SQLite database is available."""
    projects = json.loads(DEFAULT_DATA.read_text(encoding="utf-8"))["projects"]
    if not dry_run:
        gateway = SupabaseGateway(service=True)
        gateway.insert("projects", [{
            **{key: project.get(key) for key in (
                "code","name","status","client","location","contract_value_usd",
                "planned_start","planned_finish","revised_finish","reporting_date",
                "baseline_progress","revised_progress","actual_progress",
            )}, "payload": project,
        } for project in projects], upsert=True)
    return {"dry_run": dry_run, "seeded_projects": len(projects)}

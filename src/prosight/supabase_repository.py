"""Supabase/PostgREST repository preserving ProSight's domain contract."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from .auth import current_auth
from .portfolio_contract import (
    INVOICE_DB_COLUMNS,
    MANPOWER_DB_COLUMNS,
    with_invoice_legacy_aliases,
)
from .repository import ProjectRepository
from .supabase_gateway import SupabaseError, SupabaseGateway


class SupabaseProjectRepository:
    """Production repository backed by Supabase PostgreSQL and RLS."""

    def __init__(self) -> None:
        self.user = SupabaseGateway()
        self.service = SupabaseGateway(service=True)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @property
    def db(self) -> SupabaseGateway:
        """Use RLS for requests and the service role only in detached workers."""
        return self.user if current_auth.get() else self.service

    def _actor(self) -> tuple[str, str]:
        auth = current_auth.get()
        if not auth:
            raise PermissionError("An authenticated user is required")
        return auth.user_id, auth.role

    def _ensure(self) -> None:
        """Schema is managed through Supabase migrations, not at runtime."""

    ensure_schema = _ensure

    def initialize(self, source=None) -> None:
        raise RuntimeError("Use `prosight migrate-supabase` to seed Supabase")

    @staticmethod
    def _project_row(project: dict[str, Any]) -> dict[str, Any]:
        fields = (
            "code", "name", "status", "client", "location", "contract_value_usd",
            "planned_start", "planned_finish", "revised_finish", "reporting_date",
            "baseline_progress", "revised_progress", "actual_progress",
        )
        return {**{field: project.get(field) for field in fields}, "payload": project}

    @staticmethod
    def _decode_json(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                return value
        return value

    @staticmethod
    def _decorate(project: dict[str, Any], user_role: str) -> dict[str, Any]:
        return ProjectRepository._decorate(project, user_role)

    def list_projects(self, status: str | None = None, user_role: str = "employee") -> list[dict[str, Any]]:
        rows = self.user.rpc("list_authorized_projects", {
            "project_status": status.lower() if status else None,
        })
        return [self._decorate(dict(self._decode_json(row["payload"])), user_role) for row in rows]

    def find_project(self, term: str, user_role: str = "employee") -> dict[str, Any] | None:
        value = term.strip()
        if not value:
            return None
        rows = self.user.rpc("find_authorized_project", {
            "search_term": value,
        })
        return self._decorate(dict(self._decode_json(rows[0]["payload"])), user_role) if rows else None

    def portfolio_summary(self, user_role: str = "employee") -> dict[str, Any]:
        projects = self.list_projects(user_role=user_role)
        groups = {status: [item for item in projects if item["status"] == status]
                  for status in ("active", "completed", "future")}
        return {
            "project_count": len(projects),
            "counts": {key: len(items) for key, items in groups.items()},
            "contract_value_usd": {key: sum(float(item["contract_value_usd"]) for item in items)
                                   for key, items in groups.items()},
            "delayed_active_projects": [item["code"] for item in groups["active"] if item["delay_days"] > 0],
        }

    def update_project(self, project_code: str, updates: dict[str, Any], actor_role: str) -> dict[str, Any]:
        before = self.find_project(project_code, actor_role)
        if not before:
            raise KeyError("Project not found")
        after = {**before, **updates, "code": project_code}
        for calculated in ("delay_days", "variance_pct"):
            after.pop(calculated, None)
        self.user.update(
            "projects", {**self._project_row(after), "updated_at": self._now()},
            returning=False, code=f"eq.{project_code}",
        )
        self._audit(actor_role, "project_update", "project", project_code, before, after)
        return self._decorate(after, actor_role)

    def create_document(self, project_code: str, filename: str, kind: str, checksum: str, stored_path: str) -> dict[str, Any]:
        actor_id, _ = self._actor()
        document_id = str(uuid.uuid4())
        storage_key = f"{project_code}/{document_id}/{filename}"
        try:
            rows = self.db.insert("documents", {
                "id": document_id, "project_code": project_code, "uploaded_by": actor_id,
                "filename": filename, "kind": kind, "checksum": checksum,
                "storage_key": storage_key, "status": "queued",
            })
        except SupabaseError as error:
            if error.status == 409 or "duplicate" in str(error).lower():
                raise ValueError("This file has already been uploaded to the project") from error
            raise
        result = rows[0]
        result["stored_path"] = stored_path
        return result

    def store_document_file(self, document: dict[str, Any], path) -> None:
        self.user.upload(document["storage_bucket"], document["storage_key"], path.read_bytes())

    def load_document_file(self, document: dict[str, Any]) -> bytes:
        """Download a private source object for a detached ingestion task."""
        return self.service.download(document["storage_bucket"], document["storage_key"])

    def store_portfolio_file(self, record: dict[str, Any], path) -> None:
        self.user.upload(record["storage_bucket"], record["storage_key"], path.read_bytes())

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        rows = self.db.select("documents", id=f"eq.{document_id}", limit="1")
        return rows[0] if rows else None

    def list_documents(self, project_code: str) -> list[dict[str, Any]]:
        return self.db.select(
            "documents",
            select="id,project_code,filename,kind,checksum,status,reporting_date,effective_date,date_status,created_at,updated_at",
            project_code=f"eq.{project_code}", status="neq.failed", order="created_at.desc",
        )

    def update_document_status(self, document_id: str, status: str) -> None:
        self.db.update("documents", {"status": status, "updated_at": self._now()}, id=f"eq.{document_id}")

    def complete_document_ingestion(
        self, document_id: str, job_id: str, chunk_count: int
    ) -> None:
        """Atomically publish a fully embedded document and clear its completed job."""
        self.service.rpc("complete_document_ingestion", {
            "target_document_id": document_id,
            "target_job_id": job_id,
            "chunk_count": chunk_count,
        })
        # Safe with both RPC versions: the current migration deletes atomically,
        # while this clears the row when an older hosted function is still active.
        self.service.delete(
            "ingestion_jobs", id=f"eq.{job_id}", document_id=f"eq.{document_id}"
        )

    def update_document_date(self, document_id: str, reporting_date: str | None,
                             effective_date: str, date_status: str) -> None:
        self.db.update("documents", {
            "reporting_date": reporting_date, "effective_date": effective_date,
            "date_status": date_status, "updated_at": self._now(),
        }, id=f"eq.{document_id}")

    def delete_document_record(self, document_id: str) -> dict[str, Any] | None:
        rows = self.db.delete("documents", id=f"eq.{document_id}")
        return rows[0] if rows else None

    def create_job(self, document_id: str) -> dict[str, Any]:
        return self.service.insert("ingestion_jobs", {
            "id": str(uuid.uuid4()), "document_id": document_id, "status": "queued",
            "progress": 0, "created_at": self._now(), "updated_at": self._now(),
        })[0]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        rows = self.db.select("ingestion_jobs", id=f"eq.{job_id}", limit="1")
        if not rows:
            return None
        job = rows[0]
        documents = self.db.select(
            "documents",
            select="id,project_code,kind,filename,checksum,reporting_date,effective_date,date_status",
            id=f"eq.{job['document_id']}",
            limit="1",
        )
        document = documents[0] if documents else {}
        return {
            **document,
            "detected_reporting_date": document.get("reporting_date"),
            **job,
        }

    def list_jobs(self, project_code: str) -> list[dict[str, Any]]:
        documents = self.db.select(
            "documents",
            select="id,kind,filename,checksum,reporting_date,effective_date,date_status",
            project_code=f"eq.{project_code}",
        )
        by_id = {item["id"]: item for item in documents}
        ids = list(by_id)
        if not ids:
            return []
        joined = ",".join(ids)
        rows = self.db.select("ingestion_jobs", document_id=f"in.({joined})", order="created_at.desc")
        return [
            {
                **{key: value for key, value in by_id.get(row["document_id"], {}).items()
                   if key != "id"},
                "detected_reporting_date": by_id.get(row["document_id"], {}).get(
                    "reporting_date"
                ),
                **row,
            }
            for row in rows
        ]

    def update_job(self, job_id: str, status: str, progress: int, message: str | None = None,
                   change_request_id: str | None = None) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "status": status, "progress": progress, "message": message, "updated_at": self._now()
        }
        if change_request_id is not None:
            payload["change_request_id"] = change_request_id
        rows = self.service.update("ingestion_jobs", payload, id=f"eq.{job_id}")
        return rows[0] if rows else None

    def claim_job(self, job_id: str) -> bool:
        """Atomically claim a queued job through a conditional update."""
        rows = self.service.update(
            "ingestion_jobs",
            {"status": "processing", "progress": 5, "message": "Claimed for processing",
             "updated_at": self._now()},
            id=f"eq.{job_id}", status="eq.queued",
        )
        return bool(rows)

    def recover_interrupted_jobs(self) -> list[dict[str, Any]]:
        """Reset interrupted PDFs to queued and return them for bounded resubmission."""
        self.service.delete("ingestion_jobs", status="eq.ready")
        jobs = self.service.select(
            "ingestion_jobs", status="in.(queued,processing,embedding)", order="created_at.asc"
        )
        recovered: list[dict[str, Any]] = []
        for job in jobs:
            documents = self.service.select(
                "documents", id=f"eq.{job['document_id']}", limit="1"
            )
            if not documents:
                self.update_job(job["id"], "failed", 100, "The source document no longer exists")
                continue
            document = documents[0]
            if document["kind"] != "pdf":
                self.update_job(
                    job["id"], "failed", 100,
                    "Workbook processing was interrupted; upload the workbook again",
                )
                self.update_document_status(document["id"], "failed")
                continue
            self.service.update(
                "ingestion_jobs",
                {"status": "queued", "progress": 0, "message": "Recovered after restart",
                 "updated_at": self._now()},
                returning=False, id=f"eq.{job['id']}",
            )
            self.update_document_status(document["id"], "queued")
            recovered.append({"job": {**job, "status": "queued"}, "document": document})
        return recovered

    def create_change_request(self, action: str, project_code: str, payload: dict[str, Any],
                              preview: dict[str, Any], requested_by: str) -> dict[str, Any]:
        actor_id, role = self._actor()
        change = self.db.insert("change_requests", {
            "id": str(uuid.uuid4()), "action": action, "project_code": project_code,
            "payload": payload, "preview": preview, "status": "pending",
            "requested_by": actor_id, "requested_role": role,
        })[0]
        admins = self.service.select("profiles", select="id", role="eq.admin")
        if admins:
            self.service.insert("notifications", [{
                "recipient_user_id": item["id"], "event_type": "approval_required",
                "project_code": project_code, "change_request_id": change["id"],
                "title": "Approval required",
                "message": f"{role.replace('_', ' ').title()} submitted a {action.replace('_', ' ')} request.",
            } for item in admins], upsert=True)
        return change

    def create_pdf_approval(
        self, job_id: str, document: dict[str, Any], requested_by: str
    ) -> dict[str, Any]:
        """Create the mandatory approval record for a validated PDF."""
        auth = current_auth.get()
        requester_id = auth.user_id if auth else document.get("uploaded_by")
        requester_role = auth.role if auth else requested_by
        if not requester_id:
            raise PermissionError("The PDF uploader could not be identified")
        change = self.service.insert("change_requests", {
            "id": str(uuid.uuid4()), "action": "pdf_ingestion",
            "project_code": document["project_code"],
            "payload": {"job_id": job_id, "document_id": document["id"]},
            "preview": {
                "before": None,
                "after": {
                    "filename": document["filename"],
                    "reporting_date": document.get("reporting_date"),
                    "effective_date": document.get("effective_date"),
                    "date_status": document.get("date_status"),
                },
            },
            "status": "pending", "requested_by": requester_id,
            "requested_role": requester_role,
        })[0]
        admins = self.service.select("profiles", select="id", role="eq.admin")
        if admins:
            self.service.insert("notifications", [{
                "recipient_user_id": item["id"], "event_type": "approval_required",
                "project_code": document["project_code"],
                "change_request_id": change["id"], "title": "PDF approval required",
                "message": f"{requester_role.replace('_', ' ').title()} uploaded {document['filename']}.",
            } for item in admins], upsert=True)
        return change

    def get_change_request(self, change_id: str) -> dict[str, Any] | None:
        rows = self.db.select("change_requests", id=f"eq.{change_id}", limit="1")
        return rows[0] if rows else None

    def update_pending_project_change(self, change_id: str, project: dict[str, Any], actor_role: str) -> dict[str, Any]:
        if actor_role not in {"project_manager", "admin"}:
            raise PermissionError("This role cannot edit a project import")
        change = self.get_change_request(change_id)
        if not change:
            raise KeyError("Change request not found")
        if change["status"] != "pending" or change["action"] != "excel_import":
            raise ValueError("Only pending Excel imports can be edited")
        payload = {"projects": [{**change["payload"]["projects"][0], **project}]}
        preview = {**change["preview"], "after": payload["projects"][0]}
        rows = self.db.update("change_requests", {
            "project_code": project["code"], "payload": payload, "preview": preview,
        }, id=f"eq.{change_id}", status="eq.pending")
        return rows[0] if rows else change

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return self.db.select("change_requests", status="eq.pending", order="created_at.asc")

    def decide_change_request(self, change_id: str, decision: str, actor_role: str) -> dict[str, Any]:
        if actor_role != "admin":
            raise PermissionError("Admin approval is required")
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be approved or rejected")
        actor_id, _ = self._actor()
        change = self.get_change_request(change_id)
        if not change:
            raise KeyError("Change request not found")
        if change["status"] != "pending":
            raise ValueError("Change request has already been decided")
        if decision == "approved":
            self._apply_change(change)
        rows = self.db.update("change_requests", {
            "status": decision, "decided_by": actor_id, "decided_role": actor_role,
            "decided_at": self._now(),
        }, id=f"eq.{change_id}", status="eq.pending")
        jobs = self.service.select(
            "ingestion_jobs", select="id,document_id",
            change_request_id=f"eq.{change_id}",
        )
        terminal = (
            "processing"
            if decision == "approved" and change["action"] == "pdf_ingestion"
            else "ready" if decision == "approved" else "rejected"
        )
        if jobs:
            for document_id in {job["document_id"] for job in jobs}:
                self.service.update(
                    "documents", {"status": terminal, "updated_at": self._now()},
                    returning=False, id=f"eq.{document_id}",
                )
            if terminal == "ready":
                self.service.delete(
                    "ingestion_jobs", change_request_id=f"eq.{change_id}"
                )
            else:
                self.service.update(
                    "ingestion_jobs",
                    {"status": terminal, "progress": 65 if terminal == "processing" else 100,
                     "message": f"Change {decision}", "updated_at": self._now()},
                    returning=False, change_request_id=f"eq.{change_id}",
                )
        self.service.update("notifications", {"read_at": self._now()},
                            change_request_id=f"eq.{change_id}", event_type="eq.approval_required")
        if change["requested_by"] != actor_id:
            self.service.insert("notifications", {
                "recipient_user_id": change["requested_by"], "event_type": f"change_{decision}",
                "project_code": change["project_code"], "change_request_id": change_id,
                "title": f"Change {decision}",
                "message": f"Your {change['action'].replace('_', ' ')} request was {decision}.",
            }, upsert=True)
        self._audit(actor_role, decision, "change_request", change_id,
                    change["preview"].get("before"), change["preview"].get("after"))
        return rows[0] if rows else change

    def _apply_change(self, change: dict[str, Any]) -> None:
        action, payload, code = change["action"], change["payload"], change["project_code"]
        if action == "excel_import":
            for project in payload.get("projects", []):
                self.service.insert("projects", self._project_row(project), upsert=True)
        elif action == "pdf_ingestion":
            return
        elif action == "record_delete":
            self.service.delete("projects", code=f"eq.{code}")
        elif action in {"contact_update", "activity_import", "resource_import", "milestone_update"}:
            rows = self.service.select("projects", select="payload", code=f"eq.{code}", limit="1")
            if not rows:
                raise ValueError("Target project was not found")
            project = dict(rows[0]["payload"])
            if action == "contact_update":
                contact = next((x for x in project.get("contacts", [])
                                if x.get("project_role") == payload.get("project_role")), None)
                if not contact:
                    raise ValueError("Target contact role was not found")
                contact.update({key: payload[key] for key in ("name", "email", "mobile") if key in payload})
            elif action == "activity_import": project["activities"] = list(payload.get("activities", []))
            elif action == "resource_import":
                for field in ("manpower", "equipment"):
                    if field in payload: project[field] = list(payload[field])
            else: project["milestones"] = list(payload.get("milestones", []))
            self.service.update("projects", {"payload": project, "updated_at": self._now()}, code=f"eq.{code}")
        else:
            raise ValueError(f"Unsupported approved action: {action}")

    def list_notifications(self, role: str, unread_only: bool = False) -> dict[str, Any]:
        auth = current_auth.get()
        if not auth:
            return {"items": [], "unread_count": 0}
        filters: dict[str, str] = {"recipient_user_id": f"eq.{auth.user_id}", "order": "created_at.desc"}
        if unread_only:
            filters["read_at"] = "is.null"
        items = self.db.select("notifications", **filters)
        unread = self.db.select("notifications", select="id", recipient_user_id=f"eq.{auth.user_id}", read_at="is.null")
        return {"items": items, "unread_count": len(unread)}

    def mark_notification_read(self, notification_id: str, role: str) -> dict[str, Any]:
        auth = current_auth.get()
        rows = self.db.update("notifications", {"read_at": self._now()}, id=f"eq.{notification_id}",
                              recipient_user_id=f"eq.{auth.user_id if auth else ''}")
        if not rows:
            raise KeyError("Notification not found")
        return rows[0]

    def mark_all_notifications_read(self, role: str) -> int:
        auth = current_auth.get()
        rows = self.db.update("notifications", {"read_at": self._now()},
                              recipient_user_id=f"eq.{auth.user_id if auth else ''}", read_at="is.null")
        return len(rows)

    def delete_document_record_and_storage(self, document_id: str) -> dict[str, Any] | None:
        document = self.get_document(document_id)
        if document:
            self.service.remove_objects(document["storage_bucket"], [document["storage_key"]])
        return self.delete_document_record(document_id)

    def delete_failed_ingestion_records(self, job_id: str, actor_role: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if not job or job["status"] != "failed":
            raise ValueError("Only failed ingestion jobs can be cleared")
        document = self.get_document(job["document_id"])
        self.service.delete("ingestion_jobs", id=f"eq.{job_id}")
        if document:
            self.service.remove_objects(document["storage_bucket"], [document["storage_key"]])
            self.db.delete("documents", id=f"eq.{document['id']}")
        self._audit(actor_role, "failed_ingestion_cleared", "ingestion_job", job_id, job, None)
        return {"job_id": job_id, "document_id": job["document_id"]}

    def resolve_project_reference(self, value: str) -> str | None:
        project = self.find_project(value, current_auth.get().role if current_auth.get() else "employee")
        return project["code"] if project else None

    def create_portfolio_import(self, filename: str, checksum: str, stored_path: str,
                                uploaded_by: str, dataset: str = "combined",
                                project_code: str | None = None) -> dict[str, Any]:
        actor_id, _ = self._actor()
        import_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        storage_key = f"{actor_id}/{import_id}/{filename}"
        self.service.insert("portfolio_imports", {
            "id": import_id, "filename": filename, "checksum": checksum,
            "storage_key": storage_key, "uploaded_by": actor_id, "dataset": dataset,
            "project_code": project_code, "status": "processing",
        })
        self.service.insert("portfolio_import_jobs", {
            "id": job_id, "import_id": import_id, "status": "processing", "progress": 10,
            "message": "Validating portfolio import",
        })
        result = self.get_portfolio_import(import_id, include_path=True) or {}
        result["stored_path"] = stored_path
        return result

    def get_portfolio_import(self, import_id: str, include_path: bool = False) -> dict[str, Any] | None:
        rows = self.db.select("portfolio_imports", id=f"eq.{import_id}", limit="1")
        if not rows:
            return None
        jobs = self.db.select("portfolio_import_jobs", import_id=f"eq.{import_id}", limit="1")
        result = {**rows[0]}
        result["summary"] = result.pop("summary_json", None)
        if jobs:
            result.update(job_id=jobs[0]["id"], progress=jobs[0]["progress"],
                          message=jobs[0].get("message"), updated_at=jobs[0].get("updated_at"))
        return result

    def fail_portfolio_import(self, import_id: str, message: str) -> dict[str, Any]:
        self.service.update("portfolio_imports", {"status": "failed", "error_message": message}, id=f"eq.{import_id}")
        self.service.update("portfolio_import_jobs", {"status": "failed", "progress": 100,
                            "message": message, "updated_at": self._now()}, import_id=f"eq.{import_id}")
        return self.get_portfolio_import(import_id) or {}

    def apply_portfolio_import(self, import_id: str, parsed: dict[str, Any]) -> dict[str, Any]:
        counts: dict[str, dict[str, int]] = {}
        now = self._now()
        for key, table, conflict, columns, key_columns in (
            (
                "manpower", "manpower_assignments", "emp_code",
                MANPOWER_DB_COLUMNS, ("emp_code",),
            ),
            (
                "invoices", "project_invoices", "job_number,draft_invoice_number",
                INVOICE_DB_COLUMNS, ("job_number", "draft_invoice_number"),
            ),
            (
                "schedule", "project_schedule_activities", "project_code,activity_id",
                ("project_code", "activity_id", "activity_name", "start_date",
                 "finish_date", "original_duration"),
                ("project_code", "activity_id"),
            ),
        ):
            items = parsed.get(key, [])
            existing_select = list(key_columns)
            if key == "invoices":
                existing_select.append("project_code")
            existing_rows = self.service.select_all(
                table, select=",".join(dict.fromkeys(existing_select))
            )
            existing = {
                tuple(str(row.get(column) or "") for column in key_columns): row
                for row in existing_rows
            }
            rows = []
            for item in items:
                source = dict(item)
                if key == "schedule":
                    source.update(start_date=source.pop("start"), finish_date=source.pop("finish"))
                row = {column: source.get(column) for column in columns}
                stable_key = tuple(str(row.get(column) or "") for column in key_columns)
                if key == "invoices" and stable_key in existing:
                    previous_project = existing[stable_key].get("project_code")
                    if previous_project and previous_project != row.get("project_code"):
                        raise ValueError("An existing invoice cannot be reassigned to another project")
                if key in {"manpower", "invoices"}:
                    row["data_json"] = item
                row.update(import_id=import_id, updated_at=now)
                if key == "schedule":
                    row.pop("data_json", None)
                rows.append(row)
            if rows:
                path = f"/rest/v1/{table}?on_conflict={conflict}"
                self.service.request("POST", path, rows, prefer="return=representation,resolution=merge-duplicates")
            updated = sum(
                tuple(str(row.get(column) or "") for column in key_columns) in existing
                for row in rows
            )
            counts[key] = {"inserted": len(rows) - updated, "updated": updated}
        summary = {**counts, "pivot_row_count": len(self.invoice_pivot())}
        self.service.update("portfolio_imports", {"status": "completed", "summary_json": summary,
                            "completed_at": self._now()}, id=f"eq.{import_id}")
        self.service.update("portfolio_import_jobs", {"status": "completed", "progress": 100,
                            "message": "Portfolio import completed", "updated_at": self._now()}, import_id=f"eq.{import_id}")
        return self.get_portfolio_import(import_id) or {}

    def list_manpower(self, project_code: str | None = None, search: str | None = None,
                       department: str | None = None, category: str | None = None,
                       status: str | None = None, location: str | None = None) -> list[dict[str, Any]]:
        filters: dict[str, str] = {"order": "name.asc"}
        for field, value in (("current_project_code", project_code), ("department", department),
                             ("category", category), ("status", status), ("current_location", location)):
            if value: filters[field] = f"eq.{value}"
        if search: filters["or"] = f"(name.ilike.*{search}*,emp_code.ilike.*{search}*)"
        results = []
        for source in self.db.select_all("manpower_assignments", **filters):
            item = dict(self._decode_json(source.get("data_json")) or {})
            item.update({column: source.get(column) for column in MANPOWER_DB_COLUMNS})
            results.append(item)
        return results

    def list_invoices(self, project_code: str | None = None, status: str | None = None,
                      level: str | None = None, approval_status: str | None = None,
                      payment_status: str | None = None, risk_profile: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      minimum_aging_days: int | None = None) -> list[dict[str, Any]]:
        filters: dict[str, str] = {}
        for field, value in (("project_code", project_code), ("status", status), ("levels", level),
                             ("approval_status", approval_status), ("payment_status", payment_status),
                             ("risk_profile", risk_profile)):
            if value: filters[field] = f"eq.{value}"
        if date_from: filters["submission_date"] = f"gte.{date_from}"
        if date_to: filters["submission_date"] = f"lte.{date_to}"
        results = []
        for row in self.db.select_all("project_invoices", **filters):
            item = dict(self._decode_json(row.get("data_json")) or {})
            item.update({column: row.get(column) for column in INVOICE_DB_COLUMNS})
            item = with_invoice_legacy_aliases(item)
            item["live_aging_days"] = ProjectRepository._days_since(item.get("submission_date"), date.today())
            item["live_days_to_remittance"] = ProjectRepository._days_until(item.get("expected_remittance_date"), date.today())
            if minimum_aging_days is None or (item["live_aging_days"] is not None and item["live_aging_days"] >= minimum_aging_days):
                results.append(item)
        return results

    def invoice_pivot(self) -> list[dict[str, Any]]:
        rows = self.db.select("project_invoices", select="levels,status,project_code,invoice_value_usd")
        grouped: dict[tuple[str, str], dict[str, float]] = {}
        for row in rows:
            key = (row.get("levels") or "", row.get("status") or "")
            projects = grouped.setdefault(key, {})
            projects[row["project_code"]] = projects.get(row["project_code"], 0) + float(row["invoice_value_usd"])
        return [{"levels": key[0], "status": key[1], "projects": values,
                 "grand_total": round(sum(values.values()), 2)} for key, values in sorted(grouped.items())]

    def list_project_schedule(self, project_code: str) -> list[dict[str, Any]]:
        rows = self.db.select("project_schedule_activities", project_code=f"eq.{project_code}", order="start_date.asc")
        return [{"project_code": row["project_code"], "activity_id": row["activity_id"],
                 "activity_name": row["activity_name"], "start": row["start_date"],
                 "finish": row["finish_date"], "original_duration": row["original_duration"]} for row in rows]

    def _audit(self, actor_role: str, action: str, target_type: str, target_id: str,
               before: Any, after: Any) -> None:
        auth = current_auth.get()
        self.service.insert("audit_events", {
            "actor_user_id": auth.user_id if auth else None, "actor_role": actor_role,
            "action": action, "target_type": target_type, "target_id": target_id,
            "before_json": before, "after_json": after,
        })

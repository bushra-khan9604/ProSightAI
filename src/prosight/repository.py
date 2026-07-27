"""SQLite-backed access layer for ProSight project and employee information."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "data" / "projects.json"
DEFAULT_DB = ROOT / "data" / "prosight.db"


class ProjectRepository:
    """Load sample project data and expose role-filtered read operations."""

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        """Create a repository using the supplied SQLite database path."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Open a SQLite connection whose rows support dictionary-style access."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _now() -> str:
        """Return a stable UTC timestamp for persisted workflow records."""
        return datetime.now(UTC).isoformat()

    def ensure_schema(self) -> None:
        """Create additive workflow tables without rebuilding project data."""
        with closing(self.connect()) as db:
            with db:
                db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        id TEXT PRIMARY KEY,
                        project_code TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK(kind IN ('pdf','xlsx')),
                        checksum TEXT NOT NULL,
                        stored_path TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(project_code, checksum)
                    );
                    CREATE TABLE IF NOT EXISTS ingestion_jobs (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        message TEXT,
                        change_request_id TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS change_requests (
                        id TEXT PRIMARY KEY,
                        action TEXT NOT NULL,
                        project_code TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        preview TEXT NOT NULL,
                        status TEXT NOT NULL,
                        requested_by TEXT NOT NULL,
                        decided_by TEXT,
                        created_at TEXT NOT NULL,
                        decided_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id TEXT PRIMARY KEY,
                        request_id TEXT,
                        actor_role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        before_json TEXT,
                        after_json TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                self._ensure_column(db, "documents", "reporting_date", "TEXT")
                self._ensure_column(db, "documents", "effective_date", "TEXT")
                self._ensure_column(db, "documents", "date_status", "TEXT NOT NULL DEFAULT 'pending'")

    @staticmethod
    def _ensure_column(
        db: sqlite3.Connection, table: str, column: str, declaration: str
    ) -> None:
        """Add an optional schema column during additive local migrations."""
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def initialize(self, source: str | Path = DEFAULT_DATA) -> None:
        """Rebuild the SQLite project table from the canonical JSON dataset."""
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        with closing(self.connect()) as db:
            with db:
                db.executescript(
                    """
                DROP TABLE IF EXISTS projects;
                CREATE TABLE projects (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('completed','active','future')),
                    client TEXT NOT NULL,
                    location TEXT NOT NULL,
                    contract_value_usd REAL NOT NULL,
                    planned_start TEXT NOT NULL,
                    planned_finish TEXT NOT NULL,
                    revised_finish TEXT,
                    reporting_date TEXT NOT NULL,
                    baseline_progress REAL NOT NULL,
                    revised_progress REAL NOT NULL,
                    actual_progress REAL NOT NULL,
                    payload TEXT NOT NULL
                );
                """
                )
                for project in payload["projects"]:
                    db.execute(
                        """INSERT INTO projects VALUES
                    (:code,:name,:status,:client,:location,:contract_value_usd,
                    :planned_start,:planned_finish,:revised_finish,:reporting_date,
                    :baseline_progress,:revised_progress,:actual_progress,:payload)""",
                        {**project, "payload": json.dumps(project)},
                    )

    def _ensure(self) -> None:
        """Create the sample database on first use."""
        if not self.db_path.exists():
            self.initialize()
        self.ensure_schema()

    def create_document(
        self, project_code: str, filename: str, kind: str, checksum: str, stored_path: str
    ) -> dict[str, Any]:
        """Register a validated upload, rejecting project-scoped duplicates."""
        self._ensure()
        document_id = str(uuid.uuid4())
        with closing(self.connect()) as db:
            try:
                with db:
                    db.execute(
                        """INSERT INTO documents
                           (id,project_code,filename,kind,checksum,stored_path,status,created_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (document_id, project_code, filename, kind, checksum, stored_path, "queued", self._now()),
                    )
            except sqlite3.IntegrityError as error:
                raise ValueError("This file has already been uploaded to the project") from error
        return self.get_document(document_id)

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        """Return one upload metadata record."""
        self.ensure_schema()
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row else None

    def list_documents(self, project_code: str) -> list[dict[str, Any]]:
        """List project-scoped uploads without exposing stored filesystem paths."""
        self._ensure()
        with closing(self.connect()) as db:
            rows = db.execute(
                """SELECT id, project_code, filename, kind, checksum, status, created_at,
                          reporting_date, effective_date, date_status
                   FROM documents WHERE project_code = ? ORDER BY created_at DESC""",
                (project_code,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_document_status(self, document_id: str, status: str) -> None:
        """Update an upload lifecycle status."""
        with closing(self.connect()) as db:
            with db:
                db.execute("UPDATE documents SET status = ? WHERE id = ?", (status, document_id))

    def update_document_date(
        self,
        document_id: str,
        reporting_date: str | None,
        effective_date: str,
        date_status: str,
    ) -> None:
        """Persist detected or confirmed document-date provenance."""
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    """UPDATE documents SET reporting_date=?, effective_date=?, date_status=?
                       WHERE id=?""",
                    (reporting_date, effective_date, date_status, document_id),
                )

    def delete_document_record(self, document_id: str) -> dict[str, Any] | None:
        """Delete document metadata after external content has been removed."""
        document = self.get_document(document_id)
        if not document:
            return None
        with closing(self.connect()) as db:
            with db:
                db.execute("DELETE FROM ingestion_jobs WHERE document_id = ?", (document_id,))
                db.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return document

    def create_job(self, document_id: str) -> dict[str, Any]:
        """Persist a queued ingestion job."""
        job_id, now = str(uuid.uuid4()), self._now()
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    "INSERT INTO ingestion_jobs VALUES (?,?,?,?,?,?,?,?)",
                    (job_id, document_id, "queued", 0, "Queued", None, now, now),
                )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return a persisted ingestion job."""
        self.ensure_schema()
        with closing(self.connect()) as db:
            row = db.execute(
                """SELECT j.*, d.reporting_date AS detected_reporting_date,
                          d.effective_date, d.date_status, d.kind, d.filename
                   FROM ingestion_jobs j JOIN documents d ON d.id=j.document_id
                   WHERE j.id = ?""",
                (job_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_job(
        self, job_id: str, status: str, progress: int, message: str, change_request_id: str | None = None
    ) -> None:
        """Update job progress from a background worker."""
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    """UPDATE ingestion_jobs SET status=?, progress=?, message=?,
                       change_request_id=COALESCE(?, change_request_id), updated_at=? WHERE id=?""",
                    (status, max(0, min(100, progress)), message, change_request_id, self._now(), job_id),
                )

    def recover_interrupted_jobs(self) -> None:
        """Mark jobs interrupted by a process restart as failed and recoverable."""
        self.ensure_schema()
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    """UPDATE ingestion_jobs SET status='failed', message='Server restarted during ingestion',
                       updated_at=? WHERE status IN ('queued','processing')""",
                    (self._now(),),
                )

    def create_change_request(
        self, action: str, project_code: str, payload: dict[str, Any],
        preview: dict[str, Any], requested_by: str
    ) -> dict[str, Any]:
        """Store a pending, typed mutation for Admin review."""
        self._ensure()
        change_id = str(uuid.uuid4())
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    "INSERT INTO change_requests VALUES (?,?,?,?,?,'pending',?,?,?,?)",
                    (
                        change_id, action, project_code, json.dumps(payload), json.dumps(preview),
                        requested_by, None, self._now(), None,
                    ),
                )
        return self.get_change_request(change_id)

    def update_pending_project_change(
        self, change_id: str, project: dict[str, Any], actor_role: str
    ) -> dict[str, Any]:
        """Update editable project fields while retaining imported child records."""
        if actor_role not in {"project_manager", "admin"}:
            raise PermissionError("This role cannot edit a project import")
        change = self.get_change_request(change_id)
        if not change:
            raise KeyError("Change request not found")
        if change["status"] != "pending" or change["action"] != "excel_import":
            raise ValueError("Only pending Excel imports can be edited")
        imported = change["payload"].get("projects", [])
        if len(imported) != 1:
            raise ValueError("New-project imports must contain exactly one project")
        merged = {**imported[0], **project}
        payload = {"projects": [merged]}
        preview = {
            **change["preview"],
            "after": merged,
            "warnings": change["preview"].get("warnings", []),
        }
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    """UPDATE change_requests SET project_code=?, payload=?, preview=?
                       WHERE id=?""",
                    (merged["code"], json.dumps(payload), json.dumps(preview), change_id),
                )
        return self.get_change_request(change_id)

    def get_change_request(self, change_id: str) -> dict[str, Any] | None:
        """Return a pending or decided mutation with decoded JSON."""
        self.ensure_schema()
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM change_requests WHERE id = ?", (change_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["preview"] = json.loads(result["preview"])
        return result

    def decide_change_request(self, change_id: str, decision: str, actor_role: str) -> dict[str, Any]:
        """Approve or reject a pending request; only Admin may decide."""
        if actor_role != "admin":
            raise PermissionError("Admin approval is required")
        if decision not in {"approved", "rejected"}:
            raise ValueError("Decision must be approved or rejected")
        change = self.get_change_request(change_id)
        if not change:
            raise KeyError("Change request not found")
        if change["status"] != "pending":
            raise ValueError("Change request has already been decided")
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    "UPDATE change_requests SET status=?, decided_by=?, decided_at=? WHERE id=?",
                    (decision, actor_role, self._now(), change_id),
                )
                if decision == "approved":
                    self._apply_change(db, change)
                terminal = "ready" if decision == "approved" else "rejected"
                db.execute(
                    """UPDATE ingestion_jobs SET status=?, message=?, updated_at=?
                       WHERE change_request_id=?""",
                    (terminal, f"Change {decision}", self._now(), change_id),
                )
                db.execute(
                    """UPDATE documents SET status=? WHERE id IN
                       (SELECT document_id FROM ingestion_jobs WHERE change_request_id=?)""",
                    (terminal, change_id),
                )
                db.execute(
                    "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), None, actor_role, decision, "change_request", change_id,
                        json.dumps(change["preview"].get("before")),
                        json.dumps(change["preview"].get("after")), self._now(),
                    ),
                )
        return self.get_change_request(change_id)

    def _apply_change(self, db: sqlite3.Connection, change: dict[str, Any]) -> None:
        """Execute only explicitly allowlisted mutation shapes."""
        action, payload, code = change["action"], change["payload"], change["project_code"]
        if action == "excel_import":
            for project in payload.get("projects", []):
                existing = db.execute("SELECT 1 FROM projects WHERE code=?", (project["code"],)).fetchone()
                values = {**project, "payload": json.dumps(project)}
                if existing:
                    db.execute(
                        """UPDATE projects SET name=:name,status=:status,client=:client,location=:location,
                        contract_value_usd=:contract_value_usd,planned_start=:planned_start,
                        planned_finish=:planned_finish,revised_finish=:revised_finish,
                        reporting_date=:reporting_date,baseline_progress=:baseline_progress,
                        revised_progress=:revised_progress,actual_progress=:actual_progress,payload=:payload
                        WHERE code=:code""",
                        values,
                    )
                else:
                    db.execute(
                        """INSERT INTO projects VALUES
                        (:code,:name,:status,:client,:location,:contract_value_usd,:planned_start,
                        :planned_finish,:revised_finish,:reporting_date,:baseline_progress,
                        :revised_progress,:actual_progress,:payload)""",
                        values,
                    )
        elif action == "record_delete":
            db.execute("DELETE FROM projects WHERE code = ?", (code,))
        elif action in {
            "contact_update", "activity_import", "resource_import", "milestone_update"
        }:
            row = db.execute("SELECT payload FROM projects WHERE code = ?", (code,)).fetchone()
            if not row:
                raise ValueError("Target project was not found")
            project = json.loads(row["payload"])
            if action == "contact_update":
                role = payload.get("project_role")
                contact = next((item for item in project["contacts"] if item["project_role"] == role), None)
                if not contact:
                    raise ValueError("Target contact role was not found")
                for field in ("name", "email", "mobile"):
                    if field in payload:
                        contact[field] = payload[field]
            elif action == "activity_import":
                project["activities"] = list(payload.get("activities", []))
            elif action == "resource_import":
                if "manpower" in payload:
                    project["manpower"] = list(payload["manpower"])
                if "equipment" in payload:
                    project["equipment"] = list(payload["equipment"])
            else:
                project["milestones"] = list(payload.get("milestones", []))
            db.execute("UPDATE projects SET payload = ? WHERE code = ?", (json.dumps(project), code))
        elif action == "project_upsert":
            raise ValueError("Project upsert must use a validated Excel import payload")
        else:
            raise ValueError(f"Unsupported approved action: {action}")

    @staticmethod
    def _decorate(project: dict[str, Any], user_role: str) -> dict[str, Any]:
        """Add calculated fields and enforce field-level contact restrictions."""
        planned = date.fromisoformat(project["planned_finish"])
        revised = date.fromisoformat(project["revised_finish"] or project["planned_finish"])
        # Schedule and progress calculations are deterministic rather than model-generated.
        project["delay_days"] = max(0, (revised - planned).days)
        project["variance_pct"] = round(
            project["actual_progress"] - project["revised_progress"], 1
        )
        if user_role == "employee":
            for person in project["contacts"]:
                person["email"] = "restricted"
                person["mobile"] = "restricted"
        return project

    def list_projects(self, status: str | None = None, user_role: str = "employee") -> list[dict[str, Any]]:
        """Return authorized projects, optionally filtered by lifecycle status."""
        self._ensure()
        query = "SELECT payload FROM projects"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status.lower(),)
        query += " ORDER BY planned_start"
        with closing(self.connect()) as db:
            rows = db.execute(query, params).fetchall()
        return [self._decorate(json.loads(row["payload"]), user_role) for row in rows]

    def find_project(self, term: str, user_role: str = "employee") -> dict[str, Any] | None:
        """Find one project by exact or partial code/name match."""
        self._ensure()
        normalized = term.strip().lower()
        with closing(self.connect()) as db:
            rows = db.execute("SELECT code, name, payload FROM projects").fetchall()
        exact = [r for r in rows if normalized in {r["code"].lower(), r["name"].lower()}]
        partial = [
            r for r in rows
            if normalized in r["name"].lower() or normalized in r["code"].lower()
        ]
        match = (exact or partial)
        return self._decorate(json.loads(match[0]["payload"]), user_role) if match else None

    def portfolio_summary(self, user_role: str = "employee") -> dict[str, Any]:
        """Calculate portfolio counts, contract values, and delayed project codes."""
        projects = self.list_projects(user_role=user_role)
        by_status = {status: [p for p in projects if p["status"] == status]
                     for status in ("active", "completed", "future")}
        return {
            "project_count": len(projects),
            "counts": {key: len(value) for key, value in by_status.items()},
            "contract_value_usd": {
                key: sum(p["contract_value_usd"] for p in value)
                for key, value in by_status.items()
            },
            "delayed_active_projects": [
                p["code"] for p in by_status["active"] if p["delay_days"] > 0
            ],
        }

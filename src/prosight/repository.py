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
DEFAULT_PROJECT_CODES = frozenset(
    {"PRJ-2024-001", "PRJ-2025-004", "PRJ-2022-009", "BID-2027-003"}
)
DEFAULT_PROJECT_ENRICHMENT = "default_project_details_v1"


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
                    CREATE TABLE IF NOT EXISTS notifications (
                        id TEXT PRIMARY KEY,
                        recipient_role TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        project_code TEXT NOT NULL,
                        change_request_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        read_at TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE(recipient_role, event_type, change_request_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_notifications_role_created
                        ON notifications(recipient_role, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_change_requests_status_created
                        ON change_requests(status, created_at DESC);
                    CREATE TABLE IF NOT EXISTS portfolio_imports (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        checksum TEXT NOT NULL,
                        stored_path TEXT NOT NULL,
                        uploaded_by TEXT NOT NULL,
                        status TEXT NOT NULL,
                        summary_json TEXT,
                        error_message TEXT,
                        created_at TEXT NOT NULL,
                        completed_at TEXT
                    );
                    CREATE TABLE IF NOT EXISTS portfolio_import_jobs (
                        id TEXT PRIMARY KEY,
                        import_id TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL,
                        message TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS manpower_assignments (
                        emp_code TEXT PRIMARY KEY,
                        current_project_code TEXT NOT NULL,
                        mobilized_project_code TEXT,
                        name TEXT NOT NULL,
                        designation TEXT,
                        department TEXT,
                        category TEXT,
                        current_location TEXT,
                        allocation TEXT,
                        status TEXT,
                        leave_balance REAL,
                        data_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        import_id TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS project_invoices (
                        job_number TEXT NOT NULL,
                        draft_invoice_number TEXT NOT NULL,
                        project_code TEXT NOT NULL,
                        levels TEXT,
                        status TEXT,
                        approval_status TEXT,
                        payment_status TEXT,
                        risk_profile TEXT,
                        invoice_value_usd REAL NOT NULL,
                        invoice_value_aed REAL,
                        submission_date TEXT,
                        expected_remittance_date TEXT,
                        data_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        import_id TEXT NOT NULL,
                        PRIMARY KEY(job_number, draft_invoice_number)
                    );
                    CREATE TABLE IF NOT EXISTS project_schedule_activities (
                        project_code TEXT NOT NULL,
                        activity_id TEXT NOT NULL,
                        activity_name TEXT NOT NULL,
                        start_date TEXT NOT NULL,
                        finish_date TEXT NOT NULL,
                        original_duration INTEGER NOT NULL,
                        import_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY(project_code, activity_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_manpower_project
                        ON manpower_assignments(current_project_code);
                    CREATE INDEX IF NOT EXISTS idx_invoices_project
                        ON project_invoices(project_code);
                    CREATE INDEX IF NOT EXISTS idx_schedule_project_start
                        ON project_schedule_activities(project_code, start_date);
                    CREATE TABLE IF NOT EXISTS seed_migrations (
                        migration_key TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );
                    """
                )
                self._ensure_column(db, "documents", "reporting_date", "TEXT")
                self._ensure_column(db, "documents", "effective_date", "TEXT")
                self._ensure_column(db, "documents", "date_status", "TEXT NOT NULL DEFAULT 'pending'")
                self._ensure_column(db, "portfolio_imports", "dataset", "TEXT")
                self._ensure_column(db, "portfolio_imports", "project_code", "TEXT")
                # Existing pending requests predate notifications but must still
                # appear as unread Admin work after this additive migration.
                pending = db.execute(
                    """SELECT id, action, project_code, requested_by
                       FROM change_requests WHERE status='pending'"""
                ).fetchall()
                for change in pending:
                    self._insert_notification(
                        db, "admin", "approval_required", change["project_code"],
                        change["id"], "Approval required",
                        f"{change['requested_by'].replace('_', ' ').title()} submitted a "
                        f"{change['action'].replace('_', ' ')} request.",
                    )
                self._enrich_default_projects(db)

    @staticmethod
    def _ensure_column(
        db: sqlite3.Connection, table: str, column: str, declaration: str
    ) -> None:
        """Add an optional schema column during additive local migrations."""
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def _normalized_seed_value(value: Any) -> str:
        """Normalize a seed identity value without changing its displayed form."""
        return " ".join(str(value or "").strip().casefold().split())

    @classmethod
    def _seed_item_key(cls, collection: str, item: Any) -> tuple[str, ...]:
        """Return the stable identity used to append one missing nested seed item."""
        if collection == "activities":
            return (cls._normalized_seed_value(item),)
        if not isinstance(item, dict):
            return ()
        if collection == "contacts":
            return (
                cls._normalized_seed_value(item.get("name")),
                cls._normalized_seed_value(item.get("project_role")),
            )
        identity_field = {
            "manpower": "designation",
            "equipment": "type",
            "milestones": "name",
        }[collection]
        return (cls._normalized_seed_value(item.get(identity_field)),)

    def _enrich_default_projects(self, db: sqlite3.Connection) -> None:
        """Append missing canonical details to existing default projects once."""
        projects_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='projects'"
        ).fetchone()
        if not projects_table:
            return
        applied = db.execute(
            "SELECT 1 FROM seed_migrations WHERE migration_key=?",
            (DEFAULT_PROJECT_ENRICHMENT,),
        ).fetchone()
        if applied:
            return

        canonical = json.loads(DEFAULT_DATA.read_text(encoding="utf-8"))
        collections = ("contacts", "activities", "manpower", "equipment", "milestones")
        for seeded_project in canonical.get("projects", []):
            project_code = seeded_project.get("code")
            if project_code not in DEFAULT_PROJECT_CODES:
                continue
            row = db.execute(
                "SELECT payload FROM projects WHERE code=?", (project_code,)
            ).fetchone()
            if not row:
                continue
            project = json.loads(row["payload"])
            changed = False
            for collection in collections:
                current_items = project.get(collection, [])
                seeded_items = seeded_project.get(collection, [])
                if not isinstance(current_items, list) or not isinstance(seeded_items, list):
                    continue
                existing_keys = {
                    self._seed_item_key(collection, item) for item in current_items
                }
                for item in seeded_items:
                    key = self._seed_item_key(collection, item)
                    if not key or not all(key) or key in existing_keys:
                        continue
                    current_items.append(item)
                    existing_keys.add(key)
                    changed = True
                project[collection] = current_items
            if changed:
                db.execute(
                    "UPDATE projects SET payload=? WHERE code=?",
                    (json.dumps(project), project_code),
                )

        db.execute(
            "INSERT INTO seed_migrations (migration_key, applied_at) VALUES (?, ?)",
            (DEFAULT_PROJECT_ENRICHMENT, self._now()),
        )

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
                   FROM documents WHERE project_code = ? AND status <> 'failed'
                   ORDER BY created_at DESC""",
                (project_code,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_jobs(self, project_code: str) -> list[dict[str, Any]]:
        """List persisted ingestion jobs for one project without stored file paths."""
        self._ensure()
        with closing(self.connect()) as db:
            rows = db.execute(
                """SELECT j.*, d.reporting_date AS detected_reporting_date,
                          d.effective_date, d.date_status, d.kind, d.filename
                   FROM ingestion_jobs j JOIN documents d ON d.id=j.document_id
                   WHERE d.project_code=? ORDER BY j.created_at DESC""",
                (project_code,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_document_status(self, document_id: str, status: str) -> None:
        """Update an upload lifecycle status."""
        with closing(self.connect()) as db:
            with db:
                db.execute("UPDATE documents SET status = ? WHERE id = ?", (status, document_id))

    def complete_document_ingestion(
        self, document_id: str, job_id: str, chunk_count: int
    ) -> None:
        """Publish a fully embedded document and remove its completed job atomically."""
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    "UPDATE documents SET status='ready' WHERE id=?", (document_id,)
                )
                result = db.execute(
                    "DELETE FROM ingestion_jobs WHERE id=? AND document_id=?",
                    (job_id, document_id),
                )
                if result.rowcount != 1:
                    raise ValueError("Ingestion job does not match document")

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

    def delete_failed_ingestion_records(self, job_id: str, actor_role: str) -> dict[str, Any]:
        """Atomically remove one failed job and document while retaining an audit event."""
        self._ensure()
        with closing(self.connect()) as db:
            with db:
                row = db.execute(
                    """SELECT j.id AS job_id,j.document_id,j.status AS job_status,j.message,
                              j.change_request_id,d.project_code,d.filename,d.kind,d.status AS document_status
                       FROM ingestion_jobs j JOIN documents d ON d.id=j.document_id
                       WHERE j.id=?""",
                    (job_id,),
                ).fetchone()
                if not row:
                    raise KeyError("Ingestion job not found")
                record = dict(row)
                if record["job_status"] != "failed":
                    raise ValueError("Only failed ingestion jobs can be cleared")
                if record["change_request_id"]:
                    change = db.execute(
                        "SELECT status FROM change_requests WHERE id=?",
                        (record["change_request_id"],),
                    ).fetchone()
                    if change and change["status"] == "pending":
                        raise ValueError("This failed job still has an unresolved change request")
                db.execute("DELETE FROM ingestion_jobs WHERE id=?", (job_id,))
                db.execute("DELETE FROM documents WHERE id=?", (record["document_id"],))
                audit_before = {
                    "job_id": record["job_id"], "document_id": record["document_id"],
                    "project_code": record["project_code"], "filename": record["filename"],
                    "kind": record["kind"], "status": record["job_status"],
                    "failure_reason": record["message"],
                }
                self._insert_audit(
                    db, actor_role, "failed_ingestion_cleared", "ingestion_job",
                    job_id, audit_before, None, self._now(),
                )
        return audit_before

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

    def claim_job(self, job_id: str) -> bool:
        """Atomically allow only one in-process task to start a queued job."""
        with closing(self.connect()) as db:
            with db:
                result = db.execute(
                    """UPDATE ingestion_jobs SET status='processing', progress=5,
                       message='Claimed for processing', updated_at=?
                       WHERE id=? AND status='queued'""",
                    (self._now(), job_id),
                )
        return result.rowcount == 1

    def recover_interrupted_jobs(self) -> None:
        """Mark jobs interrupted by a process restart as failed and recoverable."""
        self.ensure_schema()
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    """DELETE FROM ingestion_jobs WHERE status='ready' AND document_id IN
                       (SELECT id FROM documents WHERE status='ready')"""
                )
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
                self._insert_notification(
                    db, "admin", "approval_required", project_code, change_id,
                    "Approval required",
                    f"{requested_by.replace('_', ' ').title()} submitted a {action.replace('_', ' ')} request.",
                )
        return self.get_change_request(change_id)

    def create_pdf_approval(
        self, job_id: str, document: dict[str, Any], requested_by: str
    ) -> dict[str, Any]:
        """Create the mandatory approval record for a validated PDF."""
        return self.create_change_request(
            "pdf_ingestion", document["project_code"],
            {"job_id": job_id, "document_id": document["id"]},
            {
                "before": None,
                "after": {
                    "filename": document["filename"],
                    "reporting_date": document.get("reporting_date"),
                    "effective_date": document.get("effective_date"),
                    "date_status": document.get("date_status"),
                },
            },
            requested_by,
        )

    def _insert_notification(
        self, db: sqlite3.Connection, recipient_role: str, event_type: str,
        project_code: str, change_request_id: str, title: str, message: str
    ) -> None:
        """Insert one idempotent role notification inside the caller's transaction."""
        db.execute(
            """INSERT OR IGNORE INTO notifications
               (id,recipient_role,event_type,project_code,change_request_id,
                title,message,read_at,created_at)
               VALUES (?,?,?,?,?,?,?,NULL,?)""",
            (
                str(uuid.uuid4()), recipient_role, event_type, project_code,
                change_request_id, title, message, self._now(),
            ),
        )

    def list_notifications(self, role: str, unread_only: bool = False) -> dict[str, Any]:
        """Return persistent notifications and the role's current unread count."""
        self._ensure()
        clause = "AND read_at IS NULL" if unread_only else ""
        with closing(self.connect()) as db:
            rows = db.execute(
                f"""SELECT * FROM notifications WHERE recipient_role=? {clause}
                    ORDER BY created_at DESC""",
                (role,),
            ).fetchall()
            unread_count = db.execute(
                """SELECT COUNT(*) AS count FROM notifications
                   WHERE recipient_role=? AND read_at IS NULL""",
                (role,),
            ).fetchone()["count"]
        return {"items": [dict(row) for row in rows], "unread_count": unread_count}

    def mark_notification_read(self, notification_id: str, role: str) -> dict[str, Any]:
        """Mark a notification read only when it belongs to the supplied role."""
        self._ensure()
        with closing(self.connect()) as db:
            with db:
                cursor = db.execute(
                    """UPDATE notifications SET read_at=COALESCE(read_at, ?)
                       WHERE id=? AND recipient_role=?""",
                    (self._now(), notification_id, role),
                )
                if not cursor.rowcount:
                    raise KeyError("Notification not found")
                row = db.execute(
                    "SELECT * FROM notifications WHERE id=?", (notification_id,)
                ).fetchone()
        return dict(row)

    def mark_all_notifications_read(self, role: str) -> int:
        """Mark every unread notification for one role as read."""
        self._ensure()
        with closing(self.connect()) as db:
            with db:
                cursor = db.execute(
                    """UPDATE notifications SET read_at=?
                       WHERE recipient_role=? AND read_at IS NULL""",
                    (self._now(), role),
                )
        return cursor.rowcount

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        """Return every pending change request for the server-backed Admin queue."""
        self._ensure()
        with closing(self.connect()) as db:
            rows = db.execute(
                """SELECT * FROM change_requests WHERE status='pending'
                   ORDER BY created_at DESC"""
            ).fetchall()
        approvals = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            item["preview"] = json.loads(item["preview"])
            approvals.append(item)
        return approvals

    def resolve_project_reference(self, value: str) -> str | None:
        """Resolve a workbook project code, full name, or unique short name."""
        self._ensure()
        normalized = " ".join(value.strip().casefold().split())
        if not normalized:
            return None
        with closing(self.connect()) as db:
            rows = db.execute("SELECT code,name FROM projects").fetchall()
        exact = [
            row["code"] for row in rows
            if normalized in {row["code"].casefold(), row["name"].casefold()}
        ]
        if len(exact) == 1:
            return exact[0]
        partial = [
            row["code"] for row in rows
            if normalized in row["name"].casefold() or row["name"].casefold() in normalized
        ]
        return partial[0] if len(partial) == 1 else None

    def create_portfolio_import(
        self, filename: str, checksum: str, stored_path: str, uploaded_by: str,
        dataset: str = "combined", project_code: str | None = None,
    ) -> dict[str, Any]:
        """Create durable import and job records before workbook validation."""
        self._ensure()
        import_id, job_id, now = str(uuid.uuid4()), str(uuid.uuid4()), self._now()
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    """INSERT INTO portfolio_imports
                       (id,filename,checksum,stored_path,uploaded_by,status,summary_json,
                        error_message,created_at,completed_at,dataset,project_code)
                       VALUES (?,?,?,?,?,'processing',NULL,NULL,?,NULL,?,?)""",
                    (import_id, filename, checksum, stored_path, uploaded_by, now,
                     dataset, project_code),
                )
                db.execute(
                    """INSERT INTO portfolio_import_jobs
                       VALUES (?,?,'processing',10,'Validating workbook',?,?)""",
                    (job_id, import_id, now, now),
                )
        return self.get_portfolio_import(import_id)

    def fail_portfolio_import(self, import_id: str, message: str) -> dict[str, Any]:
        """Persist a safe validation failure and notify the uploading role."""
        record = self.get_portfolio_import(import_id, include_path=True)
        if not record:
            raise KeyError("Portfolio import not found")
        now = self._now()
        with closing(self.connect()) as db:
            with db:
                db.execute(
                    """UPDATE portfolio_imports SET status='failed',error_message=?,
                       completed_at=? WHERE id=?""",
                    (message[:1000], now, import_id),
                )
                db.execute(
                    """UPDATE portfolio_import_jobs SET status='failed',progress=100,
                       message=?,updated_at=? WHERE import_id=?""",
                    (message[:500], now, import_id),
                )
                self._insert_notification(
                    db, record["uploaded_by"], "portfolio_import_failed", "PORTFOLIO",
                    import_id, "Portfolio import failed", message[:500],
                )
        return self.get_portfolio_import(import_id)

    def apply_portfolio_import(
        self, import_id: str, parsed: dict[str, Any]
    ) -> dict[str, Any]:
        """Atomically upsert validated manpower and invoice rows with audit."""
        record = self.get_portfolio_import(import_id, include_path=True)
        if not record:
            raise KeyError("Portfolio import not found")
        now, inserted_manpower, updated_manpower = self._now(), 0, 0
        inserted_invoices, updated_invoices, inserted_schedule, updated_schedule = 0, 0, 0, 0
        with closing(self.connect()) as db:
            with db:
                for item in parsed["manpower"]:
                    before_row = db.execute(
                        "SELECT data_json FROM manpower_assignments WHERE emp_code=?",
                        (item["emp_code"],),
                    ).fetchone()
                    before = json.loads(before_row["data_json"]) if before_row else None
                    if before_row:
                        updated_manpower += 1
                    else:
                        inserted_manpower += 1
                    db.execute(
                        """INSERT INTO manpower_assignments
                           (emp_code,current_project_code,mobilized_project_code,name,
                            designation,department,category,current_location,allocation,
                            status,leave_balance,data_json,updated_at,import_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(emp_code) DO UPDATE SET
                            current_project_code=excluded.current_project_code,
                            mobilized_project_code=excluded.mobilized_project_code,
                            name=excluded.name,designation=excluded.designation,
                            department=excluded.department,category=excluded.category,
                            current_location=excluded.current_location,
                            allocation=excluded.allocation,status=excluded.status,
                            leave_balance=excluded.leave_balance,data_json=excluded.data_json,
                            updated_at=excluded.updated_at,import_id=excluded.import_id""",
                        (
                            item["emp_code"], item["current_project_code"],
                            item["mobilized_project_code"], item["name"], item["designation"],
                            item["department"], item["category"], item["current_location"],
                            item["allocation"], item["status"], item["leave_balance"],
                            json.dumps(item), now, import_id,
                        ),
                    )
                    self._insert_audit(
                        db, record["uploaded_by"], "portfolio_manpower_upsert",
                        "manpower_assignment", item["emp_code"], before, item, now,
                    )
                for item in parsed["invoices"]:
                    before_row = db.execute(
                        """SELECT project_code,data_json FROM project_invoices
                           WHERE job_number=? AND draft_invoice_number=?""",
                        (item["job_number"], item["draft_invoice_number"]),
                    ).fetchone()
                    if before_row and before_row["project_code"] != item["project_code"]:
                        raise ValueError("An existing invoice cannot be reassigned to another project")
                    before = json.loads(before_row["data_json"]) if before_row else None
                    if before_row:
                        updated_invoices += 1
                    else:
                        inserted_invoices += 1
                    db.execute(
                        """INSERT INTO project_invoices
                           (job_number,draft_invoice_number,project_code,levels,status,
                            approval_status,payment_status,risk_profile,invoice_value_usd,
                            invoice_value_aed,submission_date,expected_remittance_date,
                            data_json,updated_at,import_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(job_number,draft_invoice_number) DO UPDATE SET
                            levels=excluded.levels,status=excluded.status,
                            approval_status=excluded.approval_status,
                            payment_status=excluded.payment_status,
                            risk_profile=excluded.risk_profile,
                            invoice_value_usd=excluded.invoice_value_usd,
                            invoice_value_aed=excluded.invoice_value_aed,
                            submission_date=excluded.submission_date,
                            expected_remittance_date=excluded.expected_remittance_date,
                            data_json=excluded.data_json,updated_at=excluded.updated_at,
                            import_id=excluded.import_id""",
                        (
                            item["job_number"], item["draft_invoice_number"],
                            item["project_code"], item.get("levels"), item.get("status"),
                            item.get("approval_status"), item.get("payment_status"),
                            item.get("risk_profile"), item["invoice_value_usd"],
                            item.get("invoice_value_aed"), item.get("submission_date"),
                            item.get("expected_remittance_date"), json.dumps(item),
                            now, import_id,
                        ),
                    )
                    target = f"{item['job_number']}:{item['draft_invoice_number']}"
                    self._insert_audit(
                        db, record["uploaded_by"], "portfolio_invoice_upsert",
                        "project_invoice", target, before, item, now,
                    )
                for item in parsed.get("schedule", []):
                    before_row = db.execute(
                        """SELECT * FROM project_schedule_activities
                           WHERE project_code=? AND activity_id=?""",
                        (item["project_code"], item["activity_id"]),
                    ).fetchone()
                    before = dict(before_row) if before_row else None
                    if before_row:
                        updated_schedule += 1
                    else:
                        inserted_schedule += 1
                    db.execute(
                        """INSERT INTO project_schedule_activities
                           (project_code,activity_id,activity_name,start_date,finish_date,
                            original_duration,import_id,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(project_code,activity_id) DO UPDATE SET
                            activity_name=excluded.activity_name,start_date=excluded.start_date,
                            finish_date=excluded.finish_date,
                            original_duration=excluded.original_duration,
                            import_id=excluded.import_id,updated_at=excluded.updated_at""",
                        (item["project_code"], item["activity_id"], item["activity_name"],
                         item["start"], item["finish"], item["original_duration"],
                         import_id, now, now),
                    )
                    self._insert_audit(
                        db, record["uploaded_by"], "portfolio_schedule_upsert",
                        "project_schedule_activity",
                        f"{item['project_code']}:{item['activity_id']}", before, item, now,
                    )
                summary = {
                    "manpower": {"inserted": inserted_manpower, "updated": updated_manpower},
                    "invoices": {"inserted": inserted_invoices, "updated": updated_invoices},
                    "schedule": {"inserted": inserted_schedule, "updated": updated_schedule},
                    "pivot_row_count": db.execute(
                        """SELECT COUNT(*) AS count FROM (
                           SELECT levels,status FROM project_invoices
                           GROUP BY levels,status)"""
                    ).fetchone()["count"],
                }
                db.execute(
                    """UPDATE portfolio_imports SET status='completed',summary_json=?,
                       completed_at=? WHERE id=?""",
                    (json.dumps(summary), now, import_id),
                )
                db.execute(
                    """UPDATE portfolio_import_jobs SET status='completed',progress=100,
                       message='Portfolio import completed',updated_at=? WHERE import_id=?""",
                    (now, import_id),
                )
                self._insert_notification(
                    db, record["uploaded_by"], "portfolio_import_completed", "PORTFOLIO",
                    import_id, "Portfolio import completed",
                    f"Imported {len(parsed['manpower'])} manpower and "
                    f"{len(parsed['invoices'])} invoice and "
                    f"{len(parsed.get('schedule', []))} schedule rows.",
                )
        return self.get_portfolio_import(import_id)

    def list_project_schedule(self, project_code: str) -> list[dict[str, Any]]:
        """Return normalized project schedule activities in deterministic order."""
        self._ensure()
        with closing(self.connect()) as db:
            rows = db.execute(
                """SELECT project_code,activity_id,activity_name,start_date AS start,
                          finish_date AS finish,original_duration
                   FROM project_schedule_activities WHERE project_code=?
                   ORDER BY start_date,finish_date,activity_id""",
                (project_code,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _insert_audit(
        db: sqlite3.Connection, actor_role: str, action: str, target_type: str,
        target_id: str, before: Any, after: Any, created_at: str,
    ) -> None:
        db.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()), None, actor_role, action, target_type, target_id,
                json.dumps(before), json.dumps(after), created_at,
            ),
        )

    def get_portfolio_import(
        self, import_id: str, include_path: bool = False
    ) -> dict[str, Any] | None:
        """Return one portfolio import and its durable job status."""
        self._ensure()
        with closing(self.connect()) as db:
            row = db.execute(
                """SELECT i.*,j.id AS job_id,j.progress,j.message,j.updated_at
                   FROM portfolio_imports i JOIN portfolio_import_jobs j ON j.import_id=i.id
                   WHERE i.id=?""",
                (import_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        if not include_path:
            result.pop("stored_path", None)
        result["summary"] = json.loads(result.pop("summary_json")) if result["summary_json"] else None
        return result

    def list_manpower(
        self, project_code: str | None = None, search: str | None = None,
        department: str | None = None, category: str | None = None,
        status: str | None = None, location: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query current manpower assignments by project and optional text."""
        self._ensure()
        query, params = "SELECT data_json FROM manpower_assignments WHERE 1=1", []
        if project_code:
            query += " AND current_project_code=?"
            params.append(project_code)
        if search:
            query += " AND (name LIKE ? OR emp_code LIKE ? OR department LIKE ? OR category LIKE ?)"
            params.extend([f"%{search}%"] * 4)
        for column, value in (
            ("department", department), ("category", category),
            ("status", status), ("current_location", location),
        ):
            if value:
                query += f" AND {column}=?"
                params.append(value)
        query += " ORDER BY name"
        with closing(self.connect()) as db:
            rows = db.execute(query, params).fetchall()
        return [json.loads(row["data_json"]) for row in rows]

    def list_invoices(
        self, project_code: str | None = None, status: str | None = None,
        level: str | None = None, approval_status: str | None = None,
        payment_status: str | None = None, risk_profile: str | None = None,
        date_from: str | None = None, date_to: str | None = None,
        minimum_aging_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query invoice rows and add live aging values where dates permit."""
        self._ensure()
        query, params = "SELECT data_json FROM project_invoices WHERE 1=1", []
        if project_code:
            query += " AND project_code=?"
            params.append(project_code)
        if status:
            query += " AND status=?"
            params.append(status)
        for column, value in (
            ("levels", level), ("approval_status", approval_status),
            ("payment_status", payment_status), ("risk_profile", risk_profile),
        ):
            if value:
                query += f" AND {column}=?"
                params.append(value)
        if date_from:
            query += " AND submission_date>=?"
            params.append(date_from)
        if date_to:
            query += " AND submission_date<=?"
            params.append(date_to)
        with closing(self.connect()) as db:
            rows = db.execute(query, params).fetchall()
        today, results = date.today(), []
        for row in rows:
            item = json.loads(row["data_json"])
            item["live_aging_days"] = self._days_since(item.get("submission_date"), today)
            item["live_days_to_remittance"] = self._days_until(
                item.get("expected_remittance_date"), today
            )
            if minimum_aging_days is None or (
                item["live_aging_days"] is not None
                and item["live_aging_days"] >= minimum_aging_days
            ):
                results.append(item)
        return results

    def invoice_pivot(self) -> list[dict[str, Any]]:
        """Aggregate the authoritative invoice pivot directly in SQLite."""
        self._ensure()
        with closing(self.connect()) as db:
            rows = db.execute(
                """SELECT COALESCE(levels,'') AS levels,COALESCE(status,'') AS status,
                          project_code,ROUND(SUM(invoice_value_usd),2) AS total
                   FROM project_invoices
                   GROUP BY levels,status,project_code
                   ORDER BY levels,status,project_code"""
            ).fetchall()
        grouped: dict[tuple[str, str], dict[str, float]] = {}
        for row in rows:
            key = (row["levels"], row["status"])
            grouped.setdefault(key, {})[row["project_code"]] = row["total"]
        return [
            {
                "levels": levels,
                "status": status,
                "projects": projects,
                "grand_total": round(sum(projects.values()), 2),
            }
            for (levels, status), projects in grouped.items()
        ]

    @staticmethod
    def _days_since(value: str | None, today: date) -> int | None:
        try:
            return max(0, (today - date.fromisoformat(value or "")).days)
        except ValueError:
            return None

    @staticmethod
    def _days_until(value: str | None, today: date) -> int | None:
        try:
            return (date.fromisoformat(value or "") - today).days
        except ValueError:
            return None

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

    def update_project(
        self, project_code: str, updates: dict[str, Any], actor_role: str
    ) -> dict[str, Any]:
        """Update one existing project immediately and preserve an audit trail."""
        if actor_role not in {"project_manager", "planning_engineer", "admin"}:
            raise PermissionError("This role cannot update projects")
        self._ensure()
        with closing(self.connect()) as db:
            with db:
                row = db.execute(
                    "SELECT payload FROM projects WHERE code = ?", (project_code,)
                ).fetchone()
                if not row:
                    raise KeyError("Project not found")
                before = json.loads(row["payload"])
                after = {**before, **updates, "code": project_code}
                values = {**after, "payload": json.dumps(after)}
                db.execute(
                    """UPDATE projects SET name=:name,status=:status,client=:client,
                    location=:location,contract_value_usd=:contract_value_usd,
                    planned_start=:planned_start,planned_finish=:planned_finish,
                    revised_finish=:revised_finish,reporting_date=:reporting_date,
                    baseline_progress=:baseline_progress,revised_progress=:revised_progress,
                    actual_progress=:actual_progress,payload=:payload WHERE code=:code""",
                    values,
                )
                db.execute(
                    "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), None, actor_role, "project_update", "project",
                        project_code, json.dumps(before), json.dumps(after), self._now(),
                    ),
                )
        project = self.find_project(project_code, actor_role)
        if not project:
            raise KeyError("Project not found")
        return project

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
                terminal = (
                    "processing"
                    if decision == "approved" and change["action"] == "pdf_ingestion"
                    else "ready" if decision == "approved" else "rejected"
                )
                db.execute(
                    """UPDATE documents SET status=? WHERE id IN
                       (SELECT document_id FROM ingestion_jobs WHERE change_request_id=?)""",
                    (terminal, change_id),
                )
                if terminal == "ready":
                    db.execute(
                        "DELETE FROM ingestion_jobs WHERE change_request_id=?",
                        (change_id,),
                    )
                else:
                    db.execute(
                        """UPDATE ingestion_jobs SET status=?, message=?, updated_at=?
                           WHERE change_request_id=?""",
                        (terminal, f"Change {decision}", self._now(), change_id),
                    )
                db.execute(
                    "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()), None, actor_role, decision, "change_request", change_id,
                        json.dumps(change["preview"].get("before")),
                        json.dumps(change["preview"].get("after")), self._now(),
                    ),
                )
                db.execute(
                    """UPDATE notifications SET read_at=COALESCE(read_at, ?)
                       WHERE recipient_role='admin' AND event_type='approval_required'
                       AND change_request_id=?""",
                    (self._now(), change_id),
                )
                result_event = "change_approved" if decision == "approved" else "change_rejected"
                if change["requested_by"] != "admin":
                    self._insert_notification(
                        db, change["requested_by"], result_event, change["project_code"],
                        change_id,
                        "Change approved" if decision == "approved" else "Change rejected",
                        f"Your {change['action'].replace('_', ' ')} request was {decision}.",
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
        elif action == "pdf_ingestion":
            return
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

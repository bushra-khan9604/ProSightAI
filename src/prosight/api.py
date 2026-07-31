"""FastAPI transport for queries, uploads, approvals, and the React application."""

from __future__ import annotations

import asyncio
import logging
import hashlib
import json
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agents import MultiAgentOrchestrator
from .agents.rag_agent import RAGAgent
from .config import get_settings
from .ingestion import IngestionManager
from .ingestion.excel import preview_workbook
from .ingestion.portfolio import create_portfolio_template, parse_portfolio_workbook
from .observability import RequestTrace, configure_logging, sanitize
from .rag import RAGStore
from .repository import DEFAULT_DB, ProjectRepository


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"
UPLOAD_DIR = ROOT / "data" / "uploads"
VECTOR_DIR = ROOT / "data" / "vector_store"
PORTFOLIO_DIR = ROOT / "data" / "portfolio_imports"
ROLES = {"project_manager", "planning_engineer", "admin"}
CHANGE_PREVIEW_ROLES = {"project_manager", "admin"}
PROJECT_UPDATE_ROLES = {"project_manager", "planning_engineer", "admin"}


class ChatHistoryMessage(BaseModel):
    """One user-visible message supplied as temporary conversation context."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10_000)


class QueryRequest(BaseModel):
    """Validated AI Assistant query."""

    query: str = Field(min_length=1, max_length=10_000)
    user_role: str = "project_manager"
    project_code: str | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=20)


class ProjectDraft(BaseModel):
    """Validated new-project payload stored as an approval request."""

    code: str = Field(pattern=r"^[A-Z0-9-]{3,30}$")
    name: str = Field(min_length=3, max_length=200)
    status: Literal["active", "completed", "future"]
    client: str = Field(min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=200)
    contract_value_usd: float = Field(ge=0)
    planned_start: str
    planned_finish: str
    revised_finish: str | None = None
    reporting_date: str
    baseline_progress: float = Field(ge=0, le=100)
    revised_progress: float = Field(ge=0, le=100)
    actual_progress: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_dates(self) -> "ProjectDraft":
        """Require ISO dates and coherent project schedule boundaries."""
        try:
            planned_start = date.fromisoformat(self.planned_start)
            planned_finish = date.fromisoformat(self.planned_finish)
            revised_finish = date.fromisoformat(self.revised_finish) if self.revised_finish else None
            date.fromisoformat(self.reporting_date)
        except ValueError as error:
            raise ValueError("Project dates must use YYYY-MM-DD format") from error
        if planned_finish < planned_start:
            raise ValueError("Planned finish cannot be before planned start")
        if revised_finish and revised_finish < planned_start:
            raise ValueError("Revised finish cannot be before planned start")
        return self


class ProjectUpdate(BaseModel):
    """Validated mutable fields for an existing project."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=200)
    status: Literal["active", "completed", "future"]
    client: str = Field(min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=200)
    contract_value_usd: float = Field(ge=0)
    planned_start: str
    planned_finish: str
    revised_finish: str | None = None
    reporting_date: str
    baseline_progress: float = Field(ge=0, le=100)
    revised_progress: float = Field(ge=0, le=100)
    actual_progress: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_dates(self) -> "ProjectUpdate":
        """Apply the same date invariants as new-project creation."""
        ProjectDraft(code="VALIDATION", **self.model_dump())
        return self


class DocumentDateConfirmation(BaseModel):
    """User-confirmed reporting date for a pending PDF ingestion job."""

    reporting_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class Runtime:
    """Application dependencies shared by API handlers and background workers."""

    def __init__(self, repository: ProjectRepository):
        self.repository = repository
        self.repository._ensure()
        self.rag_store: RAGStore | None = None
        self.ingestion: IngestionManager | None = None
        try:
            self.rag_store = RAGStore(VECTOR_DIR)
            self.ingestion = IngestionManager(repository, self.rag_store, UPLOAD_DIR)
        except RuntimeError:
            # Queries and database features remain usable before an API key is configured.
            logging.getLogger("prosight").warning("rag_runtime_unavailable")
        self.orchestrator = MultiAgentOrchestrator(
            repository, RAGAgent(self.rag_store) if self.rag_store else None
        )


def create_app(repository: ProjectRepository | None = None) -> FastAPI:
    """Build an independently testable FastAPI application."""
    configure_logging()
    runtime = Runtime(repository or ProjectRepository(DEFAULT_DB))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Release worker and Chroma resources during graceful shutdown."""
        yield
        if runtime.ingestion:
            runtime.ingestion.close()

    app = FastAPI(title="ProSight AI", version="0.2.0", lifespan=lifespan)
    app.state.runtime = runtime

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "llm_provider": "openai",
            "model": get_settings().openai_model,
            "rag_available": runtime.rag_store is not None,
        }

    @app.get("/api/projects")
    def projects(role: str = Query("project_manager")) -> list[dict]:
        _validate_role(role)
        return runtime.repository.list_projects(user_role=role)

    @app.post("/api/projects/change-preview", status_code=202)
    def create_project_preview(
        draft: ProjectDraft,
        role: str = Query(...),
    ) -> dict:
        """Create a reviewed project-addition request without mutating immediately."""
        _validate_role(role)
        _require_role(role, CHANGE_PREVIEW_ROLES, "This role cannot prepare project changes")
        if runtime.repository.find_project(draft.code, "admin"):
            raise HTTPException(status_code=409, detail="Project code already exists")
        project = {
            **draft.model_dump(),
            "revised_finish": draft.revised_finish or draft.planned_finish,
            "contacts": [],
            "activities": [],
            "manpower": [],
            "equipment": [],
            "total_manhours": 0,
            "milestones": [],
            "sources": [f"{role.replace('_', ' ').title()} new-project form"],
        }
        return runtime.repository.create_change_request(
            "excel_import",
            draft.code,
            {"projects": [project]},
            {"before": None, "after": project, "warnings": []},
            role,
        )

    @app.post("/api/projects/import-preview", status_code=202)
    def create_project_import_preview(
        role: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict:
        """Validate one canonical workbook and create an editable import preview."""
        _validate_role(role)
        _require_role(role, CHANGE_PREVIEW_ROLES, "This role cannot prepare project imports")
        filename = Path(file.filename or "").name
        if Path(filename).suffix.lower() != ".xlsx":
            raise HTTPException(status_code=400, detail="A canonical .xlsx workbook is required")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temporary:
            shutil.copyfileobj(file.file, temporary)
            temp_path = Path(temporary.name)
        try:
            preview = preview_workbook(temp_path, "")
            if preview["mapping_required"]:
                raise HTTPException(
                    status_code=400,
                    detail="New-project creation requires the canonical workbook format",
                )
            if len(preview["projects"]) != 1:
                raise HTTPException(
                    status_code=400,
                    detail="New-project workbooks must contain exactly one project row",
                )
            project = preview["projects"][0]
            if runtime.repository.find_project(project["code"], "admin"):
                raise HTTPException(status_code=409, detail="Project code already exists")
            counts = {
                field: len(project.get(field, []))
                for field in ("contacts", "activities", "manpower", "equipment", "milestones")
            }
            change = runtime.repository.create_change_request(
                "excel_import",
                project["code"],
                {"projects": [project]},
                {
                    "before": None,
                    "after": project,
                    "warnings": preview["warnings"],
                    "related_counts": counts,
                    "source_filename": filename,
                },
                role,
            )
            return change
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            temp_path.unlink(missing_ok=True)

    @app.patch("/api/projects/{project_code}")
    def update_project(
        project_code: str,
        update: ProjectUpdate,
        role: str = Query(...),
    ) -> dict:
        """Immediately update mutable project fields and create an audit record."""
        _validate_role(role)
        _require_role(role, PROJECT_UPDATE_ROLES, "This role cannot update projects")
        try:
            return runtime.repository.update_project(
                project_code,
                {
                    **update.model_dump(),
                    "revised_finish": update.revised_finish or update.planned_finish,
                },
                role,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.patch("/api/change-requests/{change_id}")
    def update_change_request(
        change_id: str,
        draft: ProjectDraft,
        role: str = Query(...),
    ) -> dict:
        """Apply validated form edits to one pending project import."""
        _validate_role(role)
        _require_role(role, CHANGE_PREVIEW_ROLES, "This role cannot edit project changes")
        existing = runtime.repository.find_project(draft.code, "admin")
        if existing:
            raise HTTPException(status_code=409, detail="Project code already exists")
        try:
            return runtime.repository.update_pending_project_change(
                change_id,
                {
                    **draft.model_dump(),
                    "revised_finish": draft.revised_finish or draft.planned_finish,
                },
                role,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/summary")
    def summary(role: str = Query("project_manager")) -> dict:
        _validate_role(role)
        return runtime.repository.portfolio_summary(role)

    @app.post("/api/query")
    def query(payload: QueryRequest) -> dict:
        trace = RequestTrace()
        try:
            _validate_role(payload.user_role)
            trace.event(
                "query_received",
                role=payload.user_role,
                project_code=payload.project_code,
                query_preview=sanitize(payload.query),
            )
            trace.event(
                "query_validated",
                role=payload.user_role,
                project_code=payload.project_code,
                query_length=len(payload.query),
                history_count=len(payload.history),
            )
            result = runtime.orchestrator.run(
                payload.query.strip(),
                payload.user_role,
                payload.project_code,
                trace,
                [message.model_dump() for message in payload.history],
            )
            result.update(request_id=trace.request_id, duration_ms=trace.duration_ms)
            trace.event(
                "response_generated",
                provider=result["mode"],
                agent_route=result.get("agent_route", []),
                citation_count=len(result.get("citations", [])),
                response_preview=sanitize(result.get("answer", "")),
            )
            trace.event(
                "response_sent",
                status=200,
                provider=result["mode"],
                agent_route=result.get("agent_route", []),
            )
            return result
        except HTTPException:
            raise
        except (ValueError, PermissionError) as error:
            trace.event("query_failed", level=logging.WARNING, error_type=type(error).__name__)
            raise HTTPException(
                status_code=400,
                detail={"error": str(error), "request_id": trace.request_id},
            ) from error
        except Exception as error:
            trace.event("query_failed", level=logging.ERROR, error_type=type(error).__name__)
            raise HTTPException(
                status_code=500,
                detail={"error": "internal_error", "request_id": trace.request_id},
            ) from error

    @app.post("/api/query/stream")
    async def query_stream(payload: QueryRequest) -> StreamingResponse:
        """Stream real orchestration states and a final backward-compatible answer."""
        _validate_role(payload.user_role)

        def encode(event_name: str, data: dict) -> str:
            return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        labels = {
            "thinking": "Thinking",
            "checking_database": "Checking database",
            "creating_response": "Creating response",
        }

        async def generate():
            trace = RequestTrace()
            loop = asyncio.get_running_loop()
            statuses: asyncio.Queue[str] = asyncio.Queue()
            last_state: str | None = None

            def report(state: str) -> None:
                loop.call_soon_threadsafe(statuses.put_nowait, state)

            trace.event("query_received", role=payload.user_role,
                        project_code=payload.project_code,
                        query_preview=sanitize(payload.query))
            trace.event("query_validated", role=payload.user_role,
                        project_code=payload.project_code,
                        query_length=len(payload.query), history_count=len(payload.history))
            yield encode("meta", {"request_id": trace.request_id})
            yield encode("status", {"state": "thinking", "label": "Thinking"})
            try:
                task = asyncio.create_task(asyncio.to_thread(
                    runtime.orchestrator.run,
                    payload.query.strip(), payload.user_role, payload.project_code, trace,
                    [message.model_dump() for message in payload.history], report,
                ))
                while not task.done():
                    try:
                        state = await asyncio.wait_for(statuses.get(), timeout=.1)
                    except asyncio.TimeoutError:
                        continue
                    if state != last_state:
                        last_state = state
                        yield encode("status", {
                            "state": state,
                            "label": labels.get(state, "Thinking"),
                        })
                result = await task
                while not statuses.empty():
                    state = statuses.get_nowait()
                    if state != last_state:
                        last_state = state
                        yield encode("status", {
                            "state": state,
                            "label": labels.get(state, "Thinking"),
                        })
                result.update(request_id=trace.request_id, duration_ms=trace.duration_ms)
                trace.event("response_generated", provider=result["mode"],
                            agent_route=result.get("agent_route", []),
                            citation_count=len(result.get("citations", [])),
                            response_preview=sanitize(result.get("answer", "")))
                yield encode("final", result)
                trace.event("response_sent", status=200, provider=result["mode"],
                            agent_route=result.get("agent_route", []))
            except Exception as error:
                logging.getLogger("prosight").exception(
                    "query_stream_failed", extra={"event_data": {
                        "event": "query_stream_failed", "request_id": trace.request_id,
                        "error_type": type(error).__name__,
                    }},
                )
                yield encode("error", {
                    "message": "The Assistant could not complete the request.",
                    "request_id": trace.request_id,
                })

        return StreamingResponse(generate(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        })

    @app.post("/api/uploads", status_code=202)
    def upload(
        project_code: str = Form(...),
        user_role: str = Form("project_manager"),
        file: UploadFile = File(...),
    ) -> dict:
        _validate_role(user_role)
        if not runtime.ingestion:
            raise HTTPException(
                status_code=503,
                detail="Document ingestion requires OPENAI_API_KEY and installed RAG dependencies",
            )
        if not runtime.repository.find_project(project_code, user_role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        suffix = Path(file.filename or "").suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            shutil.copyfileobj(file.file, temporary)
            temp_path = Path(temporary.name)
        try:
            return runtime.ingestion.submit(
                temp_path, file.filename or "", project_code, user_role
            )
        except (ValueError, PermissionError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            temp_path.unlink(missing_ok=True)

    @app.get("/api/ingestion-jobs/{job_id}")
    def ingestion_job(
        job_id: str, role: str = Query(...),
    ) -> dict:
        _validate_role(role)
        job = runtime.repository.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        return job

    @app.post("/api/ingestion-jobs/{job_id}/confirm-date")
    def confirm_document_date(
        job_id: str,
        confirmation: DocumentDateConfirmation,
        role: str = Query(...),
    ) -> dict:
        """Confirm the PDF reporting date and resume indexing."""
        _validate_role(role)
        if not runtime.ingestion:
            raise HTTPException(status_code=503, detail="RAG runtime unavailable")
        try:
            return runtime.ingestion.confirm_pdf_date(
                job_id, confirmation.reporting_date, role
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/projects/{project_code}/documents")
    def documents(project_code: str, role: str = Query("project_manager")) -> list[dict]:
        _validate_role(role)
        if not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_documents(project_code)

    @app.get("/api/projects/{project_code}/ingestion-jobs")
    def project_ingestion_jobs(
        project_code: str, role: str = Query("project_manager")
    ) -> list[dict]:
        _validate_role(role)
        if not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_jobs(project_code)

    @app.post("/api/portfolio-imports")
    def portfolio_import(
        role: str = Form(...), dataset: str = Form("combined"),
        project_code: str | None = Form(None), file: UploadFile = File(...)
    ) -> dict:
        _validate_role(role)
        _require_role(
            role, {"project_manager", "planning_engineer", "admin"},
            "This role cannot import portfolio data",
        )
        if dataset not in {"combined", "manpower", "invoices", "schedule"}:
            raise HTTPException(status_code=400, detail="Unsupported portfolio import dataset")
        if dataset == "schedule":
            if not project_code:
                raise HTTPException(status_code=400, detail="Select a project for the schedule import")
            if not runtime.repository.find_project(project_code, role):
                raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        filename = Path(file.filename or "").name
        if Path(filename).suffix.lower() != ".xlsx":
            raise HTTPException(status_code=400, detail="Portfolio imports must be XLSX files")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temporary:
            shutil.copyfileobj(file.file, temporary)
            temp_path = Path(temporary.name)
        try:
            if temp_path.stat().st_size > 20 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Portfolio workbook exceeds 20 MB")
            content = temp_path.read_bytes()
            if not content.startswith(b"PK"):
                raise HTTPException(status_code=400, detail="File content is not a valid XLSX workbook")
            checksum = hashlib.sha256(content).hexdigest()
            PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
            destination = PORTFOLIO_DIR / f"{uuid.uuid4()}-{filename}"
            shutil.copy2(temp_path, destination)
            record = runtime.repository.create_portfolio_import(
                filename, checksum, str(destination), role, dataset, project_code
            )
            try:
                parsed = parse_portfolio_workbook(
                    destination, runtime.repository.resolve_project_reference,
                    dataset, project_code
                )
                return runtime.repository.apply_portfolio_import(record["id"], parsed)
            except (ValueError, KeyError) as error:
                failed = runtime.repository.fail_portfolio_import(record["id"], str(error))
                raise HTTPException(
                    status_code=400,
                    detail={"message": str(error), "import": failed},
                ) from error
            except Exception as error:
                logging.getLogger("prosight.portfolio").exception(
                    "portfolio_import_failed", extra={"import_id": record["id"]}
                )
                message = "The portfolio workbook could not be processed. Check its format and try again."
                failed = runtime.repository.fail_portfolio_import(record["id"], message)
                raise HTTPException(
                    status_code=500, detail={"message": message, "import": failed}
                ) from error
        finally:
            temp_path.unlink(missing_ok=True)

    @app.get("/api/portfolio-imports/template")
    def portfolio_import_template(
        role: str = Query(...), dataset: str = Query("combined")
    ) -> FileResponse:
        _validate_role(role)
        if dataset not in {"combined", "manpower", "invoices", "schedule"}:
            raise HTTPException(status_code=400, detail="Unsupported portfolio template dataset")
        PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
        labels = {"combined": "Portfolio", "manpower": "Manpower",
                  "invoices": "Project-Invoices", "schedule": "Project-Schedule"}
        filename = f"ProSight-{labels[dataset]}-Import-Template.xlsx"
        path = PORTFOLIO_DIR / filename
        create_portfolio_template(path, dataset)
        return FileResponse(
            path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/api/portfolio-imports/{import_id}")
    def portfolio_import_status(import_id: str, role: str = Query(...)) -> dict:
        _validate_role(role)
        record = runtime.repository.get_portfolio_import(import_id)
        if not record:
            raise HTTPException(status_code=404, detail="Portfolio import not found")
        if role != "admin" and record["uploaded_by"] != role:
            raise HTTPException(status_code=403, detail="Portfolio import is restricted")
        return record

    @app.get("/api/portfolio/manpower")
    def portfolio_manpower(
        role: str = Query(...), project_code: str | None = Query(None),
        search: str | None = Query(None), department: str | None = Query(None),
        category: str | None = Query(None), status: str | None = Query(None),
        location: str | None = Query(None),
    ) -> list[dict]:
        _validate_role(role)
        if project_code and not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_manpower(
            project_code, search, department, category, status, location
        )

    @app.get("/api/projects/{project_code}/schedule")
    def project_schedule(project_code: str, role: str = Query(...)) -> list[dict]:
        _validate_role(role)
        if not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_project_schedule(project_code)

    @app.get("/api/portfolio/invoices")
    def portfolio_invoices(
        role: str = Query(...), project_code: str | None = Query(None),
        status: str | None = Query(None), level: str | None = Query(None),
        approval_status: str | None = Query(None),
        payment_status: str | None = Query(None),
        risk_profile: str | None = Query(None),
        date_from: str | None = Query(None), date_to: str | None = Query(None),
        minimum_aging_days: int | None = Query(None, ge=0),
    ) -> list[dict]:
        _validate_role(role)
        if project_code and not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_invoices(
            project_code, status, level, approval_status, payment_status,
            risk_profile, date_from, date_to, minimum_aging_days,
        )

    @app.get("/api/portfolio/invoice-pivot")
    def portfolio_invoice_pivot(role: str = Query(...)) -> list[dict]:
        _validate_role(role)
        return runtime.repository.invoice_pivot()

    @app.delete("/api/documents/{document_id}")
    def delete_document(document_id: str, role: str = Query(...)) -> dict:
        _validate_role(role)
        _require_role(role, {"admin"}, "Only Admin can delete documents")
        if not runtime.ingestion:
            raise HTTPException(status_code=503, detail="RAG runtime unavailable")
        try:
            return runtime.ingestion.delete_document(document_id, role)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/change-requests/{change_id}")
    def change_request(change_id: str, role: str = Query("project_manager")) -> dict:
        _validate_role(role)
        change = runtime.repository.get_change_request(change_id)
        if not change:
            raise HTTPException(status_code=404, detail="Change request not found")
        return change

    @app.get("/api/notifications")
    def notifications(
        role: str = Query(...), status: Literal["unread", "all"] = Query("all")
    ) -> dict:
        _validate_role(role)
        return runtime.repository.list_notifications(role, status == "unread")

    @app.post("/api/notifications/{notification_id}/read")
    def read_notification(notification_id: str, role: str = Query(...)) -> dict:
        _validate_role(role)
        try:
            return runtime.repository.mark_notification_read(notification_id, role)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/notifications/read-all")
    def read_all_notifications(role: str = Query(...)) -> dict:
        _validate_role(role)
        return {"updated": runtime.repository.mark_all_notifications_read(role)}

    @app.get("/api/approvals")
    def approvals(
        role: str = Query(...), status: Literal["pending"] = Query("pending")
    ) -> dict:
        _validate_role(role)
        _require_role(role, {"admin"}, "Only Admin can access the approval queue")
        return {"items": runtime.repository.list_pending_approvals()}

    @app.post("/api/change-requests/{change_id}/{decision}")
    def decide_change(
        change_id: str,
        decision: Literal["approve", "reject"],
        role: str = Query(...),
    ) -> dict:
        _validate_role(role)
        _require_role(role, {"admin"}, "Only Admin can approve or reject changes")
        try:
            return runtime.repository.decide_change_request(
                change_id, "approved" if decision == "approve" else "rejected", role
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        target = (FRONTEND_DIST / path).resolve()
        if path and target.is_file() and FRONTEND_DIST.resolve() in target.parents:
            return FileResponse(target)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend build not found")

    return app


def _validate_role(role: str) -> None:
    """Reject unknown role names at the transport boundary."""
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid user role")


def _require_role(role: str, allowed: set[str], detail: str) -> None:
    """Return a consistent forbidden response for a valid but unauthorized role."""
    if role not in allowed:
        raise HTTPException(status_code=403, detail=detail)


app = create_app()


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run ProSight with Uvicorn."""
    import uvicorn

    uvicorn.run("prosight.api:app", host=host, port=port, reload=False)

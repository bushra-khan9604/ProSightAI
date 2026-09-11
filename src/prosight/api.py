"""FastAPI transport for queries, uploads, approvals, and the React application."""

from __future__ import annotations

import asyncio
import logging
import hashlib
import json
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agents import MultiAgentOrchestrator
from .agents.rag_agent import RAGAgent
from .auth import SupabaseAuthVerifier, current_auth, require_current_auth
from .config import get_settings
from .ingestion import IngestionManager
from .ingestion.excel import preview_workbook
from .ingestion.portfolio import create_portfolio_template, parse_portfolio_workbook
from .observability import RequestTrace, configure_logging, sanitize
from .rag import RAGStore
from .repository import DEFAULT_DB, ProjectRepository
from .supabase_repository import SupabaseProjectRepository
from .supabase_gateway import current_access_token


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"
UPLOAD_DIR = ROOT / "data" / "uploads"
VECTOR_DIR = ROOT / "data" / "vector_store"
PORTFOLIO_DIR = ROOT / "data" / "portfolio_imports"
ROLES = {"employee", "project_manager", "planning_engineer", "admin"}
CHANGE_PREVIEW_ROLES = {"project_manager", "admin"}
PROJECT_UPDATE_ROLES = {"project_manager", "planning_engineer", "admin"}


class ChatHistoryMessage(BaseModel):
    """One user-visible message supplied as temporary conversation context."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10_000)


class QueryRequest(BaseModel):
    """Validated AI Assistant query."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=10_000)
    project_code: str | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)


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

    def __init__(self, repository):
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


def create_app(repository=None) -> FastAPI:
    """Build an independently testable FastAPI application."""
    configure_logging()
    settings = get_settings()
    use_supabase = repository is None and (
        settings.data_backend == "supabase"
        or (settings.data_backend == "auto" and bool(settings.supabase_url))
    )
    runtime = Runtime(repository or (SupabaseProjectRepository() if use_supabase else ProjectRepository(DEFAULT_DB)))
    auth_verifier = SupabaseAuthVerifier() if use_supabase else None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Release ingestion workers and retrieval resources during shutdown."""
        yield
        if runtime.ingestion:
            runtime.ingestion.close()

    app = FastAPI(title="ProSight AI", version="0.2.0", lifespan=lifespan)
    app.state.runtime = runtime
    app.state.auth_required = auth_verifier is not None

    @app.middleware("http")
    async def authenticate_api(request: Request, call_next):
        """Protect application APIs and install an RLS-aware request identity."""
        if not auth_verifier or request.url.path in {"/health", "/api/health"} or not request.url.path.startswith("/api/"):
            return await call_next(request)
        try:
            context = await asyncio.to_thread(
                auth_verifier.verify, request.headers.get("authorization")
            )
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
        auth_token = current_auth.set(context)
        access_token = current_access_token.set(context.access_token)
        try:
            return await call_next(request)
        finally:
            current_access_token.reset(access_token)
            current_auth.reset(auth_token)

    def caller_role(request: Request) -> str:
        context = current_auth.get()
        # The query fallback exists only for explicitly injected legacy test repositories.
        legacy_role = request.query_params.get("role") if request and not use_supabase else None
        role = context.role if context else (legacy_role or "project_manager")
        _validate_role(role)
        return role

    def require_project_access(project_code: str) -> None:
        """Reject authenticated cross-project requests before repository access."""
        context = current_auth.get()
        if context and context.role != "admin" and project_code not in context.project_codes:
            raise HTTPException(status_code=403, detail="Project membership is required")

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict:
        rag_health = {
            "status": "unavailable",
            "database": "ready" if not use_supabase else "unknown",
            "openai_configured": bool(settings.openai_api_key),
            "embedding_model": settings.embedding_model,
            "pending_jobs": None,
            "failed_jobs": None,
        }
        if use_supabase:
            try:
                runtime.repository.service.select(
                    "document_chunks", select="id", limit="1"
                )
                rag_health["database"] = "ready"
            except Exception:
                rag_health["database"] = "unavailable"
        if runtime.rag_store:
            try:
                rag_health = {
                    **rag_health,
                    **runtime.rag_store.health(),
                    "database": "ready",
                }
            except Exception:
                logging.getLogger("prosight").exception("rag_health_check_failed")
                rag_health["status"] = "degraded"
                rag_health["database"] = "unavailable"
        return {
            "status": "ok",
            "llm_provider": "openai",
            "model": settings.openai_model,
            "rag_available": runtime.rag_store is not None,
            "data_backend": "supabase" if use_supabase else "sqlite",
            "rag": rag_health,
        }

    @app.get("/api/me")
    def me() -> dict:
        context = require_current_auth()
        return {
            "id": context.user_id, "email": context.email,
            "display_name": context.display_name, "role": context.role,
            "project_codes": list(context.project_codes),
        }

    @app.get("/api/projects")
    def projects(role: str = Depends(caller_role)) -> list[dict]:
        return runtime.repository.list_projects(user_role=role)

    @app.post("/api/projects/change-preview", status_code=202)
    def create_project_preview(
        draft: ProjectDraft,
        role: str = Depends(caller_role),
    ) -> dict:
        """Create a reviewed project-addition request without mutating immediately."""
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
        file: UploadFile = File(...),
        role: str = Depends(caller_role),
    ) -> dict:
        """Validate one canonical workbook and create an editable import preview."""
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
        role: str = Depends(caller_role),
    ) -> dict:
        """Immediately update mutable project fields and create an audit record."""
        require_project_access(project_code)
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
        role: str = Depends(caller_role),
    ) -> dict:
        """Apply validated form edits to one pending project import."""
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
    def summary(role: str = Depends(caller_role)) -> dict:
        return runtime.repository.portfolio_summary(role)

    @app.post("/api/query")
    async def query(payload: QueryRequest, role: str = Depends(caller_role)) -> dict:
        trace = RequestTrace()
        if payload.project_code:
            require_project_access(payload.project_code)
        try:
            trace.event(
                "query_received",
                role=role,
                project_code=payload.project_code,
                query_preview=sanitize(payload.query),
            )
            trace.event(
                "query_validated",
                role=role,
                project_code=payload.project_code,
                query_length=len(payload.query),
                history_count=len(payload.history),
            )
            result = await runtime.orchestrator.run_async(
                payload.query.strip(),
                role,
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
    async def query_stream(
        payload: QueryRequest, request: Request, role: str = Depends(caller_role)
    ) -> StreamingResponse:
        """Stream real orchestration states and a final backward-compatible answer."""
        if payload.project_code:
            require_project_access(payload.project_code)
        def encode(event_name: str, data: dict) -> str:
            return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        labels = {
            "thinking": "Thinking",
            "checking_database": "Checking database",
            "creating_response": "Creating response",
        }

        async def generate():
            trace = RequestTrace()
            trace.event("query_received", role=role,
                        project_code=payload.project_code,
                        query_preview=sanitize(payload.query))
            trace.event("query_validated", role=role,
                        project_code=payload.project_code,
                        query_length=len(payload.query), history_count=len(payload.history))
            yield encode("meta", {"request_id": trace.request_id})
            yield encode("status", {"state": "thinking", "label": "Thinking"})
            event_stream = runtime.orchestrator.stream(
                payload.query.strip(), role, payload.project_code, trace,
                [message.model_dump() for message in payload.history],
            )
            iterator = event_stream.__aiter__()
            next_event: asyncio.Task | None = None
            try:
                next_event = asyncio.create_task(anext(iterator))
                while True:
                    done, _ = await asyncio.wait({next_event}, timeout=15)
                    if not done:
                        if await request.is_disconnected():
                            next_event.cancel()
                            with suppress(asyncio.CancelledError):
                                await next_event
                            return
                        yield ": keep-alive\n\n"
                        continue
                    try:
                        event_name, data = next_event.result()
                    except StopAsyncIteration:
                        break
                    if event_name == "status":
                        data["label"] = labels.get(data.get("state"), data.get("label", "Thinking"))
                    elif event_name == "final":
                        data.update(request_id=trace.request_id, duration_ms=trace.duration_ms)
                        trace.event("response_generated", provider=data["mode"],
                                    agent_route=data.get("agent_route", []),
                                    citation_count=len(data.get("citations", [])),
                                    response_preview=sanitize(data.get("answer", "")),
                                    time_to_first_token_ms=data.get("time_to_first_token_ms"))
                    elif event_name == "error":
                        data["request_id"] = trace.request_id
                    yield encode(event_name, data)
                    if event_name == "final":
                        trace.event("response_sent", status=200, provider=data["mode"],
                                    agent_route=data.get("agent_route", []))
                    if event_name == "error":
                        return
                    next_event = asyncio.create_task(anext(iterator))
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
                    "partial": False,
                })
            finally:
                if next_event and not next_event.done():
                    next_event.cancel()
                    with suppress(asyncio.CancelledError):
                        await next_event
                await event_stream.aclose()

        return StreamingResponse(generate(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        })

    @app.post("/api/uploads", status_code=202)
    def upload(
        project_code: str = Form(...),
        file: UploadFile = File(...),
        user_role: str = Depends(caller_role),
    ) -> dict:
        require_project_access(project_code)
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
        job_id: str, role: str = Depends(caller_role),
    ) -> dict:
        job = runtime.repository.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        return job

    @app.post("/api/ingestion-jobs/{job_id}/confirm-date")
    def confirm_document_date(
        job_id: str,
        confirmation: DocumentDateConfirmation,
        role: str = Depends(caller_role),
    ) -> dict:
        """Confirm the PDF reporting date and resume indexing."""
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
    def documents(project_code: str, role: str = Depends(caller_role)) -> list[dict]:
        require_project_access(project_code)
        if not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_documents(project_code)

    @app.get("/api/projects/{project_code}/ingestion-jobs")
    def project_ingestion_jobs(
        project_code: str, role: str = Depends(caller_role)
    ) -> list[dict]:
        require_project_access(project_code)
        if not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_jobs(project_code)

    @app.delete("/api/ingestion-jobs/{job_id}")
    def clear_failed_ingestion_job(job_id: str, role: str = Depends(caller_role)) -> dict:
        """Permanently clear one failed upload after project and role authorization."""
        _require_role(
            role, {"project_manager", "planning_engineer", "admin"},
            "This role cannot clear failed ingestion jobs",
        )
        job = runtime.repository.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Ingestion job not found")
        if job["status"] != "failed":
            raise HTTPException(status_code=409, detail="Only failed ingestion jobs can be cleared")
        document = runtime.repository.get_document(job["document_id"])
        if not document or not runtime.repository.find_project(document["project_code"], role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        if job.get("change_request_id"):
            change = runtime.repository.get_change_request(job["change_request_id"])
            if change and change["status"] == "pending":
                raise HTTPException(
                    status_code=409,
                    detail="This failed job still has an unresolved change request",
                )
        if not runtime.ingestion:
            raise HTTPException(status_code=503, detail="Ingestion runtime unavailable")
        try:
            return runtime.ingestion.clear_failed_job(job_id, role)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error).strip("'")) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            logging.getLogger("prosight.ingestion").exception(
                "failed_ingestion_cleanup_failed", extra={"job_id": job_id}
            )
            raise HTTPException(
                status_code=500, detail="The failed upload could not be cleared"
            ) from error

    @app.post("/api/portfolio-imports")
    def portfolio_import(
        dataset: str = Form("combined"), project_code: str | None = Form(None),
        file: UploadFile = File(...), role: str = Depends(caller_role),
    ) -> dict:
        _require_role(
            role, {"project_manager", "planning_engineer", "admin"},
            "This role cannot import portfolio data",
        )
        if dataset not in {"combined", "manpower", "invoices", "schedule"}:
            raise HTTPException(status_code=400, detail="Unsupported portfolio import dataset")
        if dataset == "schedule":
            if not project_code:
                raise HTTPException(status_code=400, detail="Select a project for the schedule import")
            require_project_access(project_code)
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
            store_file = getattr(runtime.repository, "store_portfolio_file", None)
            if store_file:
                store_file(record, destination)
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
        dataset: str = Query("combined"), role: str = Depends(caller_role)
    ) -> FileResponse:
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
    def portfolio_import_status(import_id: str, role: str = Depends(caller_role)) -> dict:
        record = runtime.repository.get_portfolio_import(import_id)
        if not record:
            raise HTTPException(status_code=404, detail="Portfolio import not found")
        auth = current_auth.get()
        if role != "admin" and auth and record["uploaded_by"] != auth.user_id:
            raise HTTPException(status_code=403, detail="Portfolio import is restricted")
        return record

    @app.get("/api/portfolio/manpower")
    def portfolio_manpower(
        project_code: str | None = Query(None),
        search: str | None = Query(None), department: str | None = Query(None),
        category: str | None = Query(None), status: str | None = Query(None),
        location: str | None = Query(None), role: str = Depends(caller_role),
    ) -> list[dict]:
        if project_code:
            require_project_access(project_code)
        if project_code and not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_manpower(
            project_code, search, department, category, status, location
        )

    @app.get("/api/projects/{project_code}/schedule")
    def project_schedule(project_code: str, role: str = Depends(caller_role)) -> list[dict]:
        require_project_access(project_code)
        if not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_project_schedule(project_code)

    @app.get("/api/portfolio/invoices")
    def portfolio_invoices(
        project_code: str | None = Query(None),
        status: str | None = Query(None), level: str | None = Query(None),
        approval_status: str | None = Query(None),
        payment_status: str | None = Query(None),
        risk_profile: str | None = Query(None),
        date_from: str | None = Query(None), date_to: str | None = Query(None),
        minimum_aging_days: int | None = Query(None, ge=0),
        role: str = Depends(caller_role),
    ) -> list[dict]:
        if project_code:
            require_project_access(project_code)
        if project_code and not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        return runtime.repository.list_invoices(
            project_code, status, level, approval_status, payment_status,
            risk_profile, date_from, date_to, minimum_aging_days,
        )

    @app.get("/api/portfolio/invoice-pivot")
    def portfolio_invoice_pivot(role: str = Depends(caller_role)) -> list[dict]:
        return runtime.repository.invoice_pivot()

    @app.delete("/api/documents/{document_id}")
    def delete_document(document_id: str, role: str = Depends(caller_role)) -> dict:
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
    def change_request(change_id: str, role: str = Depends(caller_role)) -> dict:
        change = runtime.repository.get_change_request(change_id)
        if not change:
            raise HTTPException(status_code=404, detail="Change request not found")
        return change

    @app.get("/api/notifications")
    def notifications(
        status: Literal["unread", "all"] = Query("all"),
        role: str = Depends(caller_role),
    ) -> dict:
        return runtime.repository.list_notifications(role, status == "unread")

    @app.post("/api/notifications/{notification_id}/read")
    def read_notification(notification_id: str, role: str = Depends(caller_role)) -> dict:
        try:
            return runtime.repository.mark_notification_read(notification_id, role)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/notifications/read-all")
    def read_all_notifications(role: str = Depends(caller_role)) -> dict:
        return {"updated": runtime.repository.mark_all_notifications_read(role)}

    @app.get("/api/approvals")
    def approvals(
        status: Literal["pending"] = Query("pending"), role: str = Depends(caller_role),
    ) -> dict:
        _require_role(role, {"admin"}, "Only Admin can access the approval queue")
        return {"items": runtime.repository.list_pending_approvals()}

    @app.post("/api/change-requests/{change_id}/{decision}")
    def decide_change(
        change_id: str,
        decision: Literal["approve", "reject"],
        role: str = Depends(caller_role),
    ) -> dict:
        _require_role(role, {"admin"}, "Only Admin can approve or reject changes")
        try:
            change = runtime.repository.get_change_request(change_id)
            if not change:
                raise KeyError("Change request not found")
            result = runtime.repository.decide_change_request(
                change_id, "approved" if decision == "approve" else "rejected", role
            )
            if decision == "approve" and change["action"] == "pdf_ingestion":
                if not runtime.ingestion:
                    raise ValueError("RAG runtime unavailable")
                runtime.ingestion.resume_approved_pdf(change["payload"]["job_id"])
            return result
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

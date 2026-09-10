"""FastAPI transport for queries, uploads, approvals, and the React application."""

from __future__ import annotations

import asyncio
import logging
import hashlib
import json
import shutil
import tempfile
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agents import MultiAgentOrchestrator
from .agents.rag_agent import RAGAgent
from .config import get_settings
from .supabase_auth import get_supabase_user
from .ingestion import IngestionManager
from .ingestion.excel import preview_workbook
from .ingestion.governed_excel import OrganizationMapping
from .ingestion.catalog import (
    OrganizationSheetProfile,
    compile_sheet_profile,
    load_catalog,
    organization_profile_json_schema,
)
from .ingestion.persistence import MappingRecord
from .ingestion.portfolio import create_portfolio_template, parse_portfolio_workbook
from .observability import RequestTrace, configure_logging, sanitize
from .rag import RAGStore
from .redesign_runtime import ThreeLayerRuntime
from .repository import DEFAULT_DB, ProjectRepository


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT / "frontend" / "dist"
UPLOAD_DIR = ROOT / "data" / "uploads"
VECTOR_DIR = ROOT / "data" / "vector_store"
PORTFOLIO_DIR = ROOT / "data" / "portfolio_imports"
ROLES = {"project_manager", "planning_engineer", "admin"}
CHANGE_PREVIEW_ROLES = {"project_manager", "admin"}
PROJECT_UPDATE_ROLES = {"project_manager", "planning_engineer", "admin"}
RESOURCE_CACHE_TTL_SECONDS = 15
_RESOURCE_CACHE: dict[str, tuple[float, Any]] = {}


def _resource_cache_key(endpoint: str, role: str, values: dict[str, Any]) -> str:
    """Build a permission-aware short-lived cache key for dashboard reads."""
    return json.dumps({"endpoint": endpoint, "role": role, **values}, sort_keys=True, default=str)


def _resource_cached(key: str, producer: Any) -> Any:
    """Return a cached dashboard response or compute it once for the pilot."""
    now = time.monotonic()
    cached = _RESOURCE_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]
    value = producer()
    _RESOURCE_CACHE[key] = (now + RESOURCE_CACHE_TTL_SECONDS, value)
    if len(_RESOURCE_CACHE) > 256:
        expired = [item for item, (expires, _) in _RESOURCE_CACHE.items() if expires <= now]
        for item in expired:
            _RESOURCE_CACHE.pop(item, None)
    return value


def _clear_resource_cache() -> None:
    """Invalidate resource summaries after an approved manpower import."""
    _RESOURCE_CACHE.clear()


def _mask_resource_record(item: dict[str, Any], role: str) -> dict[str, Any]:
    """Keep operational fields visible while masking commercial rates by role."""
    result = dict(item)
    if role != "admin":
        result.pop("billing_rate", None)
        result.pop("cost_rate", None)
        result.pop("cost_value", None)
    return result


def _project_import_analysis(rows: list[Any], projects: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify validated project rows as creates or updates without trusting labels."""
    existing_codes = {
        str(project.get("code", "")).strip().casefold()
        for project in projects
        if str(project.get("code", "")).strip()
    }
    create_codes: list[str] = []
    update_codes: list[str] = []
    for row in rows:
        if getattr(row, "entity_type", None) != "projects":
            continue
        code = str(getattr(row, "values", {}).get("code", "")).strip()
        if not code:
            continue
        target = update_codes if code.casefold() in existing_codes else create_codes
        target.append(code)
    if create_codes and update_codes:
        suggested_action = "create_and_update_projects"
    elif create_codes:
        suggested_action = "create_projects"
    elif update_codes:
        suggested_action = "update_projects"
    else:
        suggested_action = "review_workbook"
    return {
        "project_row_count": len(create_codes) + len(update_codes),
        "create_count": len(create_codes),
        "update_count": len(update_codes),
        "create_codes": create_codes,
        "update_codes": update_codes,
        "suggested_action": suggested_action,
    }


class ChatHistoryMessage(BaseModel):
    """One user-visible message supplied as temporary conversation context."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=10_000)


class LoginRequest(BaseModel):
    """Credentials for the local first-party login flow."""

    username: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=256)


class PasswordChangeRequest(BaseModel):
    """Current and replacement password for an authenticated user."""

    current_password: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class QueryRequest(BaseModel):
    """Validated AI Assistant query."""

    query: str = Field(min_length=1, max_length=10_000)
    user_role: str = "project_manager"
    project_code: str | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)


class ThreeLayerFactsRequest(BaseModel):
    fact: Literal["projects", "risks", "claims", "daily_reports"]
    organization_id: str | None = None


class ThreeLayerSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    organization_id: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class GovernedSheetMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(min_length=1, max_length=100)
    sheet_name: str = Field(min_length=1, max_length=250)
    sheet_aliases: list[str] = Field(default_factory=list, max_length=50)
    columns: dict[str, str | list[str]]


class GovernedMappingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str | None = None
    mapping_profile_id: str
    mapping_version_id: str
    version_no: int = Field(ge=1)
    catalog_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=2000)
    sheets: list[GovernedSheetMappingRequest] = Field(min_length=1)


class GovernedDecisionRequest(BaseModel):
    organization_id: str | None = None
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=4000)


class GovernedOrganizationRequest(BaseModel):
    organization_id: str | None = None


from .project_models import ProjectDraft, ProjectUpdate


class DocumentDateConfirmation(BaseModel):
    """User-confirmed reporting date for a pending PDF ingestion job."""

    reporting_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class Runtime:
    """Application dependencies shared by API handlers and background workers."""

    def __init__(self, repository: ProjectRepository, three_layer: ThreeLayerRuntime | None = None):
        self.repository = repository
        settings = get_settings()
        selected_mode = three_layer.mode if three_layer is not None else settings.schema_mode
        if selected_mode != "redesigned":
            self.repository._ensure()
        redesign_schema_check = getattr(self.repository, "ensure_redesign_schema", None)
        if selected_mode != "legacy" and redesign_schema_check is not None:
            redesign_schema_check()
        self.rag_store: RAGStore | None = None
        self.ingestion: IngestionManager | None = None
        if selected_mode != "redesigned":
            try:
                if getattr(repository, "backend", "sqlite") == "postgres":
                    from .rag.pgvector_store import PgVectorStore
                    from .storage import SupabaseStorage
                    self.rag_store = PgVectorStore(repository)
                    storage = SupabaseStorage(
                        settings.supabase_url, settings.supabase_secret_key,
                        settings.supabase_storage_bucket,
                    )
                else:
                    self.rag_store = RAGStore(VECTOR_DIR)
                    storage = None
                self.ingestion = IngestionManager(
                    repository, self.rag_store, UPLOAD_DIR, storage=storage
                )
            except RuntimeError:
                # Queries and database features remain usable before an API key is configured.
                logging.getLogger("prosight").warning("rag_runtime_unavailable")
        if three_layer is not None:
            self.three_layer = three_layer
        elif settings.schema_mode == "legacy":
            self.three_layer = ThreeLayerRuntime(mode="legacy")
        else:
            if getattr(repository, "backend", "sqlite") != "postgres":
                raise RuntimeError("Compare/redesigned schema mode requires the PostgreSQL backend")

            def unavailable_embedder(_texts):
                raise RuntimeError("Embedding provider is unavailable")

            redesign_embedder = getattr(self.rag_store, "embedder", None)
            if redesign_embedder is None:
                from .rag.store import OpenAIEmbedder
                try:
                    redesign_embedder = OpenAIEmbedder(
                        settings.openai_api_key, settings.embedding_model
                    )
                except RuntimeError:
                    redesign_embedder = unavailable_embedder
            self.three_layer = ThreeLayerRuntime(
                mode=settings.schema_mode,
                authenticated_connection_factory=repository.connect_authenticated,
                embedder=redesign_embedder,
                projection_version=settings.semantic_projection_version,
                chunking_version=settings.semantic_chunking_version,
            )
        self.orchestrator = None if selected_mode == "redesigned" else MultiAgentOrchestrator(
            repository, RAGAgent(self.rag_store, repository) if self.rag_store else None
        )


def create_app(
    repository: ProjectRepository | None = None,
    three_layer: ThreeLayerRuntime | None = None,
) -> FastAPI:
    """Build an independently testable FastAPI application."""
    configure_logging()
    from .db import create_repository
    runtime = Runtime(repository or create_repository(), three_layer=three_layer)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        """Release worker and Chroma resources during graceful shutdown."""
        yield
        if runtime.ingestion:
            runtime.ingestion.close()
        close_repository = getattr(runtime.repository, "close", None)
        if close_repository:
            close_repository()

    app = FastAPI(title="ProSight AI", version="0.2.0", lifespan=lifespan)
    app.state.runtime = runtime
    from .agents.attachment_update import AttachmentUpdateAgent
    from .attachment_api import attachment_router
    runtime.attachments = AttachmentUpdateAgent(runtime.repository, runtime.ingestion, UPLOAD_DIR)
    app.include_router(attachment_router(runtime.attachments, _clear_resource_cache))
    from .agents.project_creation import ProjectCreationAgent
    from .project_draft_api import project_draft_router
    runtime.project_creation = ProjectCreationAgent(runtime.attachments)
    app.include_router(project_draft_router(runtime.project_creation, _clear_resource_cache))

    @app.middleware("http")
    async def attach_identity(request: Request, call_next):
        """Resolve the session once and prevent client-supplied roles in secure mode."""
        settings = get_settings()
        if settings.auth_provider == "supabase":
            try:
                user = await get_supabase_user(request.headers.get("authorization", ""), settings)
            except HTTPException as error:
                return JSONResponse(status_code=error.status_code, content={"detail": error.detail},
                                    headers={"Cache-Control": "private, no-store"})
        elif runtime.three_layer.mode == "redesigned":
            # Redesigned requests require a server-verified Supabase identity.
            # Never consult the legacy prosight user/session tables in this mode.
            user = None
        else:
            user = runtime.repository.get_session_user(request.cookies.get(settings.auth_cookie_name))
        request.state.user = user
        public_paths = {
            "/api/health", "/health", "/api/auth/config", "/api/auth/login", "/api/auth/me", "/api/auth/logout",
        }
        if (settings.auth_required or settings.auth_provider == "supabase") and request.url.path.startswith("/api/") and request.url.path not in public_paths and not user:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"}, headers={"Cache-Control": "private, no-store"})
        if user:
            # Legacy query parameters remain accepted for local tests, but an authenticated
            # request can never elevate its role through the browser.
            from urllib.parse import parse_qsl, urlencode
            query = parse_qsl(request.scope.get("query_string", b"").decode(), keep_blank_values=True)
            query = [(key, value) for key, value in query if key not in {"role", "user_role"}]
            query.extend([("role", user["role"]), ("user_role", user["role"])])
            request.scope["query_string"] = urlencode(query).encode()
        if (
            runtime.three_layer.mode == "redesigned"
            and request.url.path.startswith("/api/")
            and request.url.path not in public_paths
            and not request.url.path.startswith("/api/three-layer/")
        ):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": (
                        "Legacy API paths are disabled in redesigned mode; "
                        "use the scoped three-layer API"
                    )
                },
                headers={"Cache-Control": "private, no-store"},
            )
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/api/auth/config")
    def auth_config() -> dict:
        settings = get_settings()
        return {"provider": settings.auth_provider,
                "url": settings.supabase_url if settings.auth_provider == "supabase" else "",
                "publishableKey": settings.supabase_publishable_key if settings.auth_provider == "supabase" else ""}

    @app.post("/api/auth/login")
    def login(payload: LoginRequest, response: Response) -> dict:
        """Authenticate a user and issue an opaque, revocable session cookie."""
        if runtime.three_layer.mode == "redesigned" or get_settings().auth_provider == "supabase":
            raise HTTPException(400, "Sign in with Supabase using your email and password")
        user = runtime.repository.authenticate_user(payload.username, payload.password)
        if not user:
            runtime.repository.record_auth_event(None, "login_failed", payload.username[:120])
            raise HTTPException(status_code=401, detail="Invalid username or password")
        settings = get_settings()
        token = runtime.repository.create_session(user["id"], settings.auth_session_ttl_seconds)
        response.set_cookie(
            settings.auth_cookie_name,
            token,
            max_age=settings.auth_session_ttl_seconds,
            httponly=True,
            secure=settings.auth_cookie_secure,
            # Strict prevents a cross-site browser navigation from carrying
            # the session into a state-changing request. API clients can use
            # the same cookie with an explicit same-origin request.
            samesite="strict",
            path="/",
        )
        runtime.repository.record_auth_event(user, "login_success")
        return user

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict:
        """Revoke the current session and remove its browser cookie."""
        settings = get_settings()
        if runtime.three_layer.mode != "redesigned" and settings.auth_provider != "supabase":
            runtime.repository.revoke_session(request.cookies.get(settings.auth_cookie_name))
            runtime.repository.record_auth_event(getattr(request.state, "user", None), "logout")
        response.delete_cookie(settings.auth_cookie_name, path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def current_user(request: Request) -> dict:
        """Return the current database-backed identity and role."""
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user

    @app.post("/api/auth/change-password")
    def change_password(payload: PasswordChangeRequest, request: Request) -> dict:
        """Change a password after re-authentication."""
        if get_settings().auth_provider == "supabase":
            raise HTTPException(400, "Manage your password through Supabase Auth")
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        verified = runtime.repository.authenticate_user(user["username"], payload.current_password)
        if not verified:
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        runtime.repository.update_user_password(user["id"], payload.new_password)
        runtime.repository.record_auth_event(user, "password_changed")
        return {"ok": True}

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "llm_provider": "openai",
            "model": get_settings().openai_model,
            "rag_available": runtime.rag_store is not None,
            "schema_mode": runtime.three_layer.mode,
            "legacy_rollback_available": runtime.three_layer.legacy_rollback_available,
        }

    def redesigned_scope(request: Request, organization_id: str | None):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Authenticated identity is required")
        try:
            # The identity comes only from the server-verified session attached
            # by middleware.  Client payloads cannot supply or replace it.
            verified_user_id = uuid.UUID(str(user["id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=401, detail="Verified user identity is invalid") from error
        try:
            return runtime.three_layer.resolve_scope(verified_user_id, organization_id)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/three-layer/facts")
    def three_layer_facts(payload: ThreeLayerFactsRequest, request: Request) -> dict:
        scope = redesigned_scope(request, payload.organization_id)
        return runtime.three_layer.structured_facts(payload.fact, scope)

    @app.post("/api/three-layer/search")
    def three_layer_search(payload: ThreeLayerSearchRequest, request: Request) -> dict:
        scope = redesigned_scope(request, payload.organization_id)
        return runtime.three_layer.search(payload.query.strip(), scope, payload.limit)

    def public_mapping(record: MappingRecord) -> dict:
        mapping = record.mapping
        return {
            "mapping_profile_id": mapping.mapping_profile_id,
            "mapping_version_id": mapping.mapping_version_id,
            "version_no": mapping.version_no,
            "catalog_version": mapping.catalog_version,
            "mapping_checksum": mapping.mapping_checksum,
            "name": record.name,
            "description": record.description,
            "sheets": [
                {
                    "entity_type": sheet.entity_type,
                    "sheet_name": sheet.sheet_name,
                    "sheet_aliases": list(sheet.sheet_aliases),
                    "columns": {
                        target: list(sheet.source_labels(target))
                        for target in sheet.columns
                    },
                }
                for sheet in mapping.sheets
            ],
        }

    @app.get("/api/three-layer/catalog")
    def governed_catalog(request: Request, organization_id: str | None = None) -> dict:
        scope = redesigned_scope(request, organization_id)
        catalog = load_catalog()
        return {
            "organization_id": scope.organization_id,
            "organization_role": scope.organization_role,
            "catalog": catalog.model_dump(by_alias=True),
            "organization_profile_schema": organization_profile_json_schema(),
        }

    @app.get("/api/three-layer/mappings")
    def governed_mappings(
        request: Request,
        organization_id: str | None = None,
        entity_type: str | None = None,
    ) -> dict:
        scope = redesigned_scope(request, organization_id)
        records = runtime.three_layer.mapping_profiles(scope, entity_type=entity_type)
        return {"organization_id": scope.organization_id,
                "items": [public_mapping(record) for record in records]}

    @app.post("/api/three-layer/mappings", status_code=201)
    def register_governed_mapping(
        payload: GovernedMappingRequest, request: Request
    ) -> dict:
        scope = redesigned_scope(request, payload.organization_id)
        try:
            catalog = load_catalog()
            if payload.catalog_version != catalog.catalog_version:
                raise ValueError(
                    f"Mapping catalog version must be {catalog.catalog_version}"
                )
            sheets = tuple(
                compile_sheet_profile(
                    OrganizationSheetProfile.model_validate(sheet.model_dump()),
                    catalog=catalog,
                )
                for sheet in payload.sheets
            )
            mapping = OrganizationMapping(
                organization_id=scope.organization_id,
                mapping_profile_id=payload.mapping_profile_id,
                mapping_version_id=payload.mapping_version_id,
                version_no=payload.version_no,
                sheets=sheets,
                catalog_version=catalog.catalog_version,
            )
            runtime.three_layer.register_mapping(
                MappingRecord(mapping, payload.name.strip(), "excel", payload.description),
                scope,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "mapping_profile_id": mapping.mapping_profile_id,
            "mapping_version_id": mapping.mapping_version_id,
            "version_no": mapping.version_no,
            "mapping_checksum": mapping.mapping_checksum,
        }

    @app.get("/api/three-layer/projects")
    def three_layer_projects(request: Request, organization_id: str | None = None) -> list[dict]:
        return runtime.three_layer.projects(redesigned_scope(request, organization_id))

    @app.get("/api/three-layer/imports")
    def governed_imports(request: Request, organization_id: str | None = None) -> dict:
        scope = redesigned_scope(request, organization_id)
        return {"organization_id": scope.organization_id,
                "organization_role": scope.organization_role,
                "items": runtime.three_layer.imports(scope)}

    @app.get("/api/three-layer/imports/{batch_id}")
    def governed_import(
        batch_id: str, request: Request, organization_id: str | None = None
    ) -> dict:
        scope = redesigned_scope(request, organization_id)
        items = runtime.three_layer.imports(scope, batch_id=batch_id)
        if not items:
            raise HTTPException(status_code=404, detail="Import batch not found")
        return items[0]

    @app.post("/api/three-layer/imports/prepare", status_code=201)
    def prepare_governed_import(
        request: Request,
        mapping_profile_id: str | None = Form(None),
        mapping_version_no: int | None = Form(None),
        organization_id: str | None = Form(None),
        project_id: str | None = Form(None),
        instruction: str | None = Form(None),
        file: UploadFile = File(...),
    ) -> dict:
        scope = redesigned_scope(request, organization_id)
        filename = Path(file.filename or "").name
        instruction_text = (instruction or "").strip()
        temp_path: Path | None = None
        try:
            if len(instruction_text) > 4_000:
                raise HTTPException(
                    status_code=400,
                    detail="Workbook instructions cannot exceed 4,000 characters",
                )
            if Path(filename).suffix.lower() != ".xlsx":
                raise HTTPException(status_code=400, detail="A governed .xlsx workbook is required")
            if mapping_profile_id is None:
                selected_mapping = runtime.three_layer.ensure_default_project_mapping(scope)
                mapping_profile_id = selected_mapping.mapping.mapping_profile_id
                mapping_version_no = selected_mapping.mapping.version_no
            elif mapping_version_no is None:
                raise HTTPException(
                    status_code=400,
                    detail="mapping_version_no is required with a profile",
                )
            oversized = False
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temporary:
                temp_path = Path(temporary.name)
                total = 0
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > 10 * 1024 * 1024:
                        oversized = True
                        break
                    temporary.write(chunk)
            if oversized:
                raise HTTPException(status_code=413, detail="Workbook exceeds the 10 MiB limit")
            prepared = runtime.three_layer.prepare_import(
                temp_path,
                scope,
                mapping_profile_id=mapping_profile_id,
                mapping_version_no=mapping_version_no,
                original_filename=filename,
                mime_type=file.content_type,
                project_id=project_id,
            )
            analysis = _project_import_analysis(
                prepared.preview.rows,
                runtime.three_layer.projects(scope),
            )
        except HTTPException:
            raise
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (LookupError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            logging.getLogger("prosight").exception("governed_import_prepare_failed")
            raise HTTPException(
                status_code=500,
                detail="The server could not process this workbook. Please retry or contact support.",
            ) from error
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        preview = prepared.preview
        return {
            "import_batch_id": preview.import_batch_id,
            "source_file_id": preview.source_file_id,
            "transformation_run_id": prepared.transformation_run_id,
            "mapping_profile_id": preview.mapping_profile_id,
            "mapping_version_id": preview.mapping_version_id,
            "mapping_version_no": preview.mapping_version_no,
            "source_checksum": preview.source_checksum,
            "profile_checksum": preview.profile_checksum,
            "input_profile_checksum": preview.input_profile_checksum,
            "normalized_preview_checksum": preview.normalized_preview_checksum,
            "validation_checksum": preview.validation_checksum,
            "valid": preview.valid,
            "instruction": instruction_text or None,
            "analysis": analysis,
            "row_count": len(preview.rows),
            "rows": [
                {"entity_type": row.entity_type, "values": row.values, "lineage": row.lineage}
                for row in preview.rows[:200]
            ],
            "issues": [issue.__dict__ for issue in preview.issues],
        }

    @app.post("/api/three-layer/imports/{batch_id}/submit")
    def submit_governed_import(
        batch_id: str, payload: GovernedOrganizationRequest, request: Request
    ) -> dict:
        scope = redesigned_scope(request, payload.organization_id)
        try:
            runtime.three_layer.submit_import(batch_id, scope)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"import_batch_id": str(uuid.UUID(batch_id)), "status": "awaiting_approval"}

    @app.post("/api/three-layer/imports/{batch_id}/decision")
    def decide_governed_import(
        batch_id: str, payload: GovernedDecisionRequest, request: Request
    ) -> dict:
        scope = redesigned_scope(request, payload.organization_id)
        try:
            binding = runtime.three_layer.decide_import(
                batch_id,
                scope,
                decision=payload.decision,
                reason=payload.reason,
            )
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "approval_id": binding.id,
            "import_batch_id": binding.batch_id,
            "decision": binding.decision,
            "validation_checksum": binding.validation_checksum,
            "normalized_preview_checksum": binding.normalized_preview_checksum,
        }

    @app.post("/api/three-layer/imports/{batch_id}/publish")
    def publish_governed_import(
        batch_id: str, payload: GovernedOrganizationRequest, request: Request
    ) -> dict:
        scope = redesigned_scope(request, payload.organization_id)
        try:
            return runtime.three_layer.publish_import(batch_id, scope)
        except PermissionError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
            **draft.storage_record(),
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
        request: Request,
        role: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict:
        """Validate one canonical workbook and create an editable import preview."""
        role = _effective_role(request, role)
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
                    **update.storage_record(),
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
                    **draft.storage_record(),
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
    def query(payload: QueryRequest, request: Request) -> dict:
        trace = RequestTrace()
        try:
            actor_role = _effective_role(request, payload.user_role)
            _validate_role(actor_role)
            trace.event(
                "query_received",
                role=actor_role,
                user_id=getattr(request.state, "user", None) and request.state.user["id"],
                project_code=payload.project_code,
                query_preview=sanitize(payload.query),
            )
            trace.event(
                "query_validated",
                role=actor_role,
                project_code=payload.project_code,
                query_length=len(payload.query),
                history_count=len(payload.history),
            )
            result = runtime.orchestrator.run(
                payload.query.strip(),
                actor_role,
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
    async def query_stream(payload: QueryRequest, request: Request) -> StreamingResponse:
        """Stream real orchestration states and a final backward-compatible answer."""
        actor_role = _effective_role(request, payload.user_role)
        _validate_role(actor_role)

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

            trace.event("query_received", role=actor_role,
                        user_id=getattr(request.state, "user", None) and request.state.user["id"],
                        project_code=payload.project_code,
                        query_preview=sanitize(payload.query))
            trace.event("query_validated", role=actor_role,
                        project_code=payload.project_code,
                        query_length=len(payload.query), history_count=len(payload.history))
            yield encode("meta", {"request_id": trace.request_id})
            yield encode("status", {"state": "thinking", "label": "Thinking"})
            try:
                task = asyncio.create_task(asyncio.to_thread(
                    runtime.orchestrator.run,
                    payload.query.strip(), actor_role, payload.project_code, trace,
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
        request: Request,
        project_code: str = Form(...),
        user_role: str = Form("project_manager"),
        file: UploadFile = File(...),
    ) -> dict:
        user_role = _effective_role(request, user_role)
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

    @app.post("/api/ingestion-jobs/{job_id}/retry-index")
    def retry_document_index(job_id: str, request: Request, role: str = Query(...)) -> dict:
        """Retry embeddings for a document approved by Admin but not indexed."""
        role = _effective_role(request, role)
        _validate_role(role)
        if not runtime.ingestion:
            raise HTTPException(status_code=503, detail="RAG runtime unavailable")
        try:
            return runtime.ingestion.retry_indexing(job_id, role)
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

    @app.delete("/api/ingestion-jobs/{job_id}")
    def clear_failed_ingestion_job(job_id: str, role: str = Query(...)) -> dict:
        """Permanently clear one failed upload after project and role authorization."""
        _validate_role(role)
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
        request: Request,
        role: str = Form(...), dataset: str = Form("combined"),
        project_code: str | None = Form(None), file: UploadFile = File(...)
    ) -> dict:
        role = _effective_role(request, role)
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
                change = runtime.repository.create_change_request(
                    "portfolio_import",
                    project_code or "PORTFOLIO",
                    {"import_id": record["id"], "parsed": parsed},
                    {
                        "before": None,
                        "after": parsed,
                        "warnings": [],
                        "source_filename": filename,
                        "dataset": dataset,
                    },
                    role,
                )
                runtime.repository.set_portfolio_import_status(
                    record["id"], "awaiting_approval", "Portfolio preview is waiting for Admin approval"
                )
                return {"status": "awaiting_approval", "import": runtime.repository.get_portfolio_import(record["id"]), "change": change}
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
        request: Request, role: str = Query(...), project_code: str | None = Query(None),
        search: str | None = Query(None), department: str | None = Query(None),
        category: str | None = Query(None), status: str | None = Query(None),
        location: str | None = Query(None),
    ) -> list[dict]:
        role = _effective_role(request, role)
        _validate_role(role)
        if project_code and not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        records = runtime.repository.list_manpower(
            project_code, search, department, category, status, location
        )
        return [_mask_resource_record(item, role) for item in records]

    def _resource_request_values(
        request: Request, role: str, project_code: str | None,
        date_from: str | None, date_to: str | None, department: str | None,
        designation: str | None, employee: str | None,
        allocation_status: str | None, billable_status: str | None,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve role and common filters once for all resource endpoints."""
        role = _effective_role(request, role)
        _validate_role(role)
        if project_code and not runtime.repository.find_project(project_code, role):
            raise HTTPException(status_code=404, detail="Project not found or unauthorized")
        if allocation_status and allocation_status not in {"overallocated", "underallocated", "balanced"}:
            raise HTTPException(status_code=400, detail="Unsupported allocation status")
        if billable_status and billable_status not in {"billable", "non_billable"}:
            raise HTTPException(status_code=400, detail="Unsupported billable status")
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=400, detail="date_from must not be after date_to")
        return role, {
            "project_code": project_code, "date_from": date_from, "date_to": date_to,
            "department": department, "designation": designation, "employee": employee,
            "allocation_status": allocation_status, "billable_status": billable_status,
        }

    @app.get("/api/resource-allocation/summary")
    def resource_allocation_summary(
        request: Request, role: str = Query(...), project_code: str | None = Query(None),
        date_from: str | None = Query(None), date_to: str | None = Query(None),
        department: str | None = Query(None), designation: str | None = Query(None),
        employee: str | None = Query(None), allocation_status: str | None = Query(None),
        billable_status: str | None = Query(None),
    ) -> dict:
        role, values = _resource_request_values(
            request, role, project_code, date_from, date_to, department,
            designation, employee, allocation_status, billable_status,
        )
        key = _resource_cache_key("summary", role, values)
        result = _resource_cached(key, lambda: runtime.repository.resource_allocation_summary(**values))
        if role == "admin":
            return result
        return {**result, "totals": {key: value for key, value in result["totals"].items() if key != "cost_value"}}

    @app.get("/api/resource-allocation/trends")
    def resource_allocation_trends(
        request: Request, role: str = Query(...), project_code: str | None = Query(None),
        date_from: str | None = Query(None), date_to: str | None = Query(None),
        department: str | None = Query(None), designation: str | None = Query(None),
        employee: str | None = Query(None), allocation_status: str | None = Query(None),
        billable_status: str | None = Query(None),
    ) -> list[dict]:
        role, values = _resource_request_values(
            request, role, project_code, date_from, date_to, department,
            designation, employee, allocation_status, billable_status,
        )
        key = _resource_cache_key("trends", role, values)
        return _resource_cached(key, lambda: runtime.repository.resource_allocation_trends(**values))

    @app.get("/api/resource-allocation/conflicts")
    def resource_allocation_conflicts(
        request: Request, role: str = Query(...), project_code: str | None = Query(None),
        date_from: str | None = Query(None), date_to: str | None = Query(None),
        department: str | None = Query(None), designation: str | None = Query(None),
        employee: str | None = Query(None), allocation_status: str | None = Query(None),
        billable_status: str | None = Query(None),
    ) -> list[dict]:
        role, values = _resource_request_values(
            request, role, project_code, date_from, date_to, department,
            designation, employee, allocation_status, billable_status,
        )
        key = _resource_cache_key("conflicts", role, values)
        records = _resource_cached(key, lambda: runtime.repository.resource_allocation_conflicts(**values))
        return [_mask_resource_record(item, role) for item in records]

    @app.get("/api/resource-allocation/details")
    def resource_allocation_details(
        request: Request, role: str = Query(...), project_code: str | None = Query(None),
        date_from: str | None = Query(None), date_to: str | None = Query(None),
        department: str | None = Query(None), designation: str | None = Query(None),
        employee: str | None = Query(None), allocation_status: str | None = Query(None),
        billable_status: str | None = Query(None), limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> dict:
        role, values = _resource_request_values(
            request, role, project_code, date_from, date_to, department,
            designation, employee, allocation_status, billable_status,
        )
        values_with_page = {**values, "limit": limit, "offset": offset}
        key = _resource_cache_key("details", role, values_with_page)
        result = _resource_cached(
            key, lambda: runtime.repository.resource_allocation_details(**values_with_page)
        )
        return {**result, "items": [_mask_resource_record(item, role) for item in result["items"]]}

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

    @app.delete("/api/projects/{project_code}")
    def delete_project(project_code: str, request: Request, confirmation: str = Query(...)) -> dict:
        # Destructive operations always require a real identity, including demo mode.
        user = request.state.user
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        _require_role(user["role"], {"admin"}, "Only Admin can delete projects")
        if confirmation != project_code:
            raise HTTPException(status_code=400, detail="Type the exact project code to confirm deletion")
        from .project_deletion import ProjectDeletion
        try:
            result = ProjectDeletion(runtime.repository, runtime.rag_store, UPLOAD_DIR, PORTFOLIO_DIR).delete(project_code, user["role"])
            _clear_resource_cache()
            return result
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Project not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except Exception as error:
            logging.getLogger("prosight").error("project_deletion_failed", extra={"error_type": type(error).__name__})
            raise HTTPException(status_code=503, detail="Deletion could not finish. Retry after checking storage and database availability.") from error

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
        if change and change.get("action") in {"attachment_update", "natural_project_create"}:
            raise HTTPException(403, "Use the authenticated AI Assistant workspace to view this preview")
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
        request: Request, role: str = Query(...), status: Literal["pending"] = Query("pending")
    ) -> dict:
        _validate_role(role)
        _require_role(role, {"admin"}, "Only Admin can access the approval queue")
        items = runtime.repository.list_pending_approvals()
        if not request.state.user or request.state.user.get("role") != "admin":
            items = [item for item in items if item.get("action") not in {"attachment_update", "natural_project_create"}]
        return {"items": items}

    @app.post("/api/change-requests/{change_id}/{decision}")
    def decide_change(
        change_id: str,
        decision: Literal["approve", "reject"],
        request: Request,
        role: str = Query(...),
    ) -> dict:
        _validate_role(role)
        _require_role(role, {"admin"}, "Only Admin can approve or reject changes")
        try:
            candidate = runtime.repository.get_change_request(change_id)
            if candidate and candidate.get("action") in {"attachment_update", "natural_project_create"}:
                raise HTTPException(409, "Review and approve this attachment in AI Assistant using its saved preview")
            result = runtime.repository.decide_change_request(
                change_id, "approved" if decision == "approve" else "rejected", role
            )
            if result.get("action") == "portfolio_import":
                import_id = result.get("payload", {}).get("import_id")
                if decision == "approve":
                    imported = runtime.repository.apply_portfolio_import(
                        import_id, result["payload"].get("parsed", {})
                    )
                    _clear_resource_cache()
                    result["import"] = imported
                elif import_id:
                    result["import"] = runtime.repository.set_portfolio_import_status(
                        import_id, "rejected", "Portfolio import was rejected by Admin"
                    )
            if result.get("action") == "document_approval" and decision == "approve":
                if not runtime.ingestion:
                    raise HTTPException(status_code=503, detail="RAG runtime unavailable")
                runtime.ingestion.index_approved_document(result)
                result["indexing"] = "queued"
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


def _effective_role(request: Request, submitted_role: str | None) -> str:
    """Use the session's database role; accept submitted roles only in local compatibility mode."""
    user = getattr(request.state, "user", None)
    if user:
        return user["role"]
    if get_settings().auth_required or get_settings().auth_provider == "supabase":
        raise HTTPException(status_code=401, detail="Authentication required")
    return submitted_role or "project_manager"


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

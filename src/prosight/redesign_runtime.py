"""Transition-safe application bridge for the construction/ingestion/semantic layers."""

from __future__ import annotations

import uuid
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Callable, Literal

from .construction_facts import ConstructionFacts
from .ingestion.governed_excel import OrganizationMapping
from .ingestion.persistence import (
    GovernedIngestionAdapter,
    GovernedIngestionService,
    MappingRecord,
    PreparedImport,
)
from .ingestion.publication import AtomicPublicationAdapter, PublicationRequest
from .rag.semantic import SemanticIndexAdapter, SemanticSearch


SchemaMode = Literal["legacy", "compare", "redesigned"]

ORGANIZATION_SCOPE_SQL = """
select membership.organization_id,membership.role
from construction.organization_members membership
where membership.user_id=%(user_id)s::uuid
  and membership.is_active
  and (%(organization_id)s::uuid is null
       or membership.organization_id=%(organization_id)s::uuid)
order by membership.organization_id
"""

PROJECT_SCOPE_SQL = """
select project.id
from construction.projects project
join construction.organization_members membership
  on membership.organization_id=project.organization_id
 and membership.user_id=%(user_id)s::uuid
 and membership.is_active
where project.organization_id=%(organization_id)s::uuid
  and (
    project.access_mode='organization'
    or membership.role in ('owner','admin','manager')
    or exists (
      select 1
      from construction.project_members project_membership
      where project_membership.organization_id=project.organization_id
        and project_membership.project_id=project.id
        and project_membership.user_id=%(user_id)s::uuid
        and project_membership.is_active
    )
  )
order by project.id
"""


@dataclass(frozen=True)
class AuthenticatedScope:
    user_id: str
    organization_id: str
    allowed_project_ids: tuple[str, ...]
    organization_role: str = "member"

    @property
    def verified_user_id(self) -> uuid.UUID:
        return uuid.UUID(self.user_id)


class AuthorizationScopeResolver:
    """Derive tenant/project scope from authenticated membership rows."""

    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    def resolve(
        self, server_verified_user_id: uuid.UUID, organization_id: str | None = None
    ) -> AuthenticatedScope:
        if not isinstance(server_verified_user_id, uuid.UUID):
            raise ValueError("A server-verified UUID user identity is required")
        user_id = str(server_verified_user_id)
        requested_org = str(uuid.UUID(organization_id)) if organization_id else None
        with closing(self.connection_factory(server_verified_user_id)) as connection:
            with connection:
                organizations = connection.execute_native(
                    ORGANIZATION_SCOPE_SQL,
                    {"user_id": user_id, "organization_id": requested_org},
                ).fetchall()
                organization_ids = tuple(str(row["organization_id"]) for row in organizations)
                if not organization_ids:
                    raise PermissionError("No active organization membership grants access")
                if len(organization_ids) != 1:
                    raise ValueError(
                        "organization_id is required when the user belongs to multiple organizations"
                    )
                selected_org = str(uuid.UUID(organization_ids[0]))
                projects = connection.execute_native(
                    PROJECT_SCOPE_SQL,
                    {"user_id": user_id, "organization_id": selected_org},
                ).fetchall()
        return AuthenticatedScope(
            user_id=user_id,
            organization_id=selected_org,
            allowed_project_ids=tuple(str(uuid.UUID(str(row["id"]))) for row in projects),
            organization_role=str(organizations[0].get("role", "member")),
        )


class ThreeLayerRuntime:
    """Select the legacy, comparison, or redesigned application path explicitly."""

    def __init__(
        self,
        *,
        mode: SchemaMode,
        authenticated_connection_factory=None,
        embedder=None,
        projection_version: int = 1,
        chunking_version: str = "pdf-heading-pages-v1",
        legacy_fact_query: Callable[..., Any] | None = None,
        legacy_semantic_search: Callable[..., Any] | None = None,
    ):
        if mode not in {"legacy", "compare", "redesigned"}:
            raise ValueError("Schema mode must be legacy, compare, or redesigned")
        self.mode = mode
        self.legacy_fact_query = legacy_fact_query
        self.legacy_semantic_search = legacy_semantic_search
        self.scope_resolver = None
        self.authenticated_connection_factory = authenticated_connection_factory
        if mode != "legacy":
            if authenticated_connection_factory is None or embedder is None:
                raise ValueError("Compare/redesigned mode requires database and embedding adapters")
            self.scope_resolver = AuthorizationScopeResolver(authenticated_connection_factory)
        self.embedder = embedder
        self.projection_version = projection_version
        self.chunking_version = chunking_version

    @property
    def legacy_rollback_available(self) -> bool:
        return self.mode in {"legacy", "compare"}

    def require_redesigned(self) -> None:
        if self.mode == "legacy":
            raise RuntimeError("Three-layer runtime is not active; legacy mode remains selected")

    def resolve_scope(
        self, server_verified_user_id: uuid.UUID, organization_id: str | None = None
    ) -> AuthenticatedScope:
        self.require_redesigned()
        assert self.scope_resolver is not None
        return self.scope_resolver.resolve(server_verified_user_id, organization_id)

    def _request_connection_factory(self, scope: AuthenticatedScope):
        assert self.authenticated_connection_factory is not None
        return lambda: self.authenticated_connection_factory(scope.verified_user_id)

    @staticmethod
    def _require_scope_organization(scope: AuthenticatedScope, organization_id: str) -> None:
        if str(uuid.UUID(organization_id)) != scope.organization_id:
            raise PermissionError("Requested organization is outside the authenticated scope")

    def ingestion_adapter(self, scope: AuthenticatedScope) -> GovernedIngestionAdapter:
        self.require_redesigned()
        return GovernedIngestionAdapter(self._request_connection_factory(scope))

    def register_mapping(self, record: MappingRecord, scope: AuthenticatedScope) -> None:
        self._require_scope_organization(scope, record.mapping.organization_id)
        if scope.organization_role not in {"owner", "admin", "manager"}:
            raise PermissionError(
                "Only an active organization owner, admin, or manager may configure mappings"
            )
        self.ingestion_adapter(scope).register_mapping(
            record, created_by=scope.user_id
        )

    def mapping_profiles(
        self, scope: AuthenticatedScope, *, entity_type: str | None = None
    ) -> list[MappingRecord]:
        records = self.ingestion_adapter(scope).list_mappings(
            scope.organization_id, entity_type=entity_type
        )
        from .ingestion.catalog import validate_compiled_mapping
        usable = []
        for record in records:
            try:
                validate_compiled_mapping(record.mapping)
            except ValueError:
                continue
            usable.append(record)
        return usable

    def ensure_default_project_mapping(self, scope: AuthenticatedScope) -> MappingRecord:
        existing = self.mapping_profiles(scope, entity_type="projects")
        if existing:
            return existing[0]
        if scope.organization_role not in {"owner", "admin", "manager"}:
            raise PermissionError(
                "An organization owner, admin, or manager must configure the first project mapping"
            )
        from .ingestion.catalog import compile_sheet_profile, default_project_sheet, load_catalog

        catalog = load_catalog()
        profile_id = str(uuid.uuid5(uuid.UUID(scope.organization_id), "prosight:projects:profile"))
        version_id = str(uuid.uuid5(uuid.UUID(profile_id), f"catalog:{catalog.catalog_version}"))
        mapping = OrganizationMapping(
            organization_id=scope.organization_id,
            mapping_profile_id=profile_id,
            mapping_version_id=version_id,
            version_no=1,
            sheets=(compile_sheet_profile(default_project_sheet(), catalog=catalog),),
            catalog_version=catalog.catalog_version,
        )
        record = MappingRecord(
            mapping, "ProSight project register", "excel",
            "Organization-scoped default aliases derived from the platform construction catalog.",
        )
        try:
            self.register_mapping(record, scope)
        except ValueError:
            # A concurrent first request may have created the deterministic version.
            return self.ingestion_adapter(scope).load_mapping(
                scope.organization_id, profile_id, 1
            )
        return record

    def imports(self, scope: AuthenticatedScope, *, batch_id: str | None = None) -> list[dict[str, Any]]:
        rows = self.ingestion_adapter(scope).list_imports(
            scope.organization_id, batch_id=batch_id
        )
        if scope.organization_role not in {"owner", "admin"}:
            rows = [row for row in rows if str(row["requester_user_id"]) == scope.user_id]
        return rows

    def projects(self, scope: AuthenticatedScope) -> list[dict[str, Any]]:
        records = ConstructionFacts(self._request_connection_factory(scope)).query(
            "projects", scope.organization_id, list(scope.allowed_project_ids)
        )
        result = []
        for record in records:
            status = "future" if record.get("status") == "planning" else record.get("status")
            progress = record.get("progress_percent") or 0
            result.append({
                **record,
                "status": status,
                "client": record.get("client") or "Not assigned",
                "contract_value_usd": record.get("contract_value") or 0,
                "planned_start": record.get("planned_start_date"),
                "planned_finish": record.get("planned_finish_date"),
                "revised_finish": record.get("planned_finish_date"),
                "actual_progress": progress,
                "baseline_progress": None,
                "revised_progress": None,
                "progress_fields_provided": ["actual_progress"],
                "variance_pct": 0,
                "variance_available": False,
                "delay_days": 0,
                "contacts": [], "activities": [], "manpower": [], "equipment": [],
                "milestones": [], "sources": ["construction.projects"],
            })
        return result

    def prepare_import(self, path, scope: AuthenticatedScope, **options) -> PreparedImport:
        organization_id = options.pop("organization_id", scope.organization_id)
        self._require_scope_organization(scope, organization_id)
        return GovernedIngestionService(self.ingestion_adapter(scope)).prepare(
            path,
            organization_id=scope.organization_id,
            allowed_project_ids=scope.allowed_project_ids,
            actor_id=scope.user_id,
            **options,
        )

    def submit_import(self, batch_id: str, scope: AuthenticatedScope) -> None:
        self.ingestion_adapter(scope).submit_for_approval(
            scope.organization_id, str(uuid.UUID(batch_id))
        )

    def decide_import(
        self,
        batch_id: str,
        scope: AuthenticatedScope,
        *,
        decision: Literal["approved", "rejected"],
        reason: str | None = None,
    ):
        return self.ingestion_adapter(scope).decide(
            scope.organization_id,
            str(uuid.UUID(batch_id)),
            actor_id=scope.user_id,
            decision=decision,
            reason=reason,
        )

    def publish_import(self, batch_id: str, scope: AuthenticatedScope) -> dict[str, Any]:
        adapter = self.ingestion_adapter(scope)
        request = adapter.publication_request(
            scope.organization_id, str(uuid.UUID(batch_id))
        )
        # The private RPC repeats every approval/actor/idempotency check while
        # holding the publication lock; there is no application row-upsert path.
        return AtomicPublicationAdapter(
            self._request_connection_factory(scope)
        ).publish(request)

    def structured_facts(self, fact: str, scope: AuthenticatedScope) -> dict[str, Any]:
        self.require_redesigned()
        facts = ConstructionFacts(self._request_connection_factory(scope))
        redesigned = facts.query(
            fact, scope.organization_id, list(scope.allowed_project_ids)
        )
        legacy = None
        if self.mode == "compare" and self.legacy_fact_query is not None:
            legacy = self.legacy_fact_query(fact, scope)
        return {"mode": self.mode, "results": redesigned, "legacy_comparison": legacy}

    def search(self, query: str, scope: AuthenticatedScope, limit: int = 5) -> dict[str, Any]:
        self.require_redesigned()
        search = SemanticSearch(
            self._request_connection_factory(scope),
            self.embedder,
            projection_version=self.projection_version,
            chunking_version=self.chunking_version,
        )
        redesigned = search.search(
            query, scope.organization_id, list(scope.allowed_project_ids), limit
        )
        legacy = None
        if self.mode == "compare" and self.legacy_semantic_search is not None:
            legacy = self.legacy_semantic_search(query, scope, limit)
        return {"mode": self.mode, "results": redesigned, "legacy_comparison": legacy}

    def publish(self, request: PublicationRequest, scope: AuthenticatedScope) -> dict[str, Any]:
        self.require_redesigned()
        return AtomicPublicationAdapter(self._request_connection_factory(scope)).publish(request)

    def index(
        self,
        chunks: list[dict[str, Any]],
        *,
        embedding_job_id: str,
        scope: AuthenticatedScope,
    ) -> int:
        self.require_redesigned()
        return SemanticIndexAdapter(
            self._request_connection_factory(scope), self.embedder
        ).upsert(chunks, embedding_job_id=embedding_job_id)

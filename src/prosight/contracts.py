"""Typed contracts exchanged between ProSight agents and ingestion services."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentName = Literal["database_manager", "rag", "writer"]


class OrchestrationPlan(BaseModel):
    """A safe, inspectable plan created before specialists are invoked."""

    intent: Literal["greeting", "database_read", "rag_read", "combined", "database_write", "unsupported"]
    agents: list[AgentName] = Field(default_factory=list)
    project_code: str | None = None
    requires_write_approval: bool = False
    steps: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """One source-backed fact passed to the Writer Agent."""

    text: str
    citation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatabaseEvidence(BaseModel):
    """Structured output of the Database Manager Agent."""

    records: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    change_request_id: str | None = None
    summary: str = ""


class RAGEvidence(BaseModel):
    """Project-scoped chunks returned by the RAG Agent."""

    evidence: list[EvidenceItem] = Field(default_factory=list)
    query: str
    project_code: str


class WriterInput(BaseModel):
    """Complete, evidence-only context accepted by the Writer Agent."""

    query: str
    database: DatabaseEvidence | None = None
    rag: RAGEvidence | None = None
    database_table: str | None = None


class AgentAnswer(BaseModel):
    """Public response returned by the orchestration layer."""

    answer: str
    citations: list[str] = Field(default_factory=list)
    agent_route: list[str] = Field(default_factory=list)
    mode: str = "openai"
    notice: str | None = None
    time_to_first_token_ms: int | None = None


class ChangeOperation(BaseModel):
    """Allowlisted database operation stored for human review."""

    action: Literal[
        "project_upsert",
        "contact_update",
        "activity_import",
        "resource_import",
        "milestone_update",
        "record_delete",
        "excel_import",
        "document_delete",
    ]
    project_code: str
    payload: dict[str, Any]
    provenance: dict[str, Any] = Field(default_factory=dict)


class ChangePreview(BaseModel):
    """Pending database change plus validation information."""

    operation: ChangeOperation
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)

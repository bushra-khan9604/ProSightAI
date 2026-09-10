"""Duplicate-safe PDF reindex planning and offline comparison support."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from .semantic import RevisionContext, extract_revision_chunks


class StorageReader(Protocol):
    """Deliberately read-only: a reindexer has no upload/delete capability."""

    def download(self, bucket: str, object_path: str) -> bytes: ...


class SemanticChunkSink(Protocol):
    def upsert(
        self,
        chunks: list[dict[str, Any]],
        *,
        embedding_job_id: str | None = None,
    ) -> int: ...


@dataclass(frozen=True)
class ReindexDocument:
    context: RevisionContext
    checksum_sha256: str
    embedding_job_id: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.checksum_sha256):
            raise ValueError("A lowercase SHA-256 revision checksum is required")
        if self.embedding_job_id is not None:
            uuid.UUID(self.embedding_job_id)


@dataclass(frozen=True)
class ReindexPlan:
    documents: tuple[ReindexDocument, ...]
    skipped_duplicates: tuple[str, ...]
    dry_run: bool = True
    uploads: int = 0
    deletes: int = 0
    legacy_index_retained: bool = True


class ReindexPlanner:
    """Deduplicate physical and logical copies without collapsing real revisions.

    Within one organization, the same checksum is a duplicate only when it also
    names the same authoritative construction document revision.  Matching
    bytes attached to distinct revision IDs remain separate auditable revisions.
    """

    def plan(self, documents: list[ReindexDocument]) -> ReindexPlan:
        unique: list[ReindexDocument] = []
        skipped: list[str] = []
        storage_owners: dict[tuple[str, str], str] = {}
        chunk_namespaces: set[tuple[str, str, int, str]] = set()
        logical_revisions: set[tuple[str, str, str, str]] = set()
        for document in documents:
            storage_key = (
                document.context.storage_bucket,
                document.context.storage_object_path,
            )
            namespace = (
                document.context.organization_id,
                document.context.semantic_document_id,
                document.context.projection_version,
                document.context.chunking_version,
            )
            logical_revision = (
                document.context.organization_id,
                document.checksum_sha256,
                document.context.construction_document_id,
                document.context.document_revision_id,
            )
            storage_owner = storage_owners.get(storage_key)
            if storage_owner is not None and storage_owner != document.context.organization_id:
                raise ValueError("A Storage object cannot be shared across organizations")
            if (
                storage_owner is not None
                or namespace in chunk_namespaces
                or logical_revision in logical_revisions
            ):
                skipped.append(document.context.document_revision_id)
                continue
            storage_owners[storage_key] = document.context.organization_id
            chunk_namespaces.add(namespace)
            logical_revisions.add(logical_revision)
            unique.append(document)
        return ReindexPlan(tuple(unique), tuple(skipped))


class ReindexExecutor:
    """Read originals, derive chunks, and write only the new semantic index."""

    def __init__(self, storage: StorageReader, sink: SemanticChunkSink):
        self.storage = storage
        self.sink = sink

    def execute(self, plan: ReindexPlan, *, dry_run: bool = True) -> dict[str, Any]:
        if dry_run:
            return {
                "dry_run": True,
                "documents": len(plan.documents),
                "chunks": 0,
                "uploads": 0,
                "deletes": 0,
                "legacy_index_retained": True,
            }
        chunk_count = 0
        published_documents = 0
        chunk_ids: set[str] = set()
        for document in plan.documents:
            content = self.storage.download(
                document.context.storage_bucket, document.context.storage_object_path
            )
            if hashlib.sha256(content).hexdigest() != document.checksum_sha256:
                raise ValueError("Storage object checksum does not match its registered revision")
            document_chunks = extract_revision_chunks(content, document.context)
            for chunk in document_chunks:
                if chunk["id"] in chunk_ids:
                    raise ValueError("Duplicate semantic chunk identifier")
                chunk_ids.add(chunk["id"])
            if document.embedding_job_id is None:
                written = self.sink.upsert(document_chunks)
            else:
                written = self.sink.upsert(
                    document_chunks,
                    embedding_job_id=document.embedding_job_id,
                )
            if written != len(document_chunks):
                raise RuntimeError(
                    "Semantic sink did not acknowledge the complete document chunk set"
                )
            chunk_count += written
            published_documents += 1
        return {
            "dry_run": False,
            "documents": published_documents,
            "chunks": chunk_count,
            "uploads": 0,
            "deletes": 0,
            "legacy_index_retained": True,
        }


def compare_rankings(
    queries: list[str], legacy_search, semantic_search, *, limit: int = 10
) -> dict[str, Any]:
    """Compare result IDs without mutating or deleting either index."""
    comparisons = []
    for query in queries:
        legacy = list(legacy_search(query, limit))
        semantic = list(semantic_search(query, limit))
        shared = set(legacy) & set(semantic)
        comparisons.append({
            "query": query,
            "legacy_ids": legacy,
            "semantic_ids": semantic,
            "overlap_count": len(shared),
            "overlap_at_limit": len(shared) / max(1, min(limit, len(set(legacy) | set(semantic)))),
        })
    return {"queries": comparisons, "legacy_index_retained": True, "cutover_accepted": False}


@dataclass(frozen=True)
class CutoverAcceptance:
    acceptance_id: str
    accepted_by: str
    comparison_checksum: str

    def __post_init__(self) -> None:
        if not self.acceptance_id.strip() or not self.accepted_by.strip():
            raise ValueError("Explicit acceptance identity and actor are required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.comparison_checksum):
            raise ValueError("A comparison SHA-256 checksum is required")


def require_cutover_acceptance(acceptance: CutoverAcceptance | None) -> CutoverAcceptance:
    if acceptance is None:
        raise PermissionError("Explicit retrieval-comparison acceptance is required before cutover")
    return acceptance

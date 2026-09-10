"""Versioned semantic projections, chunks, embeddings, and tenant-safe search."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from contextlib import closing
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from pypdf import PdfReader


EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
DESCRIPTIVE_ENTITY_FIELDS = {
    "project_summary": ("name", "description", "objectives", "scope_summary"),
    "risk": ("risk_number", "title", "description", "cause", "consequence", "mitigation_plan", "contingency_plan"),
    "claim": ("claim_number", "title", "description", "contractual_clause", "entitlement_basis", "resolution"),
    "contract_notice": ("notice_number", "subject", "description", "response"),
    "rfi": ("rfi_number", "subject", "question", "response"),
    "nonconformance_report": ("ncr_number", "title", "description", "root_cause", "corrective_action", "preventive_action"),
    "daily_report": ("report_date", "work_completed", "planned_work", "delays_and_constraints", "safety_observations", "quality_observations"),
    "meeting": ("meeting_number", "title", "agenda", "minutes"),
    "action_item": ("action_number", "description", "assigned_to_name", "closure_notes"),
    "safety_incident": ("incident_number", "incident_type", "description", "immediate_action", "root_cause", "corrective_actions"),
    "document_section": ("title", "heading_path", "body"),
    "handover_observation": ("item_number", "description", "remarks"),
}
REQUIRED_CHUNK_FIELDS = frozenset({
    "id", "body", "organization_id", "project_id", "semantic_document_id",
    "construction_document_id", "document_revision_id", "source_entity_type",
    "source_entity_id", "source_file_id", "import_batch_id", "page_start",
    "page_end", "sheet_name", "row_start", "row_end", "heading_path",
    "storage_bucket", "storage_object_path",
    "chunk_ordinal", "content_checksum", "token_count", "embedding_model",
    "embedding_dimensions", "projection_version", "chunking_version",
    "approval_status", "index_status", "metadata",
})


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def project_entity(
    entity_type: str,
    record: dict[str, Any],
    *,
    projection_version_id: str,
    projection_version: int,
) -> dict[str, Any]:
    """Create text only for the frozen descriptive allowlist."""
    if record.get("approval_status") != "approved":
        raise ValueError("Only approved source records may be projected")
    if not record.get("approved_at"):
        raise ValueError("Approved source records need an approved_at instant")
    fields = DESCRIPTIVE_ENTITY_FIELDS.get(entity_type)
    if fields is None:
        raise ValueError(f"{entity_type!r} is SQL-only or is not an approved semantic projection")
    lines = [f"{field.replace('_', ' ').title()}: {_normalize_text(record.get(field))}" for field in fields if _normalize_text(record.get(field))]
    if not lines:
        raise ValueError("A semantic projection needs descriptive content")
    body = "\n".join(lines)
    if projection_version < 1:
        raise ValueError("Projection versions start at 1")
    construction_document_id = record.get("construction_document_id")
    document_revision_id = record.get("document_revision_id")
    if (construction_document_id is None) != (document_revision_id is None):
        raise ValueError("Construction document and revision IDs must both be set or both be null")
    return {
        "source_entity_type": entity_type,
        "source_entity_id": str(uuid.UUID(str(record["id"]))),
        "organization_id": str(uuid.UUID(str(record["organization_id"]))),
        "project_id": str(uuid.UUID(str(record["project_id"]))) if record.get("project_id") else None,
        "construction_document_id": (
            str(uuid.UUID(str(construction_document_id))) if construction_document_id else None
        ),
        "document_revision_id": (
            str(uuid.UUID(str(document_revision_id))) if document_revision_id else None
        ),
        "title": _normalize_text(record.get("title") or record.get("name") or lines[0].split(":", 1)[-1]),
        "body": body,
        "language_code": "en",
        "projection_version_id": str(uuid.UUID(projection_version_id)),
        "projection_version": projection_version,
        "content_checksum": _sha(body),
        "approval_status": "approved",
        "approved_at": str(record["approved_at"]),
        "index_status": "pending",
    }


@dataclass(frozen=True)
class RevisionContext:
    organization_id: str
    project_id: str | None
    semantic_document_id: str
    construction_document_id: str
    document_revision_id: str
    source_entity_id: str
    source_file_id: str | None
    import_batch_id: str | None
    storage_bucket: str
    storage_object_path: str
    approval_status: str
    projection_version_id: str
    projection_version: int = 1
    chunking_version: str = "pdf-heading-pages-v1"
    embedding_model: str = EMBEDDING_MODEL

    def __post_init__(self) -> None:
        for value in (
            self.organization_id, self.semantic_document_id, self.construction_document_id,
            self.document_revision_id, self.source_entity_id, self.projection_version_id,
        ):
            uuid.UUID(value)
        if self.project_id:
            uuid.UUID(self.project_id)
        if (self.source_file_id is None) != (self.import_batch_id is None):
            raise ValueError("source_file_id and import_batch_id must both be set or both be null")
        if self.source_file_id is not None:
            uuid.UUID(self.source_file_id)
            uuid.UUID(self.import_batch_id or "")
        if not self.storage_bucket or not self.storage_object_path:
            raise ValueError("Storage provenance is required")
        if self.projection_version < 1 or not self.chunking_version:
            raise ValueError("Projection and chunking versions are required")
        if self.approval_status != "approved":
            raise ValueError("Only approved document revisions may be chunked")
        if self.embedding_model != EMBEDDING_MODEL:
            raise ValueError(f"Embedding model must be {EMBEDDING_MODEL}")


def validate_embedding(vector: list[float], model: str = EMBEDDING_MODEL) -> list[float]:
    if model != EMBEDDING_MODEL:
        raise ValueError(f"Embedding model must be {EMBEDDING_MODEL}")
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError("Embedding must contain exactly 1536 values")
    normalized = [float(value) for value in vector]
    if any(not math.isfinite(value) for value in normalized) or not any(value != 0 for value in normalized):
        raise ValueError("Embedding must be finite and non-zero")
    return normalized


def validate_semantic_chunk(chunk: dict[str, Any]) -> None:
    missing = REQUIRED_CHUNK_FIELDS - set(chunk)
    if missing:
        raise ValueError(f"Semantic chunk is missing required fields: {', '.join(sorted(missing))}")
    uuid.UUID(str(chunk["id"]))
    for field in ("organization_id", "semantic_document_id", "source_entity_id"):
        uuid.UUID(str(chunk[field]))
    for field in ("project_id", "construction_document_id", "document_revision_id", "source_file_id", "import_batch_id"):
        if chunk[field] is not None:
            uuid.UUID(str(chunk[field]))
    if (chunk["source_file_id"] is None) != (chunk["import_batch_id"] is None):
        raise ValueError("Semantic chunk ingestion lineage must be complete or entirely null")
    if (chunk["construction_document_id"] is None) != (chunk["document_revision_id"] is None):
        raise ValueError("Semantic chunk document lineage must be complete or entirely null")
    if not isinstance(chunk["projection_version"], int) or chunk["projection_version"] < 1:
        raise ValueError("Semantic chunk projection_version must be a positive integer")
    if not str(chunk["body"]).strip() or chunk["content_checksum"] != _sha(str(chunk["body"])):
        raise ValueError("Semantic chunk text/checksum is invalid")
    if chunk["embedding_model"] != EMBEDDING_MODEL or chunk["embedding_dimensions"] != EMBEDDING_DIMENSIONS:
        raise ValueError("Semantic chunk embedding contract is invalid")
    if chunk["approval_status"] != "approved" or chunk["index_status"] != "pending":
        raise ValueError("Only approved pending chunks may be indexed")
    metadata = chunk["metadata"]
    metadata_fields = REQUIRED_CHUNK_FIELDS - {
        "id", "body", "chunk_ordinal", "metadata", "construction_document_id"
    }
    for field in metadata_fields:
        if metadata.get(field) != chunk.get(field):
            raise ValueError(f"Semantic chunk metadata mismatch: {field}")
    if metadata.get("document_id") != chunk.get("construction_document_id"):
        raise ValueError("Semantic chunk metadata mismatch: document_id")


def _reader(source: Path | bytes | BinaryIO) -> PdfReader:
    if isinstance(source, Path):
        return PdfReader(str(source))
    if isinstance(source, bytes):
        return PdfReader(BytesIO(source))
    return PdfReader(source)


def _heading(line: str) -> bool:
    stripped = line.strip()
    if not 3 <= len(stripped) <= 120:
        return False
    return bool(re.match(r"^(?:\d+(?:\.\d+)*[.)]?\s+|[A-Z][A-Z\s/&-]{3,})", stripped))


def extract_revision_chunks(
    source: Path | bytes | BinaryIO,
    context: RevisionContext,
    *,
    max_words: int = 700,
    overlap_words: int = 80,
) -> list[dict[str, Any]]:
    """Chunk approved PDF text with stable IDs and typed provenance."""
    reader = _reader(source)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported")
    chunks: list[dict[str, Any]] = []
    heading_path: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        page_heading = next((line for line in lines if _heading(line)), None)
        if page_heading:
            heading_path = [page_heading]
        words = re.findall(r"\S+", "\n".join(lines))
        step = max(1, max_words - overlap_words)
        for start in range(0, len(words), step):
            body = " ".join(words[start:start + max_words])
            content_sha = _sha(body)
            ordinal = len(chunks) + 1
            identity = "|".join((
                context.semantic_document_id, str(context.projection_version),
                context.chunking_version, str(page_number), str(page_number),
                "/".join(heading_path), str(ordinal), content_sha,
            ))
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
            metadata = {
                "organization_id": context.organization_id,
                "project_id": context.project_id,
                "semantic_document_id": context.semantic_document_id,
                "document_id": context.construction_document_id,
                "document_revision_id": context.document_revision_id,
                "source_entity_type": "document_section",
                "source_entity_id": context.source_entity_id,
                "source_file_id": context.source_file_id,
                "import_batch_id": context.import_batch_id,
                "storage_bucket": context.storage_bucket,
                "storage_object_path": context.storage_object_path,
                "page_start": page_number,
                "page_end": page_number,
                "sheet_name": None,
                "row_start": None,
                "row_end": None,
                "heading_path": heading_path.copy(),
                "content_checksum": content_sha,
                "token_count": len(words[start:start + max_words]),
                "embedding_model": context.embedding_model,
                "embedding_dimensions": EMBEDDING_DIMENSIONS,
                "projection_version": context.projection_version,
                "chunking_version": context.chunking_version,
                "approval_status": "approved",
                "index_status": "pending",
            }
            chunks.append({
                "id": chunk_id,
                "body": body,
                "construction_document_id": context.construction_document_id,
                "chunk_ordinal": ordinal,
                "metadata": metadata,
                **{key: value for key, value in metadata.items() if key != "document_id"},
            })
    if not chunks:
        raise ValueError("No searchable text found; scanned PDFs require OCR")
    return chunks


SEMANTIC_HYBRID_SQL = """
with dense_candidates as (
  select c.id,c.embedding operator(extensions.<=>) %(vector)s::extensions.vector as distance
  from semantic.semantic_chunks c
  join semantic.semantic_documents d
    on d.organization_id=c.organization_id and d.id=c.semantic_document_id
  where c.organization_id=%(organization_id)s::uuid
    and (c.project_id is null or c.project_id=any(%(project_ids)s::uuid[]))
    and d.organization_id=%(organization_id)s::uuid
    and (d.project_id is null or d.project_id=any(%(project_ids)s::uuid[]))
    and c.approval_status='approved' and d.approval_status='approved'
    and c.index_status='ready' and d.index_status='ready'
    and c.embedding_model=%(embedding_model)s
    and c.embedding_dimensions=1536
    and c.projection_version=%(projection_version)s::integer
    and d.projection_version=%(projection_version)s::integer
    and c.chunking_version=%(chunking_version)s
    and exists (
      select 1 from semantic.semantic_projection_versions v
      where v.organization_id=d.organization_id and v.id=d.projection_version_id
        and v.version_no=d.projection_version and v.status='active'
    )
  order by c.embedding operator(extensions.<=>) %(vector)s::extensions.vector,c.id
  limit %(candidate_limit)s
), lexical_candidates as (
  select c.id,ts_rank_cd(c.search_vector,websearch_to_tsquery('english',%(query)s)) as relevance
  from semantic.semantic_chunks c
  join semantic.semantic_documents d
    on d.organization_id=c.organization_id and d.id=c.semantic_document_id
  where c.organization_id=%(organization_id)s::uuid
    and (c.project_id is null or c.project_id=any(%(project_ids)s::uuid[]))
    and d.organization_id=%(organization_id)s::uuid
    and (d.project_id is null or d.project_id=any(%(project_ids)s::uuid[]))
    and c.approval_status='approved' and d.approval_status='approved'
    and c.index_status='ready' and d.index_status='ready'
    and c.embedding_model=%(embedding_model)s
    and c.embedding_dimensions=1536
    and c.projection_version=%(projection_version)s::integer
    and d.projection_version=%(projection_version)s::integer
    and c.chunking_version=%(chunking_version)s
    and exists (
      select 1 from semantic.semantic_projection_versions v
      where v.organization_id=d.organization_id and v.id=d.projection_version_id
        and v.version_no=d.projection_version and v.status='active'
    )
    and c.search_vector @@ websearch_to_tsquery('english',%(query)s)
  order by relevance desc,c.id
  limit %(candidate_limit)s
), ranks as (
  select id,0.6/(60+row_number() over(order by distance,id)) as score from dense_candidates
  union all
  select id,0.4/(60+row_number() over(order by relevance desc,id)) as score from lexical_candidates
), fused as (select id,sum(score) relevance from ranks group by id)
select c.id,c.body,c.metadata,f.relevance
from fused f
join semantic.semantic_chunks c on c.id=f.id
join semantic.semantic_documents d
  on d.organization_id=c.organization_id and d.id=c.semantic_document_id
where c.organization_id=%(organization_id)s::uuid
  and (c.project_id is null or c.project_id=any(%(project_ids)s::uuid[]))
  and d.organization_id=%(organization_id)s::uuid
  and (d.project_id is null or d.project_id=any(%(project_ids)s::uuid[]))
  and c.approval_status='approved' and d.approval_status='approved'
  and c.index_status='ready' and d.index_status='ready'
  and c.embedding_model=%(embedding_model)s and c.embedding_dimensions=1536
  and c.projection_version=%(projection_version)s::integer and d.projection_version=%(projection_version)s::integer
  and c.chunking_version=%(chunking_version)s
  and exists (
    select 1 from semantic.semantic_projection_versions v
    where v.organization_id=d.organization_id and v.id=d.projection_version_id
      and v.version_no=d.projection_version and v.status='active'
  )
order by f.relevance desc,c.id
limit %(limit)s
"""


class SemanticSearch:
    """Query only the new semantic layer with authorization in every branch."""

    def __init__(self, connection_factory, embedder, *, projection_version: int, chunking_version: str):
        if not isinstance(projection_version, int) or projection_version < 1 or not chunking_version:
            raise ValueError("Active projection and chunking versions are required")
        self.connection_factory = connection_factory
        self.embedder = embedder
        self.projection_version = projection_version
        self.chunking_version = chunking_version

    def search(self, query: str, organization_id: str, allowed_project_ids: list[str], limit: int = 5) -> list[dict[str, Any]]:
        if not query.strip() or not 1 <= limit <= 20:
            raise ValueError("A query and limit between 1 and 20 are required")
        organization_id = str(uuid.UUID(organization_id))
        projects = [str(uuid.UUID(value)) for value in allowed_project_ids]
        vectors = self.embedder([query])
        if len(vectors) != 1:
            raise ValueError("Embedding provider returned an incomplete query batch")
        vector = json.dumps(validate_embedding(vectors[0]), allow_nan=False)
        params = {
            "organization_id": organization_id,
            "project_ids": projects,
            "query": query,
            "vector": vector,
            "embedding_model": EMBEDDING_MODEL,
            "projection_version": self.projection_version,
            "chunking_version": self.chunking_version,
            "candidate_limit": max(40, limit * 8),
            "limit": limit,
        }
        with closing(self.connection_factory()) as connection:
            with connection:
                connection.execute("set local hnsw.iterative_scan = 'strict_order'")
                rows = connection.execute_native(SEMANTIC_HYBRID_SQL, params).fetchall()
        return [dict(row) for row in rows]


INDEX_SQL = """
select * from semantic.publish_chunk_embeddings(
  %(org_id)s::uuid,
  %(job_id)s::uuid,
  %(chunks_jsonb)s::jsonb,
  %(idempotency_key)s::text
)
"""


class SemanticIndexAdapter:
    """Publish a complete validated embedding batch through one DB routine."""

    def __init__(self, connection_factory, embedder):
        self.connection_factory = connection_factory
        self.embedder = embedder

    def upsert(self, chunks: list[dict[str, Any]], *, embedding_job_id: str | None = None) -> int:
        if not chunks:
            return 0
        if len(chunks) > 1000:
            raise ValueError("An embedding publication is limited to 1000 chunks")
        batch_fields = {
            "organization_id": "organization",
            "semantic_document_id": "semantic document",
            "project_id": "project",
            "embedding_model": "embedding model",
            "projection_version": "projection version",
            "chunking_version": "chunking version",
        }
        for field, label in batch_fields.items():
            values = {chunk.get(field) for chunk in chunks}
            if len(values) != 1 or (None in values and field != "project_id"):
                raise ValueError(f"An embedding batch must belong to one {label}")
        organization_ids = {chunk.get("organization_id") for chunk in chunks}
        organization_id = str(uuid.UUID(next(iter(organization_ids))))
        job_id = str(uuid.UUID(embedding_job_id)) if embedding_job_id else str(uuid.uuid5(
            uuid.NAMESPACE_URL, "|".join(sorted(chunk["id"] for chunk in chunks))
        ))
        if len({chunk.get("id") for chunk in chunks}) != len(chunks):
            raise ValueError("An embedding batch cannot contain duplicate chunks")
        for chunk in chunks:
            validate_semantic_chunk(chunk)
        texts = [chunk["body"] for chunk in chunks]
        vectors = self.embedder(texts)
        if len(vectors) != len(chunks):
            raise ValueError("Embedding provider returned an incomplete batch")
        payload = []
        for chunk, vector in zip(chunks, vectors):
            payload.append({"chunk": chunk, "embedding": validate_embedding(vector)})
        idempotency_key = _sha("|".join(sorted(chunk["id"] for chunk in chunks)))
        params = {
            "org_id": organization_id,
            "job_id": job_id,
            "chunks_jsonb": json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
            "idempotency_key": idempotency_key,
        }
        with closing(self.connection_factory()) as connection:
            with connection:
                row = connection.execute_native(INDEX_SQL, params).fetchone()
        if not row or dict(row).get("status") not in {"succeeded", "already_succeeded"}:
            raise RuntimeError("Embedding publication did not complete idempotently")
        return len(chunks)

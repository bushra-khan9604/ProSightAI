"""Hybrid PostgreSQL full-text + pgvector retrieval with authoritative visibility."""
from __future__ import annotations

import json
import math
from contextlib import closing

from ..config import get_settings
from ..contracts import EvidenceItem, RAGEvidence
from .store import OpenAIEmbedder, RAGStore

# Scope and publication checks occur in BOTH candidate branches before ranking.
# RRF combines the two ranking scales; effective date only breaks final ties.
HYBRID_SQL = """
WITH dense_candidates AS (
    SELECT c.id, c.embedding OPERATOR(extensions.<=>) %(vector)s::extensions.vector AS distance
    FROM prosight.document_chunks c JOIN prosight.documents d ON d.id=c.document_id
    WHERE c.project_code=ANY(%(projects)s::text[]) AND d.project_code=ANY(%(projects)s::text[])
      AND d.approval_status='approved' AND d.index_status='ready' AND d.status='ready'
      AND c.metadata->>'approval_status'='approved' AND c.embedding_model=%(model)s
      AND (%(documents)s::text[] IS NULL OR c.document_id=ANY(%(documents)s::text[]))
    ORDER BY c.embedding OPERATOR(extensions.<=>) %(vector)s::extensions.vector
    LIMIT %(candidates)s
), dense AS (
    SELECT id, row_number() OVER (ORDER BY distance,id) AS rank FROM dense_candidates
), lexical_candidates AS (
    SELECT c.id, ts_rank_cd(c.search_text,websearch_to_tsquery('english',%(query)s)) AS relevance
    FROM prosight.document_chunks c JOIN prosight.documents d ON d.id=c.document_id
    WHERE c.project_code=ANY(%(projects)s::text[]) AND d.project_code=ANY(%(projects)s::text[])
      AND d.approval_status='approved' AND d.index_status='ready' AND d.status='ready'
      AND c.metadata->>'approval_status'='approved' AND c.embedding_model=%(model)s
      AND (%(documents)s::text[] IS NULL OR c.document_id=ANY(%(documents)s::text[]))
      AND c.search_text @@ websearch_to_tsquery('english',%(query)s)
    ORDER BY relevance DESC,c.id LIMIT %(candidates)s
), lexical AS (
    SELECT id,row_number() OVER (ORDER BY relevance DESC,id) AS rank FROM lexical_candidates
), ranks AS (
    SELECT id, 0.6/(60.0+rank) AS score FROM dense
    UNION ALL SELECT id,0.4/(60.0+rank) AS score FROM lexical
), fused AS (
    SELECT id,sum(score) AS relevance FROM ranks GROUP BY id
)
SELECT c.body,c.metadata,f.relevance
FROM fused f JOIN prosight.document_chunks c ON c.id=f.id
JOIN prosight.documents d ON d.id=c.document_id
WHERE d.approval_status='approved' AND d.index_status='ready' AND d.status='ready'
ORDER BY f.relevance DESC, c.metadata->>'effective_date' DESC NULLS LAST,c.id
LIMIT %(limit)s
"""


class PgVectorStore:
    """Use the same PostgreSQL pool as structured data; no second database service."""
    dimensions = 1536

    def __init__(self, repository, embedder=None):
        self.repository = repository
        settings = get_settings()
        self.model = settings.embedding_model
        self.embedder = embedder or OpenAIEmbedder(settings.openai_api_key, self.model)

    @classmethod
    def _vector(cls, value):
        if len(value) != cls.dimensions or any(not math.isfinite(float(x)) for x in value):
            raise ValueError("pgvector requires finite 1536-dimensional embeddings")
        if not any(float(x) != 0 for x in value):
            raise ValueError("Cosine embeddings must not be zero vectors")
        return json.dumps([float(x) for x in value], allow_nan=False)

    def add_chunks(self, chunks):
        if not chunks:
            raise ValueError("Cannot publish an empty document index")
        documents = {c["metadata"].get("document_id") for c in chunks}
        projects = {c["metadata"].get("project_code") for c in chunks}
        if len(documents) != 1 or len(projects) != 1 or not all(documents) or not all(projects):
            raise ValueError("One indexing operation must contain exactly one document and project")
        if len({c["id"] for c in chunks}) != len(chunks):
            raise ValueError("Duplicate chunk identifiers")
        if any(c["metadata"].get("approval_status") != "approved" or not c["text"].strip() for c in chunks):
            raise ValueError("Only explicitly approved, nonempty chunks can be indexed")
        document_id, project_code = next(iter(documents)), next(iter(projects))
        # Complete embedding before opening a database transaction. Publication
        # replaces every chunk atomically, so failed batches expose no partial set.
        rows = []
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset:offset+64]
            vectors = self.embedder([c["text"] for c in batch])
            if len(vectors) != len(batch):
                raise ValueError("Embedding provider returned an incomplete batch")
            rows.extend((c["id"], document_id, project_code, c["text"],
                         json.dumps(c["metadata"]), self._vector(v), self.model)
                        for c, v in zip(batch, vectors))
        with closing(self.repository.connect()) as db:
            with db:
                document = db.execute(
                    "SELECT approval_status,project_code FROM documents WHERE id=? FOR UPDATE",
                    (document_id,),
                ).fetchone()
                if not document or document["approval_status"] != "approved" or document["project_code"] != project_code:
                    raise ValueError("Document approval or project scope changed before indexing")
                db.execute("DELETE FROM document_chunks WHERE document_id=?", (document_id,))
                db.executemany(
                    """INSERT INTO document_chunks
                    (id,document_id,project_code,body,metadata,embedding,embedding_model)
                    VALUES (?,?,?,?,?::jsonb,?::extensions.vector,?)""", rows,
                )

    def search(self, query, project_code, limit=5, *, document_ids=None):
        if not project_code.strip():
            raise ValueError("A project scope is required")
        if not 1 <= limit <= 20:
            raise ValueError("Retrieval limit must be between 1 and 20")
        if not query.strip() or document_ids == []:
            return RAGEvidence(query=query, project_code=project_code)
        vectors = self.embedder([query])
        if len(vectors) != 1:
            raise ValueError("Embedding provider returned an incomplete query batch")
        projects = [project_code] if project_code == "COMPANY" else [project_code, "COMPANY"]
        params = {"vector": self._vector(vectors[0]), "query": query,
                  "projects": projects, "model": self.model, "documents": document_ids,
                  "candidates": max(40, limit*8), "limit": limit}
        with closing(self.repository.connect()) as db:
            # Iterative scans compensate for project/document filters in HNSW.
            db.execute("SET LOCAL hnsw.iterative_scan = 'strict_order'")
            # This query already uses psycopg named placeholders.
            rows = db.execute_native(HYBRID_SQL, params).fetchall()
        return RAGEvidence(query=query, project_code=project_code, evidence=[
            EvidenceItem(text=row["body"], citation=RAGStore._citation(row["metadata"]),
                         metadata={**row["metadata"], "relevance": float(row["relevance"]),
                                   "retrieval_backend": "pgvector"}) for row in rows
        ])

    def delete_document(self, document_id):
        with closing(self.repository.connect()) as db:
            with db:
                db.execute("DELETE FROM document_chunks WHERE document_id=?", (document_id,))

    def close(self):
        # Pool ownership belongs to the application repository.
        pass

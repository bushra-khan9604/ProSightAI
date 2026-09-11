"""Supabase pgvector retrieval with a deterministic in-memory test adapter."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Callable

from ..config import get_settings
from ..contracts import EvidenceItem, RAGEvidence
from ..supabase_gateway import SupabaseGateway


EmbeddingFunction = Callable[[list[str]], list[list[float]]]


class RAGStore:
    """Index chunks in PostgreSQL and retrieve them through hybrid search."""

    def __init__(self, persist_dir=None, embedder: EmbeddingFunction | None = None, **_: Any):
        self.embedder = embedder
        self.memory: dict[str, dict[str, Any]] = {}
        self.requires_async_embeddings = embedder is None
        if embedder is None:
            settings = get_settings()
            if not settings.supabase_url or not settings.supabase_service_role_key:
                raise RuntimeError("Supabase RAG requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
            self.user = SupabaseGateway()
            self.service = SupabaseGateway(service=True)

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Persist normalized page chunks; PostgreSQL triggers queue embeddings."""
        if self.embedder:
            vectors = self.embedder([item["text"] for item in chunks])
            for item, vector in zip(chunks, vectors):
                self.memory[item["id"]] = {**item, "embedding": vector}
            return
        rows = []
        for item in chunks:
            metadata = dict(item["metadata"])
            rows.append({
                "id": item["id"], "document_id": metadata["document_id"],
                "project_code": metadata["project_code"], "filename": metadata["filename"],
                "page_number": metadata["page_number"], "chunk_number": metadata["chunk_number"],
                "content": item["text"], "content_hash": item.get("content_hash", "pending"),
                "token_count": item.get("token_count", len(item["text"].split())),
                "reporting_date": metadata.get("reporting_date") or None,
                "effective_date": metadata.get("effective_date") or date.today().isoformat(),
                "date_status": metadata.get("date_status") or "fallback",
                "metadata": metadata, "embedding_model": get_settings().embedding_model,
                "embedding_status": "pending",
            })
        for offset in range(0, len(rows), 100):
            self.service.request(
                "POST", "/rest/v1/document_chunks?on_conflict=id", rows[offset:offset + 100],
                prefer="return=minimal,resolution=merge-duplicates",
            )

    def search(self, query: str, project_code: str, limit: int = 5) -> RAGEvidence:
        if self.embedder:
            return self._memory_search(query, project_code, limit)
        payload = self.user.invoke("hybrid-search", {
            "query": query, "project_code": project_code, "limit": limit,
        })
        evidence = []
        for item in payload.get("evidence", []):
            metadata = {
                **(item.get("metadata") or {}),
                "relevance": round(float(item.get("score", 0)), 6),
            }
            evidence.append(EvidenceItem(
                text=item["content"],
                citation=f"{item['filename']}, page {item['page_number']}",
                metadata=metadata,
            ))
        return RAGEvidence(query=query, project_code=project_code, evidence=evidence)

    def _memory_search(self, query: str, project_code: str, limit: int) -> RAGEvidence:
        query_vector = self.embedder([query])[0]
        candidates = []
        for item in self.memory.values():
            metadata = item["metadata"]
            if metadata["project_code"] != project_code:
                continue
            vector = item["embedding"]
            denominator = math.sqrt(sum(x*x for x in query_vector)) * math.sqrt(sum(x*x for x in vector))
            score = sum(a*b for a,b in zip(query_vector, vector)) / denominator if denominator else 0
            candidates.append((score, metadata.get("effective_date", ""), item))
        candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
        evidence = [EvidenceItem(
            text=item["text"],
            citation=f"{item['metadata']['filename']}, page {item['metadata']['page_number']}",
            metadata={**item["metadata"], "relevance": round(score, 4)},
        ) for score, _, item in candidates[:limit]]
        return RAGEvidence(query=query, project_code=project_code, evidence=evidence)

    def delete_document(self, document_id: str) -> None:
        if self.embedder:
            self.memory = {key: value for key, value in self.memory.items()
                           if value["metadata"]["document_id"] != document_id}
        else:
            self.service.delete("document_chunks", document_id=f"eq.{document_id}")

    def close(self) -> None:
        return None

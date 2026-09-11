"""Application-managed OpenAI embeddings and Supabase hybrid retrieval."""

from __future__ import annotations

import logging
import math
import re
import time
from datetime import date
from typing import Any, Callable

from openai import OpenAI

from ..config import get_settings
from ..contracts import EvidenceItem, RAGEvidence
from ..supabase_gateway import SupabaseGateway


EmbeddingFunction = Callable[[list[str]], list[list[float]]]
logger = logging.getLogger("prosight.rag")


class RAGStore:
    """Embed chunks in-process and retrieve them through an RLS-aware RPC."""

    def __init__(
        self, persist_dir=None, embedder: EmbeddingFunction | None = None,
        *, openai_client: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        **_: Any,
    ):
        self.embedder = embedder
        self.memory: dict[str, dict[str, Any]] = {}
        self.sleeper = sleeper
        self.settings = get_settings()
        if embedder is None:
            if not self.settings.supabase_url or not self.settings.supabase_service_role_key:
                raise RuntimeError("Supabase RAG requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
            if not self.settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is required for document retrieval")
            self.user = SupabaseGateway()
            self.service = SupabaseGateway(service=True)
            self.openai = openai_client or OpenAI(
                api_key=self.settings.openai_api_key, max_retries=0, timeout=60.0
            )

    def _chunk_row(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(item["metadata"])
        content_hash = item.get("content_hash", "pending")
        metadata["content_hash"] = content_hash
        return {
            "id": item["id"], "document_id": metadata["document_id"],
            "project_code": metadata["project_code"], "filename": metadata["filename"],
            "page_number": metadata["page_number"], "chunk_number": metadata["chunk_number"],
            "content": item["text"], "content_hash": content_hash,
            "token_count": item.get("token_count", len(item["text"].split())),
            "reporting_date": metadata.get("reporting_date") or None,
            "effective_date": metadata.get("effective_date") or date.today().isoformat(),
            "date_status": metadata.get("date_status") or "fallback",
            "metadata": metadata, "embedding_model": self.settings.embedding_model,
            "embedding_version": 1, "embedding_status": "pending",
            "embedding_error": None, "embedding_attempts": 0,
        }

    def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        if self.embedder:
            return self.embedder(texts)
        last_error: Exception | None = None
        for attempt in range(1, self.settings.embedding_retry_count + 1):
            try:
                response = self.openai.embeddings.create(
                    model=self.settings.embedding_model,
                    input=texts,
                    dimensions=1536,
                    encoding_format="float",
                )
                ordered = sorted(response.data, key=lambda item: item.index)
                vectors = [list(item.embedding) for item in ordered]
                if len(vectors) != len(texts) or any(len(vector) != 1536 for vector in vectors):
                    raise RuntimeError("Embedding response dimension mismatch")
                return vectors
            except Exception as error:  # SDK error classes vary by transport/version.
                last_error = error
                logger.warning("embedding_batch_retry", extra={"event_data": {
                    "event": "embedding_batch_retry", "attempt": attempt,
                    "batch_size": len(texts), "error_type": type(error).__name__,
                }})
                if attempt < self.settings.embedding_retry_count:
                    self.sleeper(min(16, 2 ** (attempt - 1)))
        raise RuntimeError("Embedding generation failed after retries") from last_error

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Embed normalized chunks in bounded batches and publish them idempotently."""
        if self.embedder:
            vectors = self._embed_with_retry([item["text"] for item in chunks])
            for item, vector in zip(chunks, vectors):
                self.memory[item["id"]] = {**item, "embedding": vector}
            return
        if not chunks:
            raise ValueError("No searchable text was extracted from the document")

        rows = [self._chunk_row(item) for item in chunks]
        document_id = rows[0]["document_id"]
        existing_rows = self.service.select_all(
            "document_chunks",
            select="id,content_hash,embedding_model,embedding_status",
            document_id=f"eq.{document_id}",
        )
        existing = {row["id"]: row for row in existing_rows}
        pending = [row for row in rows if not (
            row["id"] in existing
            and existing[row["id"]].get("content_hash") == row["content_hash"]
            and existing[row["id"]].get("embedding_model") == row["embedding_model"]
            and existing[row["id"]].get("embedding_status") == "ready"
        )]

        for offset in range(0, len(pending), 100):
            self.service.request(
                "POST", "/rest/v1/document_chunks?on_conflict=id", pending[offset:offset + 100],
                prefer="return=minimal,resolution=merge-duplicates",
            )

        batch_size = self.settings.embedding_batch_size
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset:offset + batch_size]
            ids = ",".join(row["id"] for row in batch)
            self.service.update(
                "document_chunks", {"embedding_status": "processing", "embedding_error": None},
                returning=False, id=f"in.({ids})",
            )
            try:
                vectors = self._embed_with_retry([row["content"] for row in batch])
            except Exception as error:
                self.service.update(
                    "document_chunks", {
                        "embedding_status": "failed",
                        "embedding_error": str(error)[:500],
                        "embedding_attempts": self.settings.embedding_retry_count,
                    }, returning=False, id=f"in.({ids})",
                )
                raise
            ready = [{
                **row, "embedding": vector, "embedding_status": "ready",
                "embedding_error": None, "embedding_attempts": 1,
            } for row, vector in zip(batch, vectors)]
            self.service.request(
                "POST", "/rest/v1/document_chunks?on_conflict=id", ready,
                prefer="return=minimal,resolution=merge-duplicates",
            )

        current_ids = {row["id"] for row in rows}
        stale_ids = [row_id for row_id in existing if row_id not in current_ids]
        if stale_ids:
            self.service.delete("document_chunks", id=f"in.({','.join(stale_ids)})")

    def search(self, query: str, project_code: str, limit: int | None = None) -> RAGEvidence:
        if self.embedder:
            return self._memory_search(query, project_code, limit or 5)
        evidence_limit = min(limit or self.settings.retrieval_evidence_count, 20)
        query_vector = self._embed_with_retry([query])[0]
        rows = self.user.rpc("hybrid_search", {
            "query_text": query,
            "query_embedding": query_vector,
            "match_project_code": project_code,
            "match_count": min(50, evidence_limit * 3),
            "candidate_count": self.settings.retrieval_candidate_count,
        }) or []
        selected: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()
        for item in rows:
            similarity = float(item.get("semantic_similarity") or -1.0)
            if not item.get("keyword_match") and similarity < self.settings.retrieval_confidence_threshold:
                continue
            content_hash = str(item.get("content_hash") or "")
            if content_hash and content_hash in seen_hashes:
                continue
            if any(self._near_duplicate(item["content"], prior["content"]) for prior in selected):
                continue
            selected.append(item)
            if content_hash:
                seen_hashes.add(content_hash)
            if len(selected) >= evidence_limit:
                break

        evidence = []
        for item in selected:
            metadata = {
                **(item.get("metadata") or {}),
                "relevance": round(float(item.get("score", 0)), 6),
                "semantic_similarity": round(float(item.get("semantic_similarity") or 0), 6),
                "keyword_match": bool(item.get("keyword_match")),
            }
            evidence.append(EvidenceItem(
                text=item["content"],
                citation=f"{item['filename']}, page {item['page_number']}",
                metadata=metadata,
            ))
        return RAGEvidence(query=query, project_code=project_code, evidence=evidence)

    @staticmethod
    def _near_duplicate(left: str, right: str, threshold: float = 0.85) -> bool:
        words_left = set(re.findall(r"[a-z0-9]+", left.casefold()))
        words_right = set(re.findall(r"[a-z0-9]+", right.casefold()))
        union = words_left | words_right
        return bool(union) and len(words_left & words_right) / len(union) >= threshold

    def _memory_search(self, query: str, project_code: str, limit: int) -> RAGEvidence:
        query_vector = self._embed_with_retry([query])[0]
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

    def health(self) -> dict[str, Any]:
        """Return bounded operational state for the public health endpoint."""
        if self.embedder:
            return {"status": "ready", "chunks": len(self.memory), "pending_jobs": 0, "failed_jobs": 0}
        return {
            "status": "ready", "embedding_model": self.settings.embedding_model,
            "openai_configured": bool(self.settings.openai_api_key),
            "pending_jobs": self.service.count(
                "ingestion_jobs", status="in.(queued,processing,embedding)"
            ),
            "failed_jobs": self.service.count("ingestion_jobs", status="eq.failed"),
        }

    def delete_document(self, document_id: str) -> None:
        if self.embedder:
            self.memory = {key: value for key, value in self.memory.items()
                           if value["metadata"]["document_id"] != document_id}
        else:
            self.service.delete("document_chunks", document_id=f"eq.{document_id}")

    def close(self) -> None:
        return None

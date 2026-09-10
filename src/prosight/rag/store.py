"""Persistent Chroma-backed vector retrieval with project metadata filters."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..config import get_settings
from ..contracts import EvidenceItem, RAGEvidence


EmbeddingFunction = Callable[[list[str]], list[list[float]]]


class OpenAIEmbedder:
    """Generate low-cost embeddings through the OpenAI Embeddings API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for document indexing")
        self.api_key, self.model = api_key, model

    def __call__(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch while preserving its original order."""
        request = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps({"model": self.model, "input": texts}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read())
        return [item["embedding"] for item in sorted(payload["data"], key=lambda item: item["index"])]


class RAGStore:
    """Index and retrieve PDF chunks from a persistent local Chroma collection."""

    def __init__(
        self,
        persist_dir: str | Path,
        embedder: EmbeddingFunction | None = None,
        collection_name: str = "prosight_project_documents",
    ):
        try:
            import chromadb
        except ImportError as error:
            raise RuntimeError("Install project dependencies to enable the RAG store") from error
        settings = get_settings()
        self.embedder = embedder or OpenAIEmbedder(
            settings.openai_api_key, settings.embedding_model
        )
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(
            collection_name, metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """Embed and persist normalized chunks in bounded batches."""
        for offset in range(0, len(chunks), 64):
            batch = chunks[offset : offset + 64]
            texts = [item["text"] for item in batch]
            self.collection.upsert(
                ids=[item["id"] for item in batch],
                documents=texts,
                metadatas=[item["metadata"] for item in batch],
                embeddings=self.embedder(texts),
            )

    def search(
        self, query: str, project_code: str, limit: int = 5,
        *, document_ids: list[str] | None = None,
    ) -> RAGEvidence:
        """Retrieve approved project chunks with dense + lexical rank fusion.

        Both candidate sources require explicit approval. The optional document
        allowlist comes from authoritative database visibility, not model input.
        Lexical candidates are bounded; a dedicated ranked keyword index is a
        separate migration, not simulated by loading every project chunk.
        """
        if not project_code.strip():
            raise ValueError("A project scope is required")
        if not 1 <= limit <= 20:
            raise ValueError("Retrieval limit must be between 1 and 20")
        if not query.strip() or document_ids == []:
            return RAGEvidence(query=query, project_code=project_code, evidence=[])
        project_filter = {"project_code": project_code} if project_code == "COMPANY" else {
            "$or": [{"project_code": project_code}, {"project_code": "COMPANY"}]
        }
        filters = [project_filter, {"approval_status": "approved"}]
        if document_ids is not None:
            filters.append({"document_id": {"$in": document_ids}})
        where = {"$and": filters}
        result = self.collection.query(
            query_embeddings=self.embedder([query]),
            n_results=max(20, min(limit * 8, 50)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        dense_rows: list[tuple[str, str, dict[str, Any], float]] = []
        for text, metadata, distance in zip(
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
        ):
            if not self._is_retrievable(metadata, project_code):
                continue
            chunk_id = f"{metadata.get('document_id', '')}:{metadata.get('page_number', '')}:{metadata.get('chunk_number', '')}"
            dense_rows.append((chunk_id, text, metadata, float(distance)))

        query_terms = self._terms(query)
        lexical_rows = {"documents": [], "metadatas": []}
        if query_terms:
            # Match whole terms case-insensitively in Chroma. Cap transfer and
            # Python scoring at 200 candidates; this is not a BM25 ranking.
            pattern = r"(?i)\b(?:" + "|".join(
                re.escape(term) for term in sorted(query_terms)[:32]
            ) + r")\b"
            lexical_rows = self.collection.get(
                where=where, where_document={"$regex": pattern}, limit=200,
                include=["documents", "metadatas"],
            )
        rows: dict[str, dict[str, Any]] = {}
        for rank, (chunk_id, text, metadata, distance) in enumerate(dense_rows, start=1):
            rows[chunk_id] = {
                "text": text, "metadata": metadata, "dense_rank": rank,
                "dense_similarity": max(0.0, 1 - distance), "lexical_score": 0.0,
            }
        lexical_ranked: list[tuple[float, str, str, dict[str, Any]]] = []
        for text, metadata in zip(
            lexical_rows.get("documents", []) or [],
            lexical_rows.get("metadatas", []) or [],
        ):
            if not self._is_retrievable(metadata, project_code):
                continue
            score = self._lexical_score(query_terms, text, query)
            if score <= 0:
                continue
            chunk_id = f"{metadata.get('document_id', '')}:{metadata.get('page_number', '')}:{metadata.get('chunk_number', '')}"
            lexical_ranked.append((score, chunk_id, text, metadata))
        lexical_ranked.sort(key=lambda item: item[0], reverse=True)
        for rank, (score, chunk_id, text, metadata) in enumerate(lexical_ranked, start=1):
            current = rows.setdefault(
                chunk_id,
                {"text": text, "metadata": metadata, "dense_rank": None,
                 "dense_similarity": 0.0, "lexical_score": score},
            )
            current["lexical_rank"] = rank
            current["lexical_score"] = score

        if not rows:
            return RAGEvidence(query=query, project_code=project_code, evidence=[])

        candidates: list[EvidenceItem] = []
        for row in rows.values():
            dense_rank = row.get("dense_rank")
            lexical_rank = row.get("lexical_rank")
            # Reciprocal rank fusion is stable across incomparable distance
            # and lexical-score scales.
            fused = (0.6 / (60 + dense_rank) if dense_rank else 0.0) + (
                0.4 / (60 + lexical_rank) if lexical_rank else 0.0
            )
            metadata = {
                **row["metadata"],
                "relevance": round(fused, 6),
                "dense_similarity": round(row["dense_similarity"], 4),
                "lexical_score": round(row["lexical_score"], 4),
            }
            candidates.append(
                EvidenceItem(
                    text=row["text"],
                    citation=self._citation(metadata),
                    metadata=metadata,
                )
            )
        candidates.sort(
            key=lambda item: (
                item.metadata["relevance"],
                item.metadata.get("effective_date", ""),
            ),
            reverse=True,
        )
        return RAGEvidence(
            query=query, project_code=project_code, evidence=candidates[:limit]
        )

    @staticmethod
    def _terms(value: str) -> set[str]:
        return {term for term in re.findall(r"\w+", value.casefold()) if len(term) > 1}

    @classmethod
    def _lexical_score(cls, query_terms: set[str], text: str, query: str = "") -> float:
        if not query_terms:
            return 0.0
        text_terms = cls._terms(text)
        overlap = len(query_terms & text_terms)
        phrase = " ".join(re.findall(r"\w+", query.casefold()))
        normalized_text = " ".join(re.findall(r"\w+", text.casefold()))
        phrase_bonus = 1.0 if phrase and f" {phrase} " in f" {normalized_text} " else 0.0
        return overlap / len(query_terms) + phrase_bonus

    @staticmethod
    def _is_retrievable(metadata: dict[str, Any], project_code: str) -> bool:
        return (
            metadata.get("project_code") in {project_code, "COMPANY"}
            and metadata.get("approval_status") == "approved"
        )

    @staticmethod
    def _citation(metadata: dict[str, Any]) -> str:
        filename = metadata.get("filename", "Uploaded document")
        revision = metadata.get("revision")
        page = metadata.get("page_number")
        sheet = metadata.get("sheet_name")
        location = f"page {page}" if page else f"sheet {sheet}" if sheet else "source"
        suffix = f", revision {revision}" if revision else ""
        return f"{filename}{suffix}, {location}"

    def delete_document(self, document_id: str) -> None:
        """Remove every vector belonging to one document."""
        self.collection.delete(where={"document_id": document_id})

    def close(self) -> None:
        """Release local Chroma file handles, primarily for clean shutdown/tests."""
        close = getattr(self.client, "close", None)
        if close:
            close()

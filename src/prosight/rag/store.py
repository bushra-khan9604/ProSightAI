"""Persistent Chroma-backed vector retrieval with project metadata filters."""

from __future__ import annotations

import json
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

    def search(self, query: str, project_code: str, limit: int = 5) -> RAGEvidence:
        """Retrieve relevant project chunks, preferring newer report evidence."""
        result = self.collection.query(
            query_embeddings=self.embedder([query]),
            n_results=max(10, min(limit * 4, 20)),
            where={"project_code": project_code},
            include=["documents", "metadatas", "distances"],
        )
        candidates: list[EvidenceItem] = []
        for text, metadata, distance in zip(
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
        ):
            citation = f"{metadata['filename']}, page {metadata['page_number']}"
            candidates.append(
                EvidenceItem(
                    text=text,
                    citation=citation,
                    metadata={**metadata, "relevance": round(1 - float(distance), 4)},
                )
            )
        if not candidates:
            return RAGEvidence(query=query, project_code=project_code, evidence=[])
        best_relevance = max(item.metadata["relevance"] for item in candidates)
        relevant = [
            item
            for item in candidates
            if item.metadata["relevance"] >= best_relevance - 0.15
        ]
        relevant.sort(
            key=lambda item: (
                item.metadata.get("effective_date", ""),
                item.metadata["relevance"],
            ),
            reverse=True,
        )
        return RAGEvidence(
            query=query, project_code=project_code, evidence=relevant[:limit]
        )

    def delete_document(self, document_id: str) -> None:
        """Remove every vector belonging to one document."""
        self.collection.delete(where={"document_id": document_id})

    def close(self) -> None:
        """Release local Chroma file handles, primarily for clean shutdown/tests."""
        close = getattr(self.client, "close", None)
        if close:
            close()

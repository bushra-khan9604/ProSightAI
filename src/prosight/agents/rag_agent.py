"""RAG Agent boundary restricted to project-scoped vector retrieval."""

from __future__ import annotations

from ..contracts import RAGEvidence
from ..rag.store import RAGStore


class RAGAgent:
    """Retrieve document evidence without database or mutation access."""

    name = "RAG Agent"

    def __init__(self, store: RAGStore):
        self.store = store

    def retrieve(self, query: str, project_code: str) -> RAGEvidence:
        """Search only the selected project's indexed PDF chunks."""
        return self.store.search(query, project_code)

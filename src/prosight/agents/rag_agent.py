"""RAG Agent boundary restricted to project-scoped vector retrieval."""

from __future__ import annotations

from ..contracts import RAGEvidence
from ..rag.store import RAGStore
from ..repository import ProjectRepository


class RAGAgent:
    """Retrieve document evidence without database or mutation access."""

    name = "RAG Agent"
    company_scope = "COMPANY"

    def __init__(self, store: RAGStore, repository: ProjectRepository):
        self.store = store
        self.repository = repository

    def retrieve(self, query: str, project_code: str) -> RAGEvidence:
        """Search only approved, fully indexed documents still in the database.

        Approval metadata in a derived vector index alone is insufficient:
        failed, deleted, and partially indexed documents must stay invisible.
        This is project/document visibility, not tenant authorization.
        """
        visible = self._visible_documents(project_code)
        result = self.store.search(query, project_code, document_ids=sorted(visible))
        # Recheck after retrieval in case deletion/revocation occurred while
        # embedding the query. Fail closed if the authoritative lookup fails.
        visible = self._visible_documents(project_code)
        allowed_projects = {project_code, self.company_scope}
        result.evidence = [
            item for item in result.evidence
            if item.metadata.get("document_id") in visible
            and item.metadata.get("project_code") in allowed_projects
            and item.metadata.get("approval_status") == "approved"
        ]
        return result

    def _visible_documents(self, project_code: str) -> set[str]:
        scopes = [project_code]
        if project_code != self.company_scope:
            scopes.append(self.company_scope)
        return {
            item["id"] for scope in scopes for item in self.repository.list_documents(scope)
            if item.get("kind") == "pdf"
            and item.get("approval_status") == "approved"
            and item.get("index_status") == "ready"
            and item.get("status") == "ready"
        }

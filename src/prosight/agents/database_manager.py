"""Database Manager Agent boundary and controlled mutation preparation."""

from __future__ import annotations

from typing import Any

from ..contracts import ChangeOperation, ChangePreview, DatabaseEvidence, EvidenceItem
from ..repository import ProjectRepository


class DatabaseManagerAgent:
    """Exclusive, governed gateway to structured project information."""

    name = "Database Manager Agent"

    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def read(self, query: str, project_code: str | None, role: str) -> DatabaseEvidence:
        """Execute a role-filtered semantic read against SQLite.

        The agent never accepts SQL from a model. It selects an allowlisted
        repository operation and returns the stored project payload as typed
        evidence for the Writer Agent.
        """
        if project_code:
            project = self.repository.find_project(project_code, role)
            if not project:
                return DatabaseEvidence(summary="Project was not found")
            citations = project.get("sources", [f"Project database: {project['code']}"])
            return DatabaseEvidence(
                records=[project],
                evidence=[
                    EvidenceItem(
                        text=f"Authorized project record for {project['code']}: {project}",
                        citation=citation,
                        metadata={"project_code": project["code"], "source_type": "database"},
                    )
                    for citation in citations[:5]
                ],
                summary=f"Found project {project['code']}",
            )
        projects = self.repository.list_projects(user_role=role)
        return DatabaseEvidence(
            records=projects,
            evidence=[
                EvidenceItem(
                    text=f"{item['code']}: {item['name']} ({item['status']})",
                    citation=f"Project database: {item['code']}",
                    metadata={"project_code": item["code"], "source_type": "database"},
                )
                for item in projects
            ],
            summary=f"Found {len(projects)} authorized projects",
        )

    def propose_change(
        self, operation: ChangeOperation, requested_by: str
    ) -> DatabaseEvidence:
        """Persist a validated change preview; execution always requires Admin approval."""
        before = self.repository.find_project(operation.project_code, "admin")
        if operation.action == "record_delete":
            after = None
        else:
            after = operation.payload
        preview = ChangePreview(operation=operation, before=before, after=after)
        change = self.repository.create_change_request(
            operation.action,
            operation.project_code,
            operation.payload,
            preview.model_dump(mode="json"),
            requested_by,
        )
        return DatabaseEvidence(
            change_request_id=change["id"],
            summary=f"Change preview {change['id']} is awaiting Admin approval",
        )

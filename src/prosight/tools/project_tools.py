"""Role-bound project data tools and provider-neutral JSON schemas."""

from __future__ import annotations

from typing import Any, Callable

from ..repository import ProjectRepository


class ProjectToolRegistry:
    """Build read-only tools that enforce the requesting user's role."""

    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    def build(
        self, role: str
    ) -> tuple[list[dict[str, Any]], dict[str, Callable[..., Any]]]:
        """Return OpenAI-style schemas and matching allowlisted handlers."""
        handlers = {
            "list_projects": lambda status=None: self.repository.list_projects(status, role),
            "get_project": lambda project: self.repository.find_project(project, role),
            "portfolio_summary": lambda: self.repository.portfolio_summary(role),
        }
        schemas = [
            {
                "type": "function",
                "name": "list_projects",
                "description": "List projects, optionally by lifecycle status.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": ["string", "null"],
                            "enum": ["active", "completed", "future", None],
                        }
                    },
                    "required": ["status"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "get_project",
                "description": "Get dates, progress, contacts, resources and milestones for one project.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {"project": {"type": "string"}},
                    "required": ["project"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "portfolio_summary",
                "description": "Get portfolio counts, values and delayed active project codes.",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        ]
        return schemas, handlers


def collect_sources(value: Any) -> set[str]:
    """Recursively extract evidence labels from tool output."""
    sources: set[str] = set()
    if isinstance(value, dict):
        sources.update(value.get("sources", []))
        for nested in value.values():
            sources.update(collect_sources(nested))
    elif isinstance(value, list):
        for item in value:
            sources.update(collect_sources(item))
    return sources

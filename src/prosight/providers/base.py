"""Shared provider interfaces and response types."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from ..observability import RequestTrace


ToolBundle = tuple[list[dict[str, Any]], dict[str, Callable[..., Any]]]


class ReasoningProvider(Protocol):
    """Contract implemented by every model-backed reasoning provider."""

    name: str
    model: str

    def answer(
        self, query: str, tools: ToolBundle, trace: RequestTrace
    ) -> dict[str, Any]:
        """Answer a query, invoking allowlisted tools when needed."""
        ...

"""Shared provider interfaces and response types."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from ..observability import RequestTrace


ToolBundle = tuple[list[dict[str, Any]], dict[str, Callable[..., Any]]]


class ModelClient(Protocol):
    """Small provider boundary; v2 intentionally activates one provider at a time."""

    name: str
    model: str

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        """Generate a non-streaming response through the active provider."""
        ...

    async def stream(self, *args: Any, **kwargs: Any) -> Any:
        """Stream a response through the active provider."""
        ...

    async def structured_output(self, *args: Any, **kwargs: Any) -> Any:
        """Request schema-constrained output from the active provider."""
        ...

    async def embed(self, *args: Any, **kwargs: Any) -> Any:
        """Create embeddings through the active provider."""
        ...

    def answer(self, query: str, tools: ToolBundle, trace: RequestTrace) -> dict[str, Any]:
        """Generate an answer using the configured provider."""
        ...


class ReasoningProvider(Protocol):
    """Contract implemented by every model-backed reasoning provider."""

    name: str
    model: str

    def answer(
        self, query: str, tools: ToolBundle, trace: RequestTrace
    ) -> dict[str, Any]:
        """Answer a query, invoking allowlisted tools when needed."""
        ...

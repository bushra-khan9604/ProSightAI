"""Writer Agent: the only specialist that creates user-facing responses."""

from __future__ import annotations

from typing import Any

from ..contracts import AgentAnswer, WriterInput


WRITER_INSTRUCTIONS = """You are the ProSight Writer Agent.
Answer only from the supplied database and RAG evidence. Never invent facts.
When evidence conflicts, use the fact from the document with the newest effective
reporting date and cite its filename and page. Mention older evidence only as
historical context. If evidence is insufficient, clearly say the information was
not found. Keep the response concise and useful to construction professionals."""


class WriterAgent:
    """Combine approved evidence packets without direct data access."""

    name = "Writer Agent"

    def fallback(self, writer_input: WriterInput) -> AgentAnswer:
        """Create deterministic answers for offline development and unit tests."""
        citations: list[str] = []
        sections: list[str] = []

        if writer_input.database:
            citations.extend(item.citation for item in writer_input.database.evidence)
            if writer_input.database.records:
                sections.append(writer_input.database.summary)
                for record in writer_input.database.records[:5]:
                    sections.append(
                        f"{record.get('code')}: {record.get('name')} — "
                        f"{record.get('status')}; actual progress "
                        f"{record.get('actual_progress', 'not available')}%."
                    )
            elif writer_input.database.summary:
                sections.append(writer_input.database.summary)

        if writer_input.rag:
            citations.extend(item.citation for item in writer_input.rag.evidence)
            sections.extend(item.text for item in writer_input.rag.evidence[:3])

        if not sections:
            sections.append("The requested information was not found in the available evidence.")

        return AgentAnswer(
            answer="\n\n".join(sections),
            citations=list(dict.fromkeys(citations)),
            agent_route=["writer"],
            mode="local",
        )

    @staticmethod
    def evidence_payload(writer_input: WriterInput) -> dict[str, Any]:
        """Serialize the typed evidence packet for the hosted Writer Agent."""
        return writer_input.model_dump(mode="json")

"""Low-latency deterministic orchestration and Writer-only model synthesis."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any, Callable

from ..config import get_settings
from ..contracts import AgentAnswer, OrchestrationPlan, WriterInput
from ..observability import RequestTrace
from ..repository import ProjectRepository
from .database_manager import DatabaseManagerAgent
from .rag_agent import RAGAgent
from .writer import WRITER_INSTRUCTIONS, WriterAgent


class MultiAgentOrchestrator:
    """Route deterministically, collect evidence concurrently, and invoke the Writer."""

    name = "Main Orchestrator Agent"

    def __init__(self, repository: ProjectRepository, rag_agent: RAGAgent | None = None):
        self.repository = repository
        self.database = DatabaseManagerAgent(repository)
        self.rag = rag_agent
        self.writer = WriterAgent()

    def plan(self, query: str, project_code: str | None = None) -> OrchestrationPlan:
        """Create a deterministic routing plan without an LLM round trip."""
        normalized = query.lower()
        planning = bool(re.search(r"\b(create|prepare|generate|build|draft|make|plan)\b", normalized)) and any(
            term in normalized for term in ("schedule", "budget", "resource", "measurement", "procurement", "kickoff", "kick off", "cash flow", "recovery plan", "project plan", "register"))
        analysis = any(term in normalized for term in ("analyze", "analyse", "earned value", "evm", "critical path", "mitigation", "resource conflict", "why is", "explain schedule risk", "cash-flow analysis", "historical benchmark", "compare with completed", "lessons learned"))
        if planning or analysis:
            agents = (["analyst"] if analysis else []) + (["planner"] if planning else []) + ["writer"]
            return OrchestrationPlan(intent="recovery" if planning and analysis else "planning" if planning else "analysis",
                                     agents=agents,project_code=project_code,steps=[f"Invoke {a}" for a in agents])
        write_terms = ("add ", "update ", "modify ", "delete ", "import ")
        rag_terms = ("document", "pdf", "report", "specification", "drawing", "clause")
        database_terms = (
            "project", "progress", "contact", "manpower", "equipment", "milestone",
            "contract", "schedule", "database", "invoice", "payment", "remittance",
            "aging", "risk profile", "workforce", "employee", "allocation",
            "manager", "engineer", "planned", "actual", "finish date", "start date",
        )
        if normalized.strip() in {"hi", "hello", "hey"}:
            intent, agents = "greeting", ["writer"]
        elif any(term in normalized for term in write_terms):
            intent, agents = "database_write", ["database_manager", "writer"]
        else:
            wants_db = any(term in normalized for term in database_terms)
            wants_rag = any(term in normalized for term in rag_terms) or (
                bool(project_code) and not wants_db
            )
            if wants_rag and wants_db:
                intent, agents = "combined", ["database_manager", "rag", "writer"]
            elif wants_rag:
                intent, agents = "rag_read", ["rag", "writer"]
            else:
                intent, agents = "database_read", ["database_manager", "writer"]
        return OrchestrationPlan(
            intent=intent,
            agents=agents,
            project_code=project_code,
            requires_write_approval=intent == "database_write",
            steps=[f"Invoke {agent}" for agent in agents],
        )

    def run(
        self,
        query: str,
        role: str,
        project_code: str | None,
        trace: RequestTrace,
        history: list[dict[str, str]] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Synchronous compatibility entry point for the CLI and existing callers."""
        return asyncio.run(self.run_async(
            query, role, project_code, trace, history, status_callback
        ))

    async def run_async(
        self,
        query: str,
        role: str,
        project_code: str | None,
        trace: RequestTrace,
        history: list[dict[str, str]] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Collect evidence concurrently and return one complete response."""
        plan = self._make_plan(query, project_code, trace)
        plan = await self._refine_plan(query, plan)
        writer_input, route = await self._collect_evidence(
            query, role, project_code, plan, trace, status_callback
        )
        self._emit_status(status_callback, "creating_response")
        settings = get_settings()
        provider = "local" if settings.ai_provider == "local" or not settings.openai_api_key else "openai"
        trace.event(
            "provider_selected", provider=provider,
            model=settings.openai_model if provider == "openai" else None, role=role,
        )
        if provider == "local":
            answer = self.writer.fallback(writer_input)
        else:
            try:
                answer = await self._write_openai(writer_input, route, history or [], trace)
            except Exception as exc:
                trace.event("fallback_activated", status="warning", error=type(exc).__name__)
                answer = self.writer.fallback(writer_input)
                answer.notice = "OpenAI was unavailable; a deterministic evidence response was used."
        answer.agent_route = route + ["writer"]
        for key, value in writer_input.specialist_metadata.items():
            if key in AgentAnswer.model_fields:
                setattr(answer, key, value)
        return answer.model_dump()

    async def stream(
        self,
        query: str,
        role: str,
        project_code: str | None,
        trace: RequestTrace,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yield safe progress, Writer text deltas, and one terminal response."""
        plan = self._make_plan(query, project_code, trace)
        plan = await self._refine_plan(query, plan)
        if any(agent in plan.agents for agent in ("analyst", "planner")):
            yield "status", {"state": "specialist", "label": "Calculating project controls and preparing validated results"}
        if any(agent in plan.agents for agent in ("database_manager", "rag")):
            yield "status", {"state": "checking_database", "label": "Checking database"}
        progress = asyncio.Queue()
        collection = asyncio.create_task(self._collect_evidence(query, role, project_code, plan, trace, progress.put_nowait))
        try:
            while not collection.done():
                try:
                    await asyncio.wait_for(asyncio.shield(collection), .25)
                except asyncio.TimeoutError:
                    pass
                while not progress.empty():
                    event = progress.get_nowait()
                    if isinstance(event, dict):
                        yield "status", event
            writer_input, route = await collection
        finally:
            if not collection.done():
                collection.cancel()
        yield "status", {"state": "creating_response", "label": "Creating response"}
        settings = get_settings()
        provider = "local" if settings.ai_provider == "local" or not settings.openai_api_key else "openai"
        trace.event(
            "provider_selected", provider=provider,
            model=settings.openai_model if provider == "openai" else None, role=role,
        )
        if provider == "local":
            answer = self.writer.fallback(writer_input)
            answer.agent_route = route + ["writer"]
            answer.time_to_first_token_ms = 0
            if answer.answer:
                yield "delta", {"text": answer.answer}
            yield "final", answer.model_dump()
            return

        emitted = False
        try:
            async for event_name, payload in self._stream_openai_writer(
                writer_input, route, history or [], trace
            ):
                if event_name == "delta":
                    emitted = True
                yield event_name, payload
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            trace.event("fallback_activated", status="warning", error=type(exc).__name__)
            if emitted:
                yield "error", {
                    "message": "The response was interrupted. Please retry.",
                    "partial": True,
                }
                return
            answer = self.writer.fallback(writer_input)
            answer.agent_route = route + ["writer"]
            answer.notice = "OpenAI was unavailable; a deterministic evidence response was used."
            answer.time_to_first_token_ms = 0
            if answer.answer:
                yield "delta", {"text": answer.answer}
            yield "final", answer.model_dump()

    def _make_plan(
        self, query: str, project_code: str | None, trace: RequestTrace
    ) -> OrchestrationPlan:
        started = time.perf_counter()
        plan = self.plan(query, project_code)
        trace.event(
            "orchestration_planned", agents=plan.agents, intent=plan.intent,
            component_duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return plan

    async def _refine_plan(self, query, plan):
        """Use a constrained classifier only for ambiguous planning/analysis phrasing."""
        if plan.intent in {'planning','analysis','recovery','database_write','greeting'}:
            return plan
        if not any(t in query.lower() for t in ('help me','what should','how can we','prepare','assess','evaluate','strategy')):
            return plan
        settings = get_settings()
        if settings.ai_provider == 'local' or not settings.openai_api_key:
            return plan
        from openai import AsyncOpenAI
        from ..contracts import SpecialistIntent
        try:
            async with AsyncOpenAI(api_key=settings.openai_api_key,timeout=20,max_retries=0) as client:
                response = await client.responses.parse(model=settings.openai_model,
                    input=[{'role':'system','content':'Classify the requested workflow only. ordinary retrieves facts/documents; analysis computes project performance; planning creates a proposed schedule/budget/register; recovery analyzes performance and drafts recovery. Never authorize writes. Choose clarify when the action is unresolved.'},{'role':'user','content':query}],text_format=SpecialistIntent)
            selected = response.output_parsed
            routes={'analysis':['analyst','writer'],'planning':['planner','writer'],'recovery':['analyst','planner','writer']}
            if selected and selected.workflow in routes:
                return OrchestrationPlan(intent=selected.workflow,agents=routes[selected.workflow],project_code=plan.project_code)
            if selected and selected.workflow == 'clarify':
                return OrchestrationPlan(intent='unsupported',agents=['writer'],project_code=plan.project_code,steps=[selected.clarification or 'Should I analyze existing performance or create a proposed plan?'])
        except Exception:
            pass
        return plan

    async def _collect_evidence(
        self,
        query: str,
        role: str,
        project_code: str | None,
        plan: OrchestrationPlan,
        trace: RequestTrace,
        status_callback: Callable[[str], None] | None = None,
    ) -> tuple[WriterInput, list[str]]:
        """Run independent specialist reads concurrently with ContextVar propagation."""
        if plan.intent == 'unsupported' and plan.steps:
            from ..contracts import DatabaseEvidence
            return self.writer.prepare_input(query,DatabaseEvidence(summary=plan.steps[0])),[]
        if any(agent in plan.agents for agent in ("analyst", "planner")):
            from ..controls.specialists import SpecialistService
            self._emit_status(status_callback, "analyzing_project")
            evidence, metadata = await SpecialistService(self.repository).run(query, project_code, role, "planner" in plan.agents, progress_callback=status_callback)
            packet = self.writer.prepare_input(query, evidence)
            packet.specialist_metadata = metadata
            return packet, [a for a in plan.agents if a != "writer"]
        self._emit_status(status_callback, "checking_database")
        evidence_started = time.perf_counter()

        async def read_database():
            started = time.perf_counter()
            evidence = await asyncio.to_thread(
                self.database.read, query, project_code, role
            )
            trace.event(
                "database_query_completed", agent="database_manager",
                result_size=len(evidence.records),
                component_duration_ms=round((time.perf_counter() - started) * 1000),
            )
            return evidence

        async def read_rag():
            started = time.perf_counter()
            evidence = await asyncio.to_thread(self.rag.retrieve, query, project_code)
            trace.event(
                "rag_retrieval_completed", agent="rag",
                result_size=len(evidence.evidence),
                component_duration_ms=round((time.perf_counter() - started) * 1000),
            )
            return evidence

        names: list[str] = []
        tasks = []
        if "database_manager" in plan.agents:
            names.append("database_manager")
            tasks.append(read_database())
        if "rag" in plan.agents and project_code and self.rag:
            names.append("rag")
            tasks.append(read_rag())
        results = await asyncio.gather(*tasks) if tasks else []
        collected = dict(zip(names, results))
        trace.event(
            "evidence_collected", agents=names,
            component_duration_ms=round((time.perf_counter() - evidence_started) * 1000),
        )
        writer_input = self.writer.prepare_input(
            query,
            collected.get("database_manager"),
            collected.get("rag"),
        )
        return writer_input, names

    @staticmethod
    def _writer_messages(
        writer_input: WriterInput, history: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        evidence = json.dumps(
            WriterAgent.evidence_payload(writer_input),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        current = (
            "Answer the current question using only the authorized evidence packet below. "
            "Conversation history is for reference resolution only.\n\n"
            f"AUTHORIZED_EVIDENCE={evidence}"
        )
        return [*history, {"role": "user", "content": current}]

    @staticmethod
    def _writer_agent():
        from agents import Agent
        from agents.model_settings import ModelSettings
        from openai.types.shared import Reasoning

        settings = get_settings()
        return Agent(
            name="Writer Agent",
            instructions=WRITER_INSTRUCTIONS,
            model=settings.openai_model,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort=settings.writer_reasoning)
            ),
            tools=[],
        )

    async def _write_openai(
        self,
        writer_input: WriterInput,
        route: list[str],
        history: list[dict[str, str]],
        trace: RequestTrace,
    ) -> AgentAnswer:
        from agents import Runner

        settings = get_settings()
        started = time.perf_counter()
        trace.event("provider_request_started", provider="openai", model=settings.openai_model)
        result = await Runner.run(
            self._writer_agent(), self._writer_messages(writer_input, history)
        )
        text = str(result.final_output)
        trace.event(
            "provider_response_received", provider="openai", result_size=len(text),
            component_duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return self._answer(text, route, writer_input)

    async def _stream_openai_writer(
        self,
        writer_input: WriterInput,
        route: list[str],
        history: list[dict[str, str]],
        trace: RequestTrace,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        from agents import Runner
        from openai.types.responses import ResponseTextDeltaEvent

        settings = get_settings()
        started = time.perf_counter()
        first_token_ms: int | None = None
        parts: list[str] = []
        trace.event("provider_request_started", provider="openai", model=settings.openai_model)
        result = Runner.run_streamed(
            self._writer_agent(), self._writer_messages(writer_input, history)
        )
        try:
            async for event in result.stream_events():
                if (
                    event.type == "raw_response_event"
                    and isinstance(event.data, ResponseTextDeltaEvent)
                    and event.data.delta
                ):
                    if first_token_ms is None:
                        first_token_ms = round((time.perf_counter() - started) * 1000)
                        trace.event("writer_first_token", time_to_first_token_ms=first_token_ms)
                    parts.append(event.data.delta)
                    yield "delta", {"text": event.data.delta}
        except asyncio.CancelledError:
            result.cancel()
            raise
        text = "".join(parts)
        final_text = str(result.final_output or "")
        if final_text.startswith(text) and len(final_text) > len(text):
            remainder = final_text[len(text):]
            parts.append(remainder)
            text = final_text
            yield "delta", {"text": remainder}
        elif not text:
            text = final_text
            if text:
                yield "delta", {"text": text}
        trace.event(
            "provider_response_received", provider="openai", result_size=len(text),
            component_duration_ms=round((time.perf_counter() - started) * 1000),
            time_to_first_token_ms=first_token_ms,
        )
        answer = self._answer(text, route, writer_input)
        answer.time_to_first_token_ms = first_token_ms
        yield "final", answer.model_dump()

    @staticmethod
    def _answer(text: str, route: list[str], writer_input: WriterInput | None = None) -> AgentAnswer:
        allowed = []
        if writer_input:
            for packet in (writer_input.database, writer_input.rag):
                if packet:
                    allowed.extend(item.citation for item in packet.evidence)
        citations = list(dict.fromkeys(c for c in allowed if c in text))
        return AgentAnswer(
            answer=text,
            citations=citations,
            agent_route=route + ["writer"],
            mode="openai",
            **({k:v for k,v in writer_input.specialist_metadata.items() if k in AgentAnswer.model_fields} if writer_input else {}),
        )

    @staticmethod
    def _emit_status(callback: Callable[[str], None] | None, state: str) -> None:
        if callback:
            try:
                callback(state)
            except Exception:
                pass

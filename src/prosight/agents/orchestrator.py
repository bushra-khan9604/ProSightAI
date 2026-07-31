"""Main Orchestrator Agent using centralized manager-style delegation."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from ..config import get_settings
from ..contracts import AgentAnswer, OrchestrationPlan, WriterInput
from ..observability import RequestTrace
from ..repository import ProjectRepository
from .database_manager import DatabaseManagerAgent
from .rag_agent import RAGAgent
from .writer import WRITER_INSTRUCTIONS, WriterAgent, create_table as format_table


ORCHESTRATOR_INSTRUCTIONS = """You are the ProSight Main Orchestrator Agent.
You own the conversation and may call specialists only through the tools provided.
For database facts call database_manager. For project-document questions call rag_agent.
For combined questions call both. Always call writer_agent last with all gathered evidence,
and return the Writer Agent output exactly. Specialists never communicate directly.
Never expose chain-of-thought. Database mutations must only create a pending preview and
must never claim execution without explicit Admin approval."""


class MultiAgentOrchestrator:
    """Plan requests, invoke isolated specialists, and expose a safe agent route."""

    name = "Main Orchestrator Agent"

    def __init__(self, repository: ProjectRepository, rag_agent: RAGAgent | None = None):
        self.repository = repository
        self.database = DatabaseManagerAgent(repository)
        self.rag = rag_agent
        self.writer = WriterAgent()

    def plan(self, query: str, project_code: str | None = None) -> OrchestrationPlan:
        """Create a deterministic routing plan before any LLM execution."""
        normalized = query.lower()
        write_terms = ("add ", "update ", "modify ", "delete ", "import ")
        rag_terms = ("document", "pdf", "report", "specification", "drawing", "clause")
        database_terms = (
            "project", "progress", "contact", "manpower", "equipment", "milestone",
            "contract", "schedule", "database", "invoice", "payment", "remittance",
            "aging", "risk profile", "workforce", "employee", "allocation",
        )
        if normalized.strip() in {"hi", "hello", "hey"}:
            intent, agents = "greeting", ["writer"]
        elif any(term in normalized for term in write_terms):
            intent, agents = "database_write", ["database_manager", "writer"]
        else:
            wants_rag = any(term in normalized for term in rag_terms)
            wants_db = any(term in normalized for term in database_terms)
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
        """Execute with OpenAI when configured, or deterministic local test routing."""
        plan = self.plan(query, project_code)
        trace.event("orchestration_planned", agents=plan.agents, intent=plan.intent)
        settings = get_settings()
        if settings.ai_provider == "local" or not settings.openai_api_key:
            return self._run_local(query, role, project_code, plan, trace, status_callback).model_dump()
        try:
            return self._run_openai(
                query, role, project_code, plan, trace, history or [], status_callback
            ).model_dump()
        except Exception as exc:
            trace.event("fallback_activated", status="warning", error=type(exc).__name__)
            answer = self._run_local(query, role, project_code, plan, trace, status_callback)
            answer.notice = "OpenAI was unavailable; a deterministic evidence response was used."
            return answer.model_dump()

    def _run_local(
        self,
        query: str,
        role: str,
        project_code: str | None,
        plan: OrchestrationPlan,
        trace: RequestTrace,
        status_callback: Callable[[str], None] | None = None,
    ) -> AgentAnswer:
        """Run the same specialist boundaries without network calls."""
        database = None
        rag = None
        route: list[str] = []
        if "database_manager" in plan.agents:
            self._emit_status(status_callback, "checking_database")
            database = self.database.read(query, project_code, role)
            route.append("database_manager")
            trace.event("database_query_completed", agent="database_manager",
                        result_size=len(database.records))
        if "rag" in plan.agents and project_code and self.rag:
            self._emit_status(status_callback, "checking_database")
            rag = self.rag.retrieve(query, project_code)
            route.append("rag")
            trace.event("rag_retrieval_completed", agent="rag",
                        result_size=len(rag.evidence))
        trace.event("provider_selected", provider="local", model=None, role=role)
        self._emit_status(status_callback, "creating_response")
        answer = self.writer.fallback(
            WriterInput(query=query, database=database, rag=rag)
        )
        answer.agent_route = route + ["writer"]
        return answer

    def _run_openai(
        self,
        query: str,
        role: str,
        project_code: str | None,
        plan: OrchestrationPlan,
        trace: RequestTrace,
        history: list[dict[str, str]],
        status_callback: Callable[[str], None] | None = None,
    ) -> AgentAnswer:
        """Use the OpenAI Agents SDK while keeping specialist data access isolated."""
        from agents import Agent, Runner, function_tool

        route: list[str] = []

        @function_tool
        def database_manager(user_query: str) -> str:
            """Read authorized relational project evidence."""
            self._emit_status(status_callback, "checking_database")
            evidence = self.database.read(user_query, project_code, role)
            route.append("database_manager")
            trace.event("tool_completed", tool_name="database_manager",
                        result_size=len(evidence.records))
            self._emit_status(status_callback, "creating_response")
            return evidence.model_dump_json()

        @function_tool
        def rag_agent(user_query: str) -> str:
            """Retrieve project-scoped PDF evidence."""
            self._emit_status(status_callback, "checking_database")
            if not project_code or not self.rag:
                self._emit_status(status_callback, "creating_response")
                return json.dumps({"evidence": [], "notice": "No project selected"})
            evidence = self.rag.retrieve(user_query, project_code)
            route.append("rag")
            trace.event("tool_completed", tool_name="rag",
                        result_size=len(evidence.evidence))
            self._emit_status(status_callback, "creating_response")
            return evidence.model_dump_json()

        @function_tool
        def create_table(
            columns: list[str],
            rows: list[list[str]],
            title: str = "",
            omitted_count: int = 0,
        ) -> str:
            """Create a safe Markdown table solely from evidence supplied to the Writer."""
            return format_table(columns, rows, title, omitted_count)

        writer_agent = Agent(
            name="Writer Agent",
            instructions=WRITER_INSTRUCTIONS,
            model=get_settings().openai_model,
            tools=[create_table],
        )
        manager = Agent(
            name=self.name,
            instructions=ORCHESTRATOR_INSTRUCTIONS,
            model=get_settings().openai_model,
            tools=[database_manager, rag_agent, writer_agent.as_tool(
                tool_name="writer_agent",
                tool_description="Create the final evidence-grounded response.",
            )],
        )
        trace.event("provider_request_started", provider="openai",
                    model=get_settings().openai_model)
        if not any(agent in plan.agents for agent in ("database_manager", "rag")):
            self._emit_status(status_callback, "creating_response")
        result = Runner.run_sync(
            manager,
            [*history, {"role": "user", "content": query}],
        )
        text = str(result.final_output)
        citations = list(dict.fromkeys(
            re.findall(r"[\w .()_-]+\.pdf, page \d+", text, flags=re.IGNORECASE)
        ))
        trace.event("provider_response_received", provider="openai",
                    result_size=len(text))
        return AgentAnswer(
            answer=text,
            citations=citations,
            agent_route=route + ["writer"],
            mode="openai",
        )

    @staticmethod
    def _emit_status(callback: Callable[[str], None] | None, state: str) -> None:
        """Report bounded UI progress without allowing observers to break a query."""
        if callback:
            try:
                callback(state)
            except Exception:
                pass

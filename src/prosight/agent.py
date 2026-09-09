"""ProSight orchestration with OpenAI and deterministic local test modes."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .config import get_settings
from .observability import RequestTrace, sanitize
from .providers import OpenAIProvider
from .repository import ProjectRepository
from .tools.project_tools import ProjectToolRegistry


class ProSightAgent:
    """Project Insights Agent coordinating OpenAI and local test actions."""

    def __init__(self, repository: ProjectRepository | None = None):
        """Create an agent over the supplied repository or the default database."""
        from .db import create_repository
        self.repository = repository or create_repository()
        self.tools = ProjectToolRegistry(self.repository)

    def _project_from_query(self, query: str, role: str) -> dict[str, Any] | None:
        """Resolve a project from a code, full name, or fuzzy name fragment."""
        normalized = re.sub(r"[^a-z0-9]+", " ", query.lower())
        query_words = {w for w in normalized.split() if len(w) > 2}
        best: tuple[float, dict[str, Any] | None] = (0.0, None)
        for project in self.repository.list_projects(user_role=role):
            code = project["code"].lower()
            name = re.sub(r"[^a-z0-9]+", " ", project["name"].lower())
            if code in query.lower() or name in normalized:
                return project
            name_words = {w for w in name.split() if len(w) > 2}
            # Token overlap handles short names; sequence similarity catches small typos.
            overlap = len(query_words & name_words) / max(len(name_words), 1)
            similarity = SequenceMatcher(None, normalized, name).ratio() * 0.7
            score = max(overlap, similarity)
            if score > best[0]:
                best = (score, project)
        return best[1] if best[0] >= 0.32 else None

    @staticmethod
    def _money(value: float) -> str:
        """Format a USD value for human-readable answers."""
        return f"${value:,.0f}"

    @staticmethod
    def _sources(projects: list[dict[str, Any]]) -> list[str]:
        """Return a stable, de-duplicated source list for multiple projects."""
        return sorted({source for project in projects for source in project["sources"]})

    @staticmethod
    def _contact_roles(query: str) -> list[str]:
        """Map natural-language contact phrases to canonical project roles."""
        mappings = {
            "project manager": "Project Manager",
            "project engineer": "Project Engineer",
            "planning engineer": "Planning Engineer",
            "site point": "Site Point of Contact",
            "site contact": "Site Point of Contact",
            "client point": "Client Point of Contact",
            "client contact": "Client Point of Contact",
            "bid manager": "Bid Manager",
        }
        return [role for phrase, role in mappings.items() if phrase in query]

    def _overview(self, project: dict[str, Any]) -> str:
        """Build a concise, grounded overview for one project."""
        direction = "behind" if project["variance_pct"] < 0 else "ahead of"
        return (
            f"**{project['name']} ({project['code']})** is {project['status']}.\n\n"
            f"- **Contract value:** {self._money(project['contract_value_usd'])}\n"
            f"- **Schedule:** {project['planned_start']} to {project['planned_finish']}; "
            f"revised finish {project['revised_finish'] or 'not set'} "
            f"({project['delay_days']} delay days)\n"
            f"- **Progress at {project['reporting_date']}:** baseline "
            f"{project['baseline_progress']}%, revised {project['revised_progress']}%, "
            f"actual {project['actual_progress']}%\n"
            f"- **Performance:** {abs(project['variance_pct']):.1f} percentage points "
            f"{direction} the revised plan"
        )

    def ask_local(
        self,
        query: str,
        user_role: str = "employee",
        trace: RequestTrace | None = None,
    ) -> dict[str, Any]:
        """Answer common project intents without calling a language model."""
        trace = trace or RequestTrace()
        q = re.sub(r"\s+", " ", query.lower().strip())
        status = next((s for s in ("active", "completed", "future") if s in q), None)
        if "ongoing" in q:
            status = "active"
        all_projects = self.repository.list_projects(user_role=user_role)
        candidates = [p for p in all_projects if not status or p["status"] == status]
        project = self._project_from_query(query, user_role)
        citations: list[str] = []

        # Project-specific intents take precedence over portfolio-level intents.
        if project:
            citations = project["sources"]
            requested_roles = self._contact_roles(q)
            contact_intent = requested_roles or any(
                word in q for word in ("who", "contact", "manager", "engineer", "phone", "email", "mobile")
            )
            if contact_intent:
                contacts = [
                    p for p in project["contacts"]
                    if not requested_roles or p["project_role"] in requested_roles
                ]
                if contacts:
                    answer = f"### Contacts for {project['name']}\n" + "\n".join(
                        f"- **{p['project_role']}:** {p['name']} — {p['email']}, {p['mobile']}"
                        for p in contacts
                    )
                else:
                    roles = ", ".join(p["project_role"] for p in project["contacts"])
                    answer = f"I could not find that role for **{project['name']}**. Available roles: {roles}."
            elif any(phrase in q for phrase in ("activity", "activities", "working on", "work happening")):
                answer = f"### Current activities — {project['name']}\n" + "\n".join(
                    f"- {item}" for item in project["activities"]
                ) + f"\n\n*Reporting date: {project['reporting_date']}*"
            elif any(word in q for word in ("manpower", "workforce", "labor", "labour", "workers")):
                total = sum(item["count"] for item in project["manpower"])
                answer = f"### Manpower — {project['name']}\n" + "\n".join(
                    f"- **{item['designation']}:** {item['count']}" for item in project["manpower"]
                ) + f"\n\n**Total listed manpower: {total}**"
            elif any(word in q for word in ("equipment", "machinery", "plant")):
                answer = f"### Equipment — {project['name']}\n" + "\n".join(
                    f"- **{item['type']}:** {item['count']}" for item in project["equipment"]
                )
            elif any(word in q for word in ("milestone", "milestones", "handover")):
                answer = f"### Milestones — {project['name']}\n" + "\n".join(
                    f"- **{item['name']}:** {item['status']}" for item in project["milestones"]
                )
            elif any(phrase in q for phrase in ("manhour", "man-hour", "hours worked")):
                answer = f"**{project['name']} has recorded {project['total_manhours']:,} total man-hours.**"
            else:
                answer = self._overview(project)
        elif any(phrase in q for phrase in ("most delayed", "highest delay", "maximum delay", "worst delay")):
            delayed = [p for p in candidates if p["delay_days"] > 0]
            if delayed:
                worst = max(delayed, key=lambda p: p["delay_days"])
                answer = (
                    f"**{worst['name']} ({worst['code']}) has the largest schedule delay: "
                    f"{worst['delay_days']} days.** Revised finish is {worst['revised_finish']}; "
                    f"planned finish was {worst['planned_finish']}."
                )
                citations = worst["sources"]
            else:
                answer = "No delayed projects were found for that lifecycle filter."
        elif any(phrase in q for phrase in (
            "behind schedule", "behind plan", "at risk", "delayed projects", "projects delayed"
        )):
            attention = [p for p in candidates if p["delay_days"] > 0 or p["variance_pct"] < 0]
            answer = "### Projects requiring attention\n" + (
                "\n".join(
                    f"- **{p['code']} — {p['name']}:** {p['delay_days']} delay days; "
                    f"progress variance {p['variance_pct']:+.1f} pp"
                    for p in sorted(attention, key=lambda x: (x["delay_days"], -x["variance_pct"]), reverse=True)
                ) if attention else "No projects currently meet that condition."
            )
            citations = self._sources(attention)
        elif any(term in q for term in ("compare", "comparison", "versus", " vs ")):
            answer = "### Project comparison\n" + "\n".join(
                f"- **{p['code']} — {p['name']}:** {p['actual_progress']}% actual, "
                f"{p['variance_pct']:+.1f} pp variance, {p['delay_days']} delay days, "
                f"{self._money(p['contract_value_usd'])}"
                for p in candidates
            )
            citations = self._sources(candidates)
        elif any(term in q for term in ("summary", "portfolio", "total", "how many")):
            summary = self.repository.portfolio_summary(user_role)
            answer = (
                "### Portfolio summary\n"
                f"- **Projects:** {summary['project_count']} projects total — "
                f"{summary['counts']['active']} active, {summary['counts']['completed']} completed, "
                f"{summary['counts']['future']} future\n"
                f"- **Active contract value:** {self._money(summary['contract_value_usd']['active'])}\n"
                f"- **Delayed active projects:** "
                f"{', '.join(summary['delayed_active_projects']) or 'none'}"
            )
            citations = ["Portfolio database snapshot"]
        else:
            label = status or "all"
            answer = f"### {label.title()} projects\n" + "\n".join(
                f"- **{p['code']}: {p['name']}** — {self._money(p['contract_value_usd'])}; "
                f"{p['actual_progress']}% actual progress"
                for p in candidates
            )
            citations = self._sources(candidates)
        result = {
            "answer": answer,
            "citations": citations,
            "mode": "local",
            "notice": "Using local data mode. Configure OPENAI_API_KEY for full AI reasoning.",
        }
        trace.event(
            "provider_response_received",
            provider="local",
            status="success",
            response_preview=sanitize(answer),
            citation_count=len(citations),
        )
        return result

    def _tools(self, role: str):
        """Return role-aware schemas and handlers for compatibility with callers."""
        return self.tools.build(role)

    def ask_openai(
        self,
        query: str,
        user_role: str = "employee",
        trace: RequestTrace | None = None,
    ) -> dict[str, Any]:
        """Delegate an application query to GPT-5.6 Luna through OpenAI."""
        trace = trace or RequestTrace()
        settings = get_settings()
        provider = OpenAIProvider(settings.openai_api_key, settings.openai_model)
        return provider.answer(query, self._tools(user_role), trace)

    def ask(
        self,
        query: str,
        user_role: str = "employee",
        trace: RequestTrace | None = None,
    ) -> dict[str, Any]:
        """Select a provider from environment settings and answer the query."""
        trace = trace or RequestTrace()
        settings = get_settings()
        provider = settings.ai_provider
        if provider not in {"auto", "local", "openai"}:
            raise ValueError("PROSIGHT_AI_PROVIDER must be auto, local, or openai")
        # The web app uses GPT-5.6 Luna when a key exists. Tests explicitly force local.
        if provider == "auto":
            provider = "openai" if settings.openai_api_key else "local"
        model = settings.openai_model if provider == "openai" else None
        trace.event(
            "provider_selected",
            provider=provider,
            model=model,
            role=user_role,
        )
        trace.event("provider_request_started", provider=provider, model=model)
        if provider == "openai":
            result = self.ask_openai(query, user_role, trace)
        else:
            result = self.ask_local(query, user_role, trace)
        trace.event(
            "response_generated",
            provider=result["mode"],
            status="success",
            response_preview=sanitize(result["answer"]),
            citation_count=len(result.get("citations", [])),
        )
        return result

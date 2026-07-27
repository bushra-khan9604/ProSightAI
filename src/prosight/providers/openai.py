"""OpenAI Responses API provider using GPT-5.6 Luna by default."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from ..observability import RequestTrace
from ..prompts import PROJECT_INSIGHTS_SYSTEM_PROMPT
from .base import ToolBundle


class OpenAIProvider:
    """Run the Project Insights Agent through OpenAI function calling."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-5.6-luna"):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.model = model

    def answer(
        self, query: str, tools: ToolBundle, trace: RequestTrace
    ) -> dict[str, Any]:
        """Execute a bounded Responses API tool loop and return grounded text."""
        schemas, handlers = tools
        body: dict[str, Any] = {
            "model": self.model,
            "instructions": PROJECT_INSIGHTS_SYSTEM_PROMPT,
            "input": query,
            "tools": schemas,
        }
        for _ in range(6):
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(body).encode(),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read())
            trace.event(
                "provider_response_received",
                provider=self.name,
                model=self.model,
                status="success",
                output_items=len(result.get("output", [])),
            )
            calls = [item for item in result["output"] if item["type"] == "function_call"]
            if not calls:
                text = "".join(
                    part.get("text", "")
                    for item in result["output"]
                    if item["type"] == "message"
                    for part in item.get("content", [])
                    if part["type"] == "output_text"
                )
                return {"answer": text, "citations": [], "mode": self.name, "notice": None}
            outputs = []
            for call in calls:
                name = call["name"]
                trace.event("tool_requested", provider=self.name, tool_name=name)
                started = trace.duration_ms
                output = handlers[name](**json.loads(call["arguments"]))
                trace.event(
                    "tool_completed",
                    provider=self.name,
                    tool_name=name,
                    status="success",
                    tool_duration_ms=trace.duration_ms - started,
                    result_size=len(json.dumps(output, default=str)),
                )
                outputs.append({
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": json.dumps(output),
                })
            body = {
                "model": self.model,
                "instructions": PROJECT_INSIGHTS_SYSTEM_PROMPT,
                "previous_response_id": result["id"],
                "input": outputs,
                "tools": schemas,
            }
        raise RuntimeError("OpenAI tool-call limit exceeded")

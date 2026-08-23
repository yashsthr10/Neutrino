"""Bounded read-only subagent for agent.task."""

from __future__ import annotations

import json
from typing import Any

from src.inference.adapters.tool_adapter import tool_engine_schemas_to_specs
from src.inference.models.request import InferenceRequest, Message
from src.inference.stream_accumulator import accumulate_stream
from src.tool_engine.engine import ToolEngine
from src.tool_engine.models import ToolRequest

_READ_ONLY_PREFIXES = ("rna.", "context.")
_FORBIDDEN = frozenset(
    {
        "executor.apply",
        "executor.run",
        "terminal.run",
        "git.commit",
        "git.undo",
    }
)

_MAX_SUBAGENT_STEPS = 5


def run_subagent(
    *,
    inference: Any,
    tool_engine: ToolEngine,
    prompt: str,
    scope: str | None,
    execution_context: Any | None,
) -> dict[str, Any]:
    """Execute a short read-only tool loop; return compact summary dict."""
    task = prompt.strip()
    if scope:
        task = f"{task}\nScope: {scope}"
    messages: list[Message] = [
        Message(
            role="user",
            content=(
                "You are a read-only exploration subagent. Use tools to gather evidence, "
                "then reply with a concise markdown summary. Do not edit files or run shell."
            ),
        ),
        Message(role="user", content=task),
    ]
    tools_used: list[str] = []
    final_text = ""

    read_only_schemas = [
        s
        for s in tool_engine.schemas_for_state("AGENT")
        if any(s["name"].startswith(p) for p in _READ_ONLY_PREFIXES) and s["name"] not in _FORBIDDEN
    ]
    tool_specs = tool_engine_schemas_to_specs(read_only_schemas)

    for _ in range(_MAX_SUBAGENT_STEPS):
        response = accumulate_stream(
            inference.stream(
                InferenceRequest(
                    messages=tuple(messages),
                    tools=tool_specs,
                    tool_choice="auto" if tool_specs else None,
                )
            )
        )
        if response.content:
            final_text = response.content
        if not response.tool_calls:
            break
        messages.append(
            Message(role="assistant", content=response.content, tool_calls=response.tool_calls)
        )
        for tc in response.tool_calls:
            if tc.name in _FORBIDDEN or not tc.name.startswith(_READ_ONLY_PREFIXES):
                result_payload = {
                    "success": False,
                    "errors": ["forbidden in subagent"],
                }
            else:
                tools_used.append(tc.name)
                try:
                    args = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                result = tool_engine.invoke(
                    ToolRequest(name=tc.name, arguments=args, execution_context=execution_context),
                    state="AGENT",
                )
                result_payload = result.to_dict()
            messages.append(
                Message(
                    role="tool",
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=json.dumps(result_payload, default=str),
                )
            )

    return {
        "summary": (final_text or "").strip() or "(no summary produced)",
        "tools_used": list(dict.fromkeys(tools_used)),
        "steps": len(tools_used),
    }

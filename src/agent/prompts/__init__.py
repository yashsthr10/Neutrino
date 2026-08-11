"""Agent prompts — L1–L6 Claude Code–style layered compiler.

Layers:
  L1 core identity (``layers.core``)
  L2 capability contracts from ToolSpecs (``layers.capabilities``)
  L3 environment (``layers.environment``)
  L4 task / working set (``layers.task_context``)
  L5 soft agent state (``layers.agent_state``)
  L6 dynamic reminders (``src.agent.reminders``, injected as user messages)
"""

from __future__ import annotations

from src.agent.prompts.compiler import (
    DYNAMIC_BOUNDARY,
    CompiledPrompt,
    PromptInputs,
    compile_system_prompt,
    format_reminders_message,
)
from src.agent.prompts.system import build_system_prompt, format_execution_snapshot

__all__ = [
    "DYNAMIC_BOUNDARY",
    "CompiledPrompt",
    "PromptInputs",
    "build_system_prompt",
    "compile_system_prompt",
    "format_execution_snapshot",
    "format_reminders_message",
]

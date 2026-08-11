"""Recover usable tool calls from provider ``failed_generation`` dumps.

Some models (notably Qwen on Groq) emit XML-ish tool markup in the assistant
text instead of native function-calling. Groq then returns HTTP 400
``tool_use_failed`` with the bad text in ``failed_generation``.

We try to salvage complete calls; incomplete / truncated ones are left alone so
the agent loop can ask the model to retry correctly.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src.inference.errors import extract_failed_generation, is_tool_use_failed_message
from src.inference.models.request import ToolCall

__all__ = [
    "extract_failed_generation",
    "is_tool_use_failed",
    "salvage_tool_calls",
    "repair_guidance",
]

# Groq / Qwen-style:
#   <tool_call>
#   <function=executor.apply>
#   <parameter=patch>
#   ...value...
#   </parameter>
#   </function>
#   </tool_call>
_FUNCTION_RE = re.compile(
    r"<function\s*=\s*(?P<name>[A-Za-z0-9_.\-]+)>(?P<body>.*?)</function>",
    re.DOTALL | re.IGNORECASE,
)
_PARAM_RE = re.compile(
    r"<parameter\s*=\s*(?P<key>[A-Za-z0-9_.\-]+)>\s*(?P<value>.*?)\s*</parameter>",
    re.DOTALL | re.IGNORECASE,
)
# Loose form when the model never closed tags (common on truncation):
_LOOSE_FUNCTION_RE = re.compile(
    r"<function\s*=\s*(?P<name>[A-Za-z0-9_.\-]+)>\s*"
    r"(?:<parameter\s*=\s*(?P<key>[A-Za-z0-9_.\-]+)>\s*(?P<value>.*))",
    re.DOTALL | re.IGNORECASE,
)


def is_tool_use_failed(exc: BaseException | str) -> bool:
    return is_tool_use_failed_message(str(exc))


def salvage_tool_calls(failed_generation: str) -> tuple[ToolCall, ...]:
    """Parse XML-style tool markup into ToolCalls when the call looks complete."""
    if not failed_generation or not failed_generation.strip():
        return ()

    calls: list[ToolCall] = []
    for match in _FUNCTION_RE.finditer(failed_generation):
        name = match.group("name").strip()
        body = match.group("body")
        args = _params_to_args(body)
        if not name or not args:
            continue
        if not _args_look_complete(name, args):
            continue
        calls.append(
            ToolCall(
                id=f"repaired-{len(calls) + 1}",
                name=name,
                arguments=json.dumps(args),
            )
        )

    if calls:
        return tuple(calls)

    # Truncated single-parameter form — only accept if patch/content is closed.
    loose = _LOOSE_FUNCTION_RE.search(failed_generation)
    if loose is None:
        return ()
    name = (loose.group("name") or "").strip()
    key = (loose.group("key") or "").strip()
    value = (loose.group("value") or "").strip()
    # Strip trailing half-tags
    value = re.sub(r"</?(parameter|function|tool_call)[^>]*$", "", value, flags=re.I).rstrip()
    if not name or not key or not value:
        return ()
    args = {key: value}
    if not _args_look_complete(name, args):
        return ()
    return (ToolCall(id="repaired-1", name=name, arguments=json.dumps(args)),)


def repair_guidance(*, salvaged: bool, failed_generation: str | None) -> str:
    """User-turn guidance fed back into the conversation after tool_use_failed."""
    size_hint = ""
    if failed_generation and len(failed_generation) > 4000:
        size_hint = (
            " Your previous attempt was very large and likely truncated. "
            "Prefer smaller `executor.apply` patches (scaffold first, then fill), "
            "or split CSS/JS into separate files."
        )
    if salvaged:
        return (
            "Your previous tool call used invalid markup and was repaired by the runtime. "
            "Continue using the provider's native function-calling API only "
            "(never emit `<tool_call>` / `<function=` XML)." + size_hint
        )
    return (
        "Your previous response was rejected by the provider (`tool_use_failed`). "
        "Do NOT emit XML like `<tool_call>` or `<function=...>`. "
        "Call tools only via the native tool/function-calling interface supplied "
        "in this request. Keep `executor.apply` patches modest in size; for a large "
        "landing page, create a small scaffold first, then update in follow-up applies." + size_hint
    )


def _params_to_args(body: str) -> dict[str, Any]:
    args: dict[str, Any] = {}
    for match in _PARAM_RE.finditer(body):
        key = match.group("key").strip()
        value = match.group("value")
        # Preserve patch text as-is (including leading newlines)
        args[key] = value if key == "patch" else value.strip()
    return args


def _args_look_complete(name: str, args: dict[str, Any]) -> bool:
    if name == "executor.apply":
        patch = str(args.get("patch") or "")
        if not patch.strip():
            return False
        # Require a closed patch block so we never write truncated HTML.
        if "*** Begin Patch" in patch and "*** End Patch" not in patch:
            return False
        if "<<<<<<< SEARCH" in patch and ">>>>>>> REPLACE" not in patch:
            return False
        return True
    # Other tools: require at least one non-empty arg
    return any(str(v).strip() for v in args.values())

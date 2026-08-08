"""Salvage / guidance for Groq tool_use_failed dumps."""

from __future__ import annotations

import json

from src.agent.tool_call_repair import (
    extract_failed_generation,
    is_tool_use_failed,
    repair_guidance,
    salvage_tool_calls,
)
from src.inference.errors import ToolUseFailed


def test_is_tool_use_failed_detects_groq_code() -> None:
    assert is_tool_use_failed("Error code: 400 - tool_use_failed")
    assert is_tool_use_failed("Failed to call a function. Please adjust your prompt.")
    assert not is_tool_use_failed("connection reset")


def test_extract_failed_generation_from_tool_use_failed() -> None:
    exc = ToolUseFailed("boom", failed_generation="<function=rna.read_file>")
    assert extract_failed_generation(exc) == "<function=rna.read_file>"


def test_extract_failed_generation_from_message_repr() -> None:
    msg = (
        "Error code: 400 - {'error': {'message': \"Failed to call a function. "
        "Please adjust your prompt. See 'failed_generation' for more details.\", "
        "'type': 'invalid_request_error', 'code': 'tool_use_failed', "
        "'failed_generation': 'hello\\n<tool_call>\\n'}}"
    )
    fg = extract_failed_generation(msg)
    assert fg is not None
    assert "<tool_call>" in fg
    assert fg != "invalid_request_error"


def test_salvage_complete_xml_tool_call() -> None:
    dump = """
I'll write the file.
<tool_call>
<function=executor.apply>
<parameter=format>
patch
</parameter>
<parameter=patch>
*** Begin Patch
*** Add File: index.html
+<!DOCTYPE html>
+<html><body>hi</body></html>
*** End Patch
</parameter>
</function>
</tool_call>
"""
    calls = salvage_tool_calls(dump)
    assert len(calls) == 1
    assert calls[0].name == "executor.apply"
    args = json.loads(calls[0].arguments)
    assert args["format"] == "patch"
    assert "*** End Patch" in args["patch"]
    assert "index.html" in args["patch"]


def test_salvage_rejects_truncated_patch() -> None:
    dump = """
<function=executor.apply>
<parameter=patch>
*** Begin Patch
*** Add File: index.html
+<!DOCTYPE html>
+<html>
"""
    assert salvage_tool_calls(dump) == ()


def test_repair_guidance_mentions_size_when_large() -> None:
    text = repair_guidance(salvaged=False, failed_generation="x" * 5000)
    assert "tool_use_failed" in text
    assert "truncated" in text.lower() or "smaller" in text.lower()

"""Classifier unit tests."""

from __future__ import annotations

from src.agent.classifier import classify
from src.inference.models.request import ToolCall
from src.inference.models.response import InferenceResponse
from src.inference.models.usage import Usage


def test_classify_tool_calls() -> None:
    resp = InferenceResponse(
        content=None,
        tool_calls=(ToolCall(id="1", name="rna.search", arguments='{"query":"x"}'),),
        usage=Usage(),
        finish_reason="tool_calls",
    )
    out = classify(resp)
    assert out.kind == "tool_calls"
    assert out.tool_calls[0].name == "rna.search"


def test_classify_final() -> None:
    resp = InferenceResponse(
        content="done for now",
        usage=Usage(),
        finish_reason="stop",
    )
    out = classify(resp)
    assert out.kind == "final"
    assert out.content == "done for now"


def test_classify_error() -> None:
    out = classify(None, error="boom")
    assert out.kind == "error"
    assert out.message == "boom"


def test_classify_malformed_tool_call() -> None:
    resp = InferenceResponse(
        content=None,
        tool_calls=(ToolCall(id="1", name="", arguments="{}"),),
        usage=Usage(),
        finish_reason="tool_calls",
    )
    out = classify(resp)
    assert out.kind == "invalid"


def test_classify_empty_content_is_invalid() -> None:
    resp = InferenceResponse(content="", usage=Usage(), finish_reason="stop")
    out = classify(resp)
    assert out.kind == "invalid"
    assert out.message == "empty_or_non_substantive_response"


def test_classify_thinking_signature_dump_is_invalid() -> None:
    dump = (
        "[{'type': 'text', 'text': '', 'extras': {'signature': "
        "'ErYCCrMCARFNMg/E18U1Ls+9WfS/iSleSFUQ6DeosRI2Kwhl6x7JcuA++Hy3ZguujcrWZkiyjZnk0u2r4bhc'}}]"
    )
    resp = InferenceResponse(content=dump, usage=Usage(), finish_reason="stop")
    out = classify(resp)
    assert out.kind == "invalid"


def test_classify_xml_tool_markup_is_invalid() -> None:
    resp = InferenceResponse(
        content="<tool_call>\n<function=executor.apply>\n<parameter=patch>\nx\n",
        usage=Usage(),
        finish_reason="stop",
    )
    out = classify(resp)
    assert out.kind == "invalid"
    assert out.message == "xml_tool_markup_in_content"

"""Tool schema generation stays aligned with Rna signatures."""

from __future__ import annotations

from src.rna.mcp.schema import all_tool_schemas, tool_schema


def test_all_tools_present() -> None:
    schemas = all_tool_schemas()
    names = {s["name"] for s in schemas}
    assert "rna_get_callers" in names
    assert "rna_get_hld" in names
    assert "rna_google_search" in names
    assert len(schemas) == 12


def test_get_callers_schema() -> None:
    schema = tool_schema("get_callers")
    assert schema["name"] == "rna_get_callers"
    props = schema["parameters"]["properties"]
    assert "symbol" in props
    assert "symbol" in schema["parameters"]["required"]
    assert "file_hint" in props

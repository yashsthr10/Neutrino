"""Design recovery: HLD / LLD / workflow."""

from __future__ import annotations

import shutil

import pytest

from src.rna import Rna
from src.rna.config import RnaConfig
from src.rna.graph_engine.design_recovery import DesignRecovery, _format_mermaid_flowchart


def test_mermaid_flowchart_uses_safe_node_ids() -> None:
    diagram = _format_mermaid_flowchart(
        [
            ("src/agent", "ext:__future__", 2),
            ("src/agent", "src/tool_engine", 8),
        ]
    )
    assert "graph TD" in diagram
    assert '"src/agent"' in diagram
    assert '"ext:__future__"' in diagram
    assert '"src/agent" -->' not in diagram
    assert "n0[" in diagram
    assert " -->|" in diagram


def test_hld_granularity_controls_node_grouping(rna_python: Rna) -> None:
    coarse = rna_python.get_hld(scope="pkg", granularity="coarse")
    file_level = rna_python.get_hld(scope="pkg", granularity="file")

    assert len(coarse.data.nodes) < len(file_level.data.nodes)
    assert any(n.id == "pkg" for n in coarse.data.nodes)
    assert all("/" in n.id or n.id.endswith(".py") for n in file_level.data.nodes)


def test_hld_node_id_mapping() -> None:
    assert DesignRecovery._hld_node_id("src/agent/loop.py", granularity="coarse") == "src"
    assert DesignRecovery._hld_node_id("src/agent/loop.py", granularity="module") == "src/agent"
    assert DesignRecovery._hld_node_id("pkg/parser.py", granularity="module") == "pkg"
    assert (
        DesignRecovery._hld_node_id("src/agent/prompts/layers/foo.py", granularity="fine")
        == "src/agent/prompts"
    )
    assert (
        DesignRecovery._hld_node_id("src/agent/loop.py", granularity="file") == "src/agent/loop.py"
    )


def test_get_hld_defaults_to_json(rna_python: Rna) -> None:
    hld = rna_python.get_hld(scope="pkg")
    assert hld.data.mermaid is None
    assert hld.data.nodes


def test_get_import_graph_and_hld(rna_python: Rna) -> None:
    g = rna_python.get_import_graph()
    assert g.data.edges
    hld = rna_python.get_hld(format="mermaid")
    assert hld.data.nodes
    assert hld.data.mermaid is not None
    assert "graph TD" in hld.data.mermaid


def test_get_lld_degrades_without_tier3(rna_python: Rna) -> None:
    # Tier-1 only config
    result = rna_python.get_lld("pkg/parser.py", format="json")
    assert result.data.scope == "pkg/parser.py"
    assert result.meta.degraded is True or result.data.nodes
    # Should find parse_request somehow
    names = {n.symbol.name for n in result.data.nodes}
    assert "parse_request" in names or result.meta.degraded


def test_get_workflow_depth_cap(python_repo) -> None:
    cfg = RnaConfig(
        repo_path=python_repo,
        cache_dir=python_repo / ".rna_cache",
        enabled_tiers=("structural",),
        max_workflow_depth=2,
    )
    rna = Rna(cfg)
    trace = rna.get_workflow("handle", max_depth=100)
    assert trace.data.entrypoint == "handle"
    # hard cap should prevent runaway; either truncated or shallow
    depths = [s.depth for s in trace.data.steps]
    assert not depths or max(depths) <= 2 or trace.data.truncated_by_depth


def test_get_tests_naming_and_import(rna_python: Rna) -> None:
    links = rna_python.get_tests("pkg/parser.py")
    assert links.data
    files = {t.test_file for t in links.data}
    assert "tests/test_parser.py" in files
    relations = {t.relation for t in links.data}
    assert "direct_import" in relations or "naming_convention" in relations


@pytest.mark.skipif(
    shutil.which("pyan3") is None and shutil.which("pyan") is None, reason="pyan3 not installed"
)
def test_tier3_python_lld(python_repo) -> None:
    cfg = RnaConfig(
        repo_path=python_repo,
        cache_dir=python_repo / ".rna_cache",
        enabled_tiers=("structural", "whole_program"),
    )
    rna = Rna(cfg)
    result = rna.get_lld("pkg", format="json")
    # May still degrade if pyan output empty on tiny fixture, but should not raise
    assert result.data.scope == "pkg"
    assert result.meta.confidence in {"heuristic", "precise", "whole_program"}

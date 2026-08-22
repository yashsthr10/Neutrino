"""Shared fixtures for rpc tests."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from src.config.schema import InferenceProviderConfig
from src.inference import build_inference
from src.orchestrator import AgentOrchestrator
from src.rpc.framing import NdjsonWriter
from src.rpc.server import RpcServer, build_server
from src.tool_engine import build_tool_engine_from_subsystem
from tests.doubles import FakeInferenceProvider, FakeRna


def build_fast_server(
    repo: Path,
    writer: NdjsonWriter,
    *,
    auto_approve: bool = True,
) -> RpcServer:
    """AgentOrchestrator with scripted inference — fast RPC wire tests."""
    inference_cfg = InferenceProviderConfig(model="test")
    mgr = build_inference(
        inference_cfg,
        provider=FakeInferenceProvider(response_text="Done."),
    )
    session_id = uuid.uuid4().hex
    rna = FakeRna()
    engine = build_tool_engine_from_subsystem(rna, session_id, repo_path=repo)

    holder: dict[str, RpcServer] = {}

    def emit(event):  # type: ignore[no-untyped-def]
        holder["server"].emit_ui_event(event)

    orch = AgentOrchestrator(
        emit,
        repo,
        inference=mgr,
        tool_engine=engine,
        auto_approve=auto_approve,
        session_id=session_id,
    )
    server = RpcServer(
        writer,
        orch,
        model_name="test",
        project_name=repo.name,
        inference=inference_cfg,
    )
    holder["server"] = server
    return server

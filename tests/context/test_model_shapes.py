"""Model shape and config defaults."""

from __future__ import annotations

import dataclasses

from src.context.config import ContextConfig
from src.context import models
from src.context.runtime import execution_context as ec_mod
from src.context.runtime import repository_context as repo_mod
from src.context.runtime import conversation_context as conv_mod
from src.context.runtime import request_context as req_mod
from src.context.runtime import planning_context as plan_mod
from src.context.runtime import execution_state as exec_mod
from src.context.runtime import verification_context as ver_mod
from src.context.runtime import metrics_context as met_mod
from src.context.runtime import event_log as event_mod


def _frozen_types(module) -> list[type]:
    out = []
    for name in dir(module):
        obj = getattr(module, name)
        if dataclasses.is_dataclass(obj) and isinstance(obj, type):
            out.append(obj)
    return out


def test_config_defaults() -> None:
    cfg = ContextConfig()
    assert cfg.max_context_tokens == 8000
    assert cfg.max_files == 5
    assert cfg.max_lines_per_file == 200


def test_dataclasses_are_frozen() -> None:
    modules = [
        models,
        ec_mod,
        repo_mod,
        conv_mod,
        req_mod,
        plan_mod,
        exec_mod,
        ver_mod,
        met_mod,
        event_mod,
    ]
    for mod in modules:
        for cls in _frozen_types(mod):
            params = getattr(cls, "__dataclass_params__", None)
            assert params is not None and params.frozen, f"{cls} must be frozen"
            assert hasattr(cls, "__slots__"), f"{cls} must use slots"

"""Tool Engine facade — validate, dispatch, execute, serialize."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.context.bootstrap import build_context_subsystem
from src.context.config import ContextConfig
from src.execution import GitService, build_execution_service
from src.tool_engine.capabilities import (
    AgentTaskCapability,
    CapabilitiesCapability,
    ContextCapability,
    ExecutionCapability,
    GitCapability,
    PlanningCapability,
    ResearchCapability,
    RnaCapability,
    RuntimeServices,
    TerminalCapability,
    VerificationCapability,
)
from src.verification import build_verification_service
from src.tool_engine.contracts.schema import specs_to_schemas
from src.tool_engine.dispatcher import ToolDispatcher
from src.tool_engine.errors import (
    ExecutionError,
    PermissionDenied,
    ToolDisabled,
    ToolEngineError,
    ToolNotFound,
    ValidationError,
)
from src.tool_engine.executor import ToolExecutor
from src.tool_engine.models import ToolRequest, ToolResult, ToolSpec
from src.tool_engine.observability import EventCallback
from src.tool_engine.registry import ToolRegistry
from src.tool_engine.serializer import ResultSerializer
from src.tool_engine.state_policy import normalize_state
from src.tool_engine.tools import all_tool_specs
from src.tool_engine.validator import ToolValidator


class ToolEngine:
    """LLM-facing tool surface. Stateless aside from registry/handler bindings."""

    def __init__(
        self,
        registry: ToolRegistry,
        validator: ToolValidator,
        dispatcher: ToolDispatcher,
        executor: ToolExecutor,
        serializer: ResultSerializer,
        services: RuntimeServices,
    ) -> None:
        self.registry = registry
        self.validator = validator
        self.dispatcher = dispatcher
        self.executor = executor
        self.serializer = serializer
        self.services = services
        self._expanded_deferred: set[str] = set()

    def expand_deferred_tool(self, name: str) -> None:
        """Load full schema for a deferred tool for the rest of the session."""
        self._expanded_deferred.add(name)

    def register_deferred_tools(self, specs: list[ToolSpec]) -> None:
        """Register MCP or other deferred tool stubs (stable append order)."""
        for spec in sorted(specs, key=lambda s: s.name):
            self.registry.register(spec)

    def list_tools(self, state: str) -> list[ToolSpec]:
        return self.registry.list(state=normalize_state(state))

    def schemas_for_state(self, state: str) -> list[dict[str, Any]]:
        return specs_to_schemas(
            self.list_tools(state),
            expanded_deferred=frozenset(self._expanded_deferred),
        )

    def invoke(self, request: ToolRequest, *, state: str | None = None) -> ToolResult:
        resolved_state = normalize_state(state or _infer_state(request) or "INIT")

        try:
            args = dict(request.arguments or {})
            args = _strip_host_only_args(request.name, args)
            validation_request = ToolRequest(
                name=request.name,
                arguments=args,
                execution_context=request.execution_context,
            )
            spec = self.validator.validate(validation_request, state=resolved_state)
            handler = self.dispatcher.resolve(spec.handler_key)
            self.services.execution_context = request.execution_context
            args = _apply_host_context(spec.name, args, request.execution_context)
            # Fill defaults for missing optional params
            for p in spec.parameters:
                if p.name not in args and p.default is not None:
                    args[p.name] = p.default
            raw, cost_ms = self.executor.execute(
                handler,
                tool_name=spec.name,
                arguments=args,
                state=resolved_state,
            )
            if isinstance(raw, ToolResult):
                return ToolResult(
                    success=raw.success,
                    data=raw.data,
                    meta=type(raw.meta)(
                        cost_ms=cost_ms or raw.meta.cost_ms,
                        truncated=raw.meta.truncated,
                        degraded=raw.meta.degraded,
                        reason=raw.meta.reason,
                        error=raw.meta.error,
                        result_bytes=raw.meta.result_bytes,
                        tool_version=spec.version,
                    ),
                    errors=raw.errors,
                )
            return self.serializer.serialize(raw, cost_ms=cost_ms, tool_version=spec.version)
        except ToolNotFound as exc:
            return self.serializer.from_exception(str(exc), error_code="tool_not_found")
        except ToolDisabled as exc:
            return self.serializer.from_exception(str(exc), error_code="tool_disabled")
        except PermissionDenied as exc:
            return self.serializer.from_exception(str(exc), error_code="permission_denied")
        except ValidationError as exc:
            return self.serializer.from_exception(str(exc), error_code="validation_error")
        except ExecutionError as exc:
            return self.serializer.from_exception(str(exc), error_code="execution_error")
        except ToolEngineError as exc:
            return self.serializer.from_exception(str(exc), error_code="tool_engine_error")
        finally:
            self.services.execution_context = None


_CONTEXT_TOOLS = frozenset({"context.resolve", "context.expand", "context.refresh"})
_HOST_ONLY_ARGS = frozenset({"task_complexity", "requesting_agent"})


def _strip_host_only_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Remove host-injected fields before LLM schema validation."""
    if tool_name not in _CONTEXT_TOOLS:
        return args
    return {k: v for k, v in args.items() if k not in _HOST_ONLY_ARGS}


def _apply_host_context(
    tool_name: str,
    args: dict[str, Any],
    execution_context: Any | None,
) -> dict[str, Any]:
    """Inject host-owned context fields; overrides model-supplied tier/agent."""
    if tool_name not in _CONTEXT_TOOLS or execution_context is None:
        return args
    req = getattr(execution_context, "request", None)
    if req is None:
        return args
    out = dict(args)
    complexity = getattr(req, "task_complexity", None)
    if complexity:
        out["task_complexity"] = complexity
    agent = getattr(req, "requesting_agent", None)
    if agent:
        # Context prefetch uses planner retrieval rules regardless of host agent label.
        out["requesting_agent"] = "planner" if tool_name == "context.resolve" else agent
    return out


def _infer_state(request: ToolRequest) -> str | None:
    """FSM phase is owned by the runtime, not ExecutionState.status.

    Callers must pass ``state=`` explicitly. Do not infer PLAN/EXECUTE from
    execution.status (INIT|RUNNING|DONE|FAIL) — that is a different namespace.
    """
    _ = request
    return None


def build_tool_engine(
    services: RuntimeServices,
    *,
    on_event: EventCallback | None = None,
) -> ToolEngine:
    serializer = ResultSerializer()
    registry = ToolRegistry()
    for spec in all_tool_specs():
        registry.register(spec)

    dispatcher = ToolDispatcher()
    capabilities = [
        ContextCapability(services, serializer),
        RnaCapability(services, serializer),
        ResearchCapability(services, serializer),
        ExecutionCapability(services, serializer),
        TerminalCapability(services, serializer),
        VerificationCapability(services, serializer),
        GitCapability(services, serializer),
        PlanningCapability(services, serializer),
        CapabilitiesCapability(services, serializer),
        AgentTaskCapability(services, serializer),
    ]
    for cap in capabilities:
        for key, handler in cap.as_handler_map().items():
            dispatcher.bind(key, handler)

    engine = ToolEngine(
        registry=registry,
        validator=ToolValidator(registry),
        dispatcher=dispatcher,
        executor=ToolExecutor(on_event=on_event),
        serializer=serializer,
        services=services,
    )
    services.engine = engine
    return engine


def build_tool_engine_from_subsystem(
    rna: Any,
    session_id: str,
    *,
    config: ContextConfig | None = None,
    repo_path: Path | None = None,
    on_event: EventCallback | None = None,
    test_command: str = "pytest",
    lint_command: str = "ruff check",
) -> ToolEngine:
    """Wire Context + Conversation + execution/git/verification, then build the engine."""
    context_manager, conversation_manager = build_context_subsystem(
        rna,
        session_id,
        config,
        repo_path=repo_path,
    )
    root = Path(repo_path).resolve() if repo_path is not None else None
    if root is None:
        cfg_root = getattr(rna, "config", None)
        maybe = getattr(cfg_root, "repo_path", None) if cfg_root is not None else None
        if maybe is not None:
            root = Path(maybe).resolve()

    execution = build_execution_service(root) if root is not None else None
    git = GitService(root) if root is not None else None
    verification = (
        build_verification_service(root, test_command=test_command, lint_command=lint_command)
        if root is not None
        else None
    )
    services = RuntimeServices(
        context=context_manager,
        conversation=conversation_manager,
        rna=rna,
        execution=execution,
        git=git,
        verification=verification,
        repo_path=root,
    )
    return build_tool_engine(services, on_event=on_event)

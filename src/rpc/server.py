"""JSON-RPC server bridging presentation clients to OrchestratorPort."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Protocol, TextIO, runtime_checkable

from src.config.load import load_merged_settings, save_user_inference
from src.config.schema import InferenceProviderConfig
from src.credentials.manager import CredentialManager, build_credential_manager
from src.ports.orchestrator_port import LogLine, UIEvent
from src.rpc import CAPABILITIES, PROTOCOL_MAJOR, PROTOCOL_VERSION
from src.rpc import credentials_rpc, inference_rpc
from src.rpc.dummy import DummyOrchestrator
from src.rpc.framing import NdjsonWriter, read_messages
from src.rpc.mapper import map_ui_event

logger = logging.getLogger("neutrino.rpc")


@runtime_checkable
class _OrchLike(Protocol):
    _repo_path: Path

    def submit_task(self, user_query: str) -> None: ...

    def cancel_run(self) -> None: ...

    def get_status(self) -> dict[str, Any]: ...


def _git_branch(cwd: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        return out.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


class RpcServer:
    """Dispatch JSON-RPC requests; push ui.event notifications via emit."""

    def __init__(
        self,
        writer: NdjsonWriter,
        orchestrator: _OrchLike,
        *,
        model_name: str = "dummy",
        project_name: str | None = None,
        credentials: CredentialManager | None = None,
        inference: InferenceProviderConfig | None = None,
    ) -> None:
        self._writer = writer
        self._orch = orchestrator
        self._inference = inference or InferenceProviderConfig(model=model_name)
        self._model_name = self._inference.model
        self._project_name = project_name or orchestrator._repo_path.name
        self._cwd = orchestrator._repo_path
        self._hello_ok = False
        self._credentials = credentials or build_credential_manager()
        self._credential_profile = self._inference.credential or "default"

    def emit_ui_event(self, event: UIEvent) -> None:
        mapped = map_ui_event(event)
        self._writer.write(
            {
                "jsonrpc": "2.0",
                "method": "ui.event",
                "params": mapped,
            }
        )

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        # Notifications (no id) — ignore unknown
        if msg_id is None:
            return None

        try:
            result = self._dispatch(str(method or ""), params)
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except ProtocolError as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": exc.code, "message": exc.message},
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("RPC handler error")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "session.hello":
            return self._hello(params)
        if method == "runtime.execute":
            self._require_hello()
            task = str(params.get("task") or "")
            if not task.strip():
                raise ProtocolError(-32602, "task is required")
            self.emit_ui_event_started(task)
            self._orch.submit_task(task)
            return {"ok": True}
        if method == "runtime.cancel":
            self._require_hello()
            self._orch.cancel_run()
            return {"ok": True}
        if method == "runtime.approve":
            self._require_hello()
            request_id = str(params.get("requestId") or "")
            action = str(params.get("action") or "accept")
            self._orch.send_approval_action(request_id, action)  # type: ignore[arg-type]
            return {"ok": True}
        if method == "runtime.submitEdit":
            self._require_hello()
            self._orch.submit_approval_edit(
                str(params.get("requestId") or ""),
                str(params.get("text") or ""),
            )
            return {"ok": True}
        if method == "runtime.setMode":
            self._require_hello()
            mode = str(params.get("mode") or "fast")
            self._orch.set_runtime_mode(mode)  # type: ignore[arg-type]
            return {"ok": True}
        if method == "runtime.retry":
            self._require_hello()
            self._orch.request_retry()
            return {"ok": True}
        if method == "runtime.refreshContext":
            self._require_hello()
            self._orch.request_context_refresh()
            return {"ok": True}
        if method == "runtime.requestRepoTree":
            self._require_hello()
            self._orch.request_repo_tree()
            return {"ok": True}
        if method == "runtime.selectRecovery":
            self._require_hello()
            self._orch.select_recovery_option(str(params.get("optionId") or ""))
            return {"ok": True}
        if method == "runtime.undo":
            self._require_hello()
            self._orch.undo()
            return {"ok": True}
        if method == "runtime.status":
            self._require_hello()
            return self._orch.get_status()
        if method == "credentials.list":
            self._require_hello()
            return credentials_rpc.credentials_list(self._credentials, params)
        if method == "credentials.set":
            self._require_hello()
            try:
                return credentials_rpc.credentials_set(self._credentials, params)
            except ValueError as exc:
                raise ProtocolError(-32602, str(exc)) from exc
        if method == "credentials.remove":
            self._require_hello()
            try:
                return credentials_rpc.credentials_remove(self._credentials, params)
            except ValueError as exc:
                raise ProtocolError(-32602, str(exc)) from exc
        if method == "inference.catalog":
            self._require_hello()
            profile = str(params.get("profile") or self._credential_profile)
            return inference_rpc.catalog(
                self._credentials, self._inference, profile=profile
            )
        if method == "inference.listModels":
            self._require_hello()
            provider_id = str(params.get("providerId") or "").strip()
            if not provider_id:
                raise ProtocolError(-32602, "providerId is required")
            profile = str(params.get("profile") or self._credential_profile)
            base_url = params.get("baseUrl")
            try:
                return inference_rpc.list_models_for_provider(
                    self._credentials,
                    provider_id,
                    active=self._inference,
                    profile=profile,
                    base_url=str(base_url) if base_url else None,
                )
            except ValueError as exc:
                raise ProtocolError(-32602, str(exc)) from exc
        if method == "runtime.setModel":
            self._require_hello()
            profile = str(params.get("profile") or self._credential_profile)
            try:
                self._inference = inference_rpc.apply_set_model(
                    self._inference,
                    params,
                    self._credentials,
                    profile=profile,
                )
            except ValueError as exc:
                raise ProtocolError(-32602, str(exc)) from exc
            self._model_name = self._inference.model
            try:
                saved = save_user_inference(self._inference)
                self.emit_ui_event(
                    LogLine(
                        f"Saved default model to {saved}",
                        "info",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not persist inference selection: %s", exc)
                self.emit_ui_event(
                    LogLine(
                        f"Model active for this session but not persisted: {exc}",
                        "warning",
                    )
                )
            try:
                self._sync_orchestrator_inference()
            except Exception as exc:  # noqa: BLE001
                raise ProtocolError(
                    -32000,
                    f"Model config saved but agent backend failed to switch: {exc}",
                ) from exc
            self._emit_model_changed()
            self.emit_ui_event(
                LogLine(
                    f"Model set to {self._inference.provider_id()}/{self._model_name}",
                    "info",
                )
            )
            return {
                "ok": True,
                "model": self._model_name,
                "providerId": self._inference.provider_id(),
                "type": self._inference.type,
                "vendor": self._inference.vendor,
                "baseUrl": self._inference.base_url,
            }
        if method == "ping":
            return {}
        raise ProtocolError(-32601, f"Method not found: {method}")

    def _sync_orchestrator_inference(self) -> None:
        """Rebuild InferenceManager and attach it to AgentOrchestrator.

        Without this, /model only updates the TUI label while the agent keeps
        the provider created at RPC process start (e.g. Ollama llama3.2).
        """
        if os.environ.get("NEUTRINO_ORCHESTRATOR", "agent").strip().lower() == "dummy":
            return

        replace = getattr(self._orch, "replace_inference", None)
        if not callable(replace):
            # DummyOrchestrator (or other stand-in) — try promoting to real agent
            self._try_promote_agent_orchestrator()
            replace = getattr(self._orch, "replace_inference", None)
            if not callable(replace):
                return

        from src.inference import build_inference

        # Attach first (start=False) so /model is not blocked by a flaky health probe.
        # Then optionally start(); warn on failure but keep the swap.
        mgr = build_inference(self._inference, self._credentials, start=False)
        replace(mgr)
        try:
            status = mgr.start()
            if not status.ok:
                self.emit_ui_event(
                    LogLine(
                        f"Model selected but health check failed: {status.message}",
                        "warning",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Inference start after setModel failed: %s", exc)
            self.emit_ui_event(
                LogLine(
                    f"Model selected; provider start deferred ({exc}). "
                    "First chat will retry.",
                    "warning",
                )
            )

    def _try_promote_agent_orchestrator(self) -> None:
        """If we fell back to Dummy at boot, rebuild AgentOrchestrator now."""
        if type(self._orch).__name__ != "DummyOrchestrator":
            return
        try:
            from src.inference import build_inference
            from src.orchestrator import AgentOrchestrator
            from src.rna import Rna, RnaConfig
            from src.tool_engine import build_tool_engine_from_subsystem

            mgr = build_inference(self._inference, self._credentials, start=False)
            session_id = uuid.uuid4().hex
            rna = Rna(RnaConfig(repo_path=self._cwd))
            engine = build_tool_engine_from_subsystem(
                rna, session_id, repo_path=self._cwd
            )
            self._orch = AgentOrchestrator(
                self.emit_ui_event,
                self._cwd,
                inference=mgr,
                tool_engine=engine,
                auto_approve=True,
                session_id=session_id,
            )
            logger.info("Promoted DummyOrchestrator -> AgentOrchestrator after setModel")
            self.emit_ui_event(
                LogLine("Agent backend ready with selected model", "info")
            )
            try:
                mgr.start()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Promoted agent; start deferred: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not promote to AgentOrchestrator: %s", exc)
            raise

    def _emit_model_changed(self) -> None:
        self._writer.write(
            {
                "jsonrpc": "2.0",
                "method": "ui.event",
                "params": {
                    "type": "model.changed",
                    "payload": {
                        "model": self._model_name,
                        "providerId": self._inference.provider_id(),
                        "type": self._inference.type,
                        "vendor": self._inference.vendor,
                        "baseUrl": self._inference.base_url,
                    },
                },
            }
        )

    def emit_ui_event_started(self, task: str) -> None:
        self._writer.write(
            {
                "jsonrpc": "2.0",
                "method": "ui.event",
                "params": {
                    "type": "execution.started",
                    "payload": {"task": task},
                },
            }
        )

    def _hello(self, params: dict[str, Any]) -> dict[str, Any]:
        version = str(params.get("protocolVersion") or "")
        major_s = version.split(".", 1)[0]
        try:
            major = int(major_s)
        except ValueError:
            major = -1
        if major != PROTOCOL_MAJOR:
            raise ProtocolError(
                -32000,
                f"Unsupported protocol version {version!r}; server speaks {PROTOCOL_VERSION}",
            )
        cwd = params.get("cwd")
        if cwd:
            self._cwd = Path(str(cwd)).expanduser().resolve()
        self._hello_ok = True
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "projectName": self._project_name,
            "model": self._model_name,
            "branch": _git_branch(self._cwd),
            "capabilities": list(CAPABILITIES),
        }

    def _require_hello(self) -> None:
        if not self._hello_ok:
            raise ProtocolError(-32001, "Call session.hello before other methods")

    def serve_stdio(self, stdin: TextIO = sys.stdin, stdout: TextIO | None = None) -> None:
        # stdout is already bound via writer; keep signature for tests
        _ = stdout
        for message in read_messages(stdin):
            if not isinstance(message, dict):
                continue
            response = self.handle(message)
            if response is not None:
                self._writer.write(response)


class ProtocolError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def build_server(
    repo: Path | str,
    writer: NdjsonWriter | None = None,
    *,
    model_name: str = "dummy",
    auto_approve: bool = True,
    auto_recover: bool = True,
    credentials: CredentialManager | None = None,
    inference: InferenceProviderConfig | None = None,
) -> RpcServer:
    out = writer or NdjsonWriter(sys.stdout)
    repo_path = Path(repo).resolve()
    holder: dict[str, RpcServer] = {}

    def emit(event: UIEvent) -> None:
        holder["server"].emit_ui_event(event)

    if inference is None:
        try:
            settings = load_merged_settings()
            inference = settings.resolved_inference()
        except Exception:  # noqa: BLE001
            inference = InferenceProviderConfig()
            settings = None
        if model_name and model_name != "dummy":
            inference = inference.model_copy(update={"model": model_name})
    else:
        try:
            settings = load_merged_settings()
        except Exception:  # noqa: BLE001
            settings = None

    creds = credentials or build_credential_manager()
    orch: _OrchLike = _build_orchestrator(
        emit,
        repo_path,
        inference=inference,
        credentials=creds,
        settings=settings,
        auto_approve=auto_approve,
        auto_recover=auto_recover,
    )
    server = RpcServer(
        out,
        orch,
        model_name=model_name,
        project_name=repo_path.name,
        credentials=creds,
        inference=inference,
    )
    holder["server"] = server
    return server


def _build_orchestrator(
    emit,
    repo_path: Path,
    *,
    inference: InferenceProviderConfig,
    credentials: CredentialManager,
    settings: Any,
    auto_approve: bool,
    auto_recover: bool,
) -> _OrchLike:
    mode = os.environ.get("NEUTRINO_ORCHESTRATOR", "agent").strip().lower()
    if mode == "dummy":
        logger.info("Using DummyOrchestrator (NEUTRINO_ORCHESTRATOR=dummy)")
        return DummyOrchestrator(
            emit,
            repo_path,
            auto_approve=auto_approve,
            auto_recover=auto_recover,
        )

    try:
        from src.inference import build_inference
        from src.orchestrator import AgentOrchestrator
        from src.rna import Rna, RnaConfig
        from src.tool_engine import build_tool_engine_from_subsystem

        rules = getattr(settings, "rules", None) if settings is not None else None
        # Never block session.hello on provider health (rate limits / retries can hang
        # the TUI on "Connecting to runtime…"). First chat / setModel may start later.
        mgr = build_inference(
            settings if settings is not None else inference,
            credentials,
            start=False,
        )
        session_id = uuid.uuid4().hex
        rna = Rna(RnaConfig(repo_path=repo_path))
        engine = build_tool_engine_from_subsystem(
            rna, session_id, repo_path=repo_path
        )
        logger.info("Using AgentOrchestrator")
        return AgentOrchestrator(
            emit,
            repo_path,
            inference=mgr,
            tool_engine=engine,
            rules=rules,
            auto_approve=auto_approve,
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "AgentOrchestrator unavailable (%s); falling back to DummyOrchestrator",
            exc,
        )
        return DummyOrchestrator(
            emit,
            repo_path,
            auto_approve=auto_approve,
            auto_recover=auto_recover,
        )

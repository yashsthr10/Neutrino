"""LangChain-backed native vendors (optional extras)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from src.config.schema import InferenceProviderConfig
from src.credentials.models import ResolvedCredentials
from src.inference.errors import (
    AuthenticationError,
    InferenceConfigError,
    InferenceConnectionError,
    RateLimitExceeded,
    ToolUseFailed,
    UnsupportedCapability,
    extract_failed_generation,
    is_tool_use_failed_message,
)
from src.inference.models.capabilities import ProviderCapabilities
from src.inference.models.request import InferenceRequest, ToolCall
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)
from src.inference.models.usage import Usage


class LangChainProvider:
    name = "langchain"

    def __init__(
        self,
        config: InferenceProviderConfig,
        credentials: ResolvedCredentials,
        *,
        chat_model: Any | None = None,
    ) -> None:
        self._config = config
        self._credentials = credentials
        self._chat_model = chat_model
        self._vendor = (config.vendor or "openai").lower()

    def connect(self) -> None:
        if self._chat_model is None:
            self._chat_model = self._build_chat_model()

    def close(self) -> None:
        self._chat_model = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, structured_output=False, streaming=True)

    def health(self) -> HealthStatus:
        from src.inference.models.request import Message

        self.connect()
        try:
            self.chat(
                InferenceRequest(
                    messages=(Message(role="user", content="Respond with OK."),),
                    max_tokens=8,
                    temperature=0,
                )
            )
            return HealthStatus(ok=True, message=f"{self._vendor} ok")
        except AuthenticationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise InferenceConnectionError(str(exc)) from exc

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id=self._config.model, owned_by=self._vendor)]

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        self.connect()
        assert self._chat_model is not None
        try:
            from langchain_core.messages import (
                AIMessage,
                HumanMessage,
                SystemMessage,
                ToolMessage,
            )
        except ImportError as exc:
            raise UnsupportedCapability(
                "Install langchain-core and a vendor extra (e.g. inference-openai)"
            ) from exc

        lc_messages: list[Any] = []
        for m in request.messages:
            if m.role == "system":
                lc_messages.append(SystemMessage(content=m.content or ""))
            elif m.role == "assistant":
                if m.tool_calls:
                    lc_tool_calls = []
                    for tc in m.tool_calls:
                        try:
                            args = json.loads(tc.arguments) if tc.arguments else {}
                        except json.JSONDecodeError:
                            args = {"_raw": tc.arguments}
                        if not isinstance(args, dict):
                            args = {"value": args}
                        lc_tool_calls.append(
                            {"id": tc.id or tc.name, "name": tc.name, "args": args}
                        )
                    lc_messages.append(AIMessage(content=m.content or "", tool_calls=lc_tool_calls))
                else:
                    lc_messages.append(AIMessage(content=m.content or ""))
            elif m.role == "tool":
                lc_messages.append(
                    ToolMessage(
                        content=m.content or "",
                        tool_call_id=m.tool_call_id or "",
                        name=m.name or "",
                    )
                )
            else:
                lc_messages.append(HumanMessage(content=m.content or ""))

        model = self._chat_model
        if request.tools:
            # Bind Tool Engine schemas so native vendors (Gemini, etc.) can call tools.
            tool_dicts = [
                {
                    "name": t.name,
                    "description": t.description or t.name,
                    "parameters": t.parameters or {"type": "object", "properties": {}},
                }
                for t in request.tools
            ]
            try:
                model = self._chat_model.bind_tools(tool_dicts)
            except Exception:  # noqa: BLE001
                # Older LC versions / vendors — fall back to unbound chat
                model = self._chat_model

        try:
            result = model.invoke(lc_messages)
        except Exception as exc:  # noqa: BLE001
            mapped = _map_invoke_error(exc)
            raise mapped from exc

        content = _normalize_lc_content(getattr(result, "content", None))
        tool_calls: list[ToolCall] = []
        for tc in getattr(result, "tool_calls", None) or []:
            parsed = _parse_lc_tool_call(tc)
            if parsed is not None:
                tool_calls.append(parsed)
        usage_meta = getattr(result, "usage_metadata", None) or {}
        usage = Usage(
            input_tokens=int(usage_meta.get("input_tokens") or 0),
            output_tokens=int(usage_meta.get("output_tokens") or 0),
        )
        return InferenceResponse(
            content=content,
            tool_calls=tuple(tool_calls),
            usage=usage,
            finish_reason="tool_calls" if tool_calls else "stop",
            model=self._config.model,
        )

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        # Phase A: fall back to non-streaming chat then emit as deltas
        resp = self.chat(request)
        if resp.content:
            yield InferenceStreamEvent(type="delta_text", text=resp.content)
        yield InferenceStreamEvent(type="usage", usage=resp.usage)
        yield InferenceStreamEvent(type="done", finish_reason=resp.finish_reason)

    def _build_chat_model(self) -> Any:
        vendor = self._vendor
        model = self._config.model
        key = self._credentials.fields.get("api_key") or self._credentials.fields.get("token")

        if vendor == "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as exc:
                raise UnsupportedCapability("pip install 'neutrino-cli[inference-openai]'") from exc
            kwargs: dict[str, Any] = {"model": model, "temperature": self._config.temperature}
            if key:
                kwargs["api_key"] = key
            if self._config.organization:
                kwargs["organization"] = self._config.organization
            if self._config.base_url:
                kwargs["base_url"] = self._config.base_url
            return ChatOpenAI(**kwargs)

        if vendor == "openrouter":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as exc:
                raise UnsupportedCapability("pip install 'neutrino-cli[inference-openai]'") from exc
            return ChatOpenAI(
                model=model,
                api_key=key,
                base_url=_openrouter_base_url(self._config.base_url),
                temperature=self._config.temperature,
            )

        if vendor == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError as exc:
                raise UnsupportedCapability(
                    "pip install 'neutrino-cli[inference-anthropic]'"
                ) from exc
            return ChatAnthropic(model=model, api_key=key, temperature=self._config.temperature)

        if vendor == "azure_openai":
            try:
                from langchain_openai import AzureChatOpenAI
            except ImportError as exc:
                raise UnsupportedCapability("pip install 'neutrino-cli[inference-azure]'") from exc
            endpoint = (
                self._config.azure_endpoint
                or self._credentials.hints.get("azure_endpoint")
                or self._config.base_url
            )
            if not endpoint or not self._config.api_version:
                raise InferenceConfigError("azure_openai requires azure_endpoint and api_version")
            deployment = self._config.deployment or model
            return AzureChatOpenAI(
                azure_endpoint=endpoint,
                api_version=self._config.api_version,
                deployment_name=deployment,
                api_key=key,
                temperature=self._config.temperature,
            )

        if vendor == "bedrock":
            try:
                from langchain_aws import ChatBedrockConverse
            except ImportError as exc:
                raise UnsupportedCapability(
                    "pip install 'neutrino-cli[inference-bedrock]'"
                ) from exc
            region = self._config.region or self._credentials.hints.get("region")
            if not region:
                raise InferenceConfigError("bedrock requires region")
            kwargs = {
                "model": model,
                "region_name": region,
                "temperature": self._config.temperature,
            }
            if self._credentials.kind == "aws":
                # boto3 session from explicit keys is left to env; langchain uses default chain
                pass
            if self._config.aws_profile:
                import os

                os.environ.setdefault("AWS_PROFILE", self._config.aws_profile)
            return ChatBedrockConverse(**kwargs)

        if vendor == "google_genai":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as exc:
                raise UnsupportedCapability("pip install 'neutrino-cli[inference-google]'") from exc
            return ChatGoogleGenerativeAI(
                model=model, google_api_key=key, temperature=self._config.temperature
            )

        if vendor == "groq":
            try:
                from langchain_groq import ChatGroq
            except ImportError as exc:
                raise UnsupportedCapability("pip install 'neutrino-cli[inference-groq]'") from exc
            return ChatGroq(model=model, api_key=key, temperature=self._config.temperature)

        raise UnsupportedCapability(f"Unsupported native vendor: {vendor}")


def _map_invoke_error(exc: Exception) -> Exception:
    """Map vendor SDK exceptions to inference error types."""
    text = str(exc)
    lower = text.lower()
    if is_tool_use_failed_message(text):
        fg = _failed_generation_from_exc(exc) or extract_failed_generation(exc)
        return ToolUseFailed(text, failed_generation=fg)
    if "auth" in lower or "api key" in lower or "401" in lower or "403" in lower:
        return AuthenticationError(text)
    if "429" in lower or "rate limit" in lower:
        return RateLimitExceeded(text)
    return InferenceConnectionError(text)


def _failed_generation_from_exc(exc: Exception) -> str | None:
    """Best-effort pull of Groq ``failed_generation`` from SDK error objects."""
    for attr in ("body", "error"):
        candidate = _failed_generation_from_payload(getattr(exc, attr, None))
        if candidate:
            return candidate
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            data = resp.json() if callable(getattr(resp, "json", None)) else None
        except Exception:  # noqa: BLE001
            data = None
        candidate = _failed_generation_from_payload(data)
        if candidate:
            return candidate
    return None


def _failed_generation_from_payload(payload: Any) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    err = payload.get("error") if "error" in payload else payload
    if isinstance(err, dict):
        fg = err.get("failed_generation")
        if isinstance(fg, str) and fg.strip():
            return fg
    return None


def _normalize_lc_content(content: Any) -> str | None:
    """Flatten LangChain/Gemini content blocks to plain text."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                if block.strip():
                    parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                # Skip empty thinking/signature-only blocks
                if isinstance(text, str) and text.strip():
                    parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        joined = "\n".join(parts).strip()
        return joined or None
    text = str(content).strip()
    return text or None


def _parse_lc_tool_call(tc: Any) -> ToolCall | None:
    if isinstance(tc, dict):
        name = str(tc.get("name") or "")
        tid = str(tc.get("id") or name)
        args = tc.get("args") if "args" in tc else tc.get("arguments")
    else:
        name = str(getattr(tc, "name", "") or "")
        tid = str(getattr(tc, "id", "") or name)
        args = getattr(tc, "args", None)
    if not name:
        return None
    if isinstance(args, str):
        arguments = args
    else:
        try:
            arguments = json.dumps(args if args is not None else {})
        except TypeError:
            arguments = json.dumps({"_raw": str(args)})
    return ToolCall(id=tid, name=name, arguments=arguments)


_OPENROUTER_DEFAULT_BASE = "https://openrouter.ai/api/v1"


def _openrouter_base_url(configured: str | None) -> str:
    """Use OpenRouter cloud URL; ignore inherited local openai-compatible hosts."""
    if not configured or not configured.strip():
        return _OPENROUTER_DEFAULT_BASE
    lower = configured.strip().lower()
    if any(token in lower for token in ("127.0.0.1", "localhost", "0.0.0.0", ":11434", "/ollama")):
        return _OPENROUTER_DEFAULT_BASE
    return configured.rstrip("/")

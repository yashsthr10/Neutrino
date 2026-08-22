"""OpenAI-compatible HTTP provider (Ollama, vLLM, LM Studio, llama.cpp)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from src.credentials.models import ResolvedCredentials
from src.inference.adapters.request_adapter import request_to_openai_body
from src.inference.adapters.response_adapter import parse_openai_chat_completion
from src.inference.errors import (
    AuthenticationError,
    InferenceConnectionError,
    ModelNotFound,
    ProviderUnavailable,
    RateLimitExceeded,
    StreamingError,
    Timeout,
    ToolUseFailed,
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
from src.config.schema import InferenceProviderConfig


def _is_local_base_url(url: str) -> bool:
    lower = url.strip().lower()
    return any(token in lower for token in ("127.0.0.1", "localhost", "0.0.0.0", ":11434"))


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self,
        config: InferenceProviderConfig,
        credentials: ResolvedCredentials,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        base = (config.base_url or "http://127.0.0.1:11434/v1").rstrip("/")
        self._base_url = base
        self._credentials = credentials
        self._client = client
        self._owns_client = client is None

    def connect(self) -> None:
        if self._client is None:
            headers = {"Content-Type": "application/json"}
            api_key = self._credentials.fields.get("api_key") or self._credentials.fields.get(
                "token"
            )
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            read_timeout = self._config.timeout_s
            if _is_local_base_url(self._base_url):
                read_timeout = max(read_timeout, 600.0)
            self._client = httpx.Client(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=10.0),
            )

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, structured_output=False, streaming=True)

    def health(self) -> HealthStatus:
        self.connect()
        assert self._client is not None
        try:
            resp = self._client.get("/models")
            if resp.status_code in {401, 403}:
                raise AuthenticationError("openai-compatible auth failed on /models")
            if resp.status_code < 400:
                data = resp.json()
                models = tuple(str(m.get("id")) for m in (data.get("data") or []) if m.get("id"))
                return HealthStatus(ok=True, message="ok", models=models)
        except httpx.HTTPError:
            pass
        # Fallback minimal completion
        try:
            body = {
                "model": self._config.model,
                "messages": [{"role": "user", "content": "Respond with OK."}],
                "max_tokens": 8,
                "temperature": 0,
            }
            resp = self._client.post("/chat/completions", json=body)
            if resp.status_code in {401, 403}:
                raise AuthenticationError("openai-compatible auth failed")
            if resp.status_code >= 400:
                return HealthStatus(ok=False, message=f"HTTP {resp.status_code}")
            return HealthStatus(ok=True, message="ok via chat fallback")
        except AuthenticationError:
            raise
        except httpx.TimeoutException as exc:
            raise Timeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise InferenceConnectionError(str(exc)) from exc

    def list_models(self) -> list[ModelInfo]:
        self.connect()
        assert self._client is not None
        try:
            resp = self._client.get("/models")
            resp.raise_for_status()
            data = resp.json()
            return [
                ModelInfo(id=str(m.get("id")), owned_by=m.get("owned_by"))
                for m in (data.get("data") or [])
                if m.get("id")
            ]
        except httpx.HTTPError as exc:
            raise InferenceConnectionError(str(exc)) from exc

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        self.connect()
        assert self._client is not None
        body = request_to_openai_body(
            request,
            default_model=self._config.model,
            default_temperature=self._config.temperature,
            default_max_tokens=self._config.max_tokens,
        )
        try:
            resp = self._client.post("/chat/completions", json=body)
            return self._handle_chat_response(resp)
        except httpx.TimeoutException as exc:
            raise Timeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise InferenceConnectionError(str(exc)) from exc

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        self.connect()
        assert self._client is not None
        body = request_to_openai_body(
            request,
            default_model=self._config.model,
            default_temperature=self._config.temperature,
            default_max_tokens=self._config.max_tokens,
        )
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        try:
            with self._client.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code in {401, 403}:
                    raise AuthenticationError("openai-compatible auth failed")
                if resp.status_code == 429:
                    raise RateLimitExceeded("rate limited")
                if resp.status_code >= 400:
                    raise ProviderUnavailable(f"HTTP {resp.status_code}")
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        payload = line[6:].strip()
                    else:
                        continue
                    if payload == "[DONE]":
                        yield InferenceStreamEvent(type="done", finish_reason="stop")
                        return
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choice = (data.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    reasoning = (
                        delta.get("reasoning_content")
                        or delta.get("reasoning")
                        or delta.get("thinking")
                    )
                    if reasoning:
                        yield InferenceStreamEvent(type="delta_reasoning", text=str(reasoning))
                    if delta.get("content"):
                        yield InferenceStreamEvent(type="delta_text", text=str(delta["content"]))
                    for tc in delta.get("tool_calls") or []:
                        fn = tc.get("function") or {}
                        yield InferenceStreamEvent(
                            type="tool_call_delta",
                            tool_call=ToolCall(
                                id=str(tc.get("id") or ""),
                                name=str(fn.get("name") or ""),
                                arguments=str(fn.get("arguments") or ""),
                            ),
                            tool_index=int(tc["index"]) if tc.get("index") is not None else None,
                        )
                    usage_raw = data.get("usage")
                    if usage_raw:
                        yield InferenceStreamEvent(
                            type="usage",
                            usage=Usage(
                                input_tokens=int(usage_raw.get("prompt_tokens") or 0),
                                output_tokens=int(usage_raw.get("completion_tokens") or 0),
                            ),
                        )
        except (AuthenticationError, RateLimitExceeded, ProviderUnavailable):
            raise
        except httpx.TimeoutException as exc:
            raise Timeout(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise StreamingError(str(exc)) from exc

    def _handle_chat_response(self, resp: httpx.Response) -> InferenceResponse:
        if resp.status_code in {401, 403}:
            raise AuthenticationError("openai-compatible auth failed")
        if resp.status_code == 404:
            raise ModelNotFound(f"model not found: {self._config.model}")
        if resp.status_code == 429:
            raise RateLimitExceeded("rate limited")
        if resp.status_code >= 500:
            raise ProviderUnavailable(f"HTTP {resp.status_code}")
        if resp.status_code >= 400:
            body = resp.text or ""
            if is_tool_use_failed_message(body):
                raise ToolUseFailed(
                    f"HTTP {resp.status_code}: {body[:500]}",
                    failed_generation=extract_failed_generation(body),
                )
            raise InferenceConnectionError(f"HTTP {resp.status_code}: {body[:200]}")
        return parse_openai_chat_completion(resp.json())

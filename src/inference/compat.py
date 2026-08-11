"""Adapt InferencePort/Manager to Context ChatModelPort.complete()."""

from __future__ import annotations


from src.inference.models.request import InferenceRequest, Message
from src.inference.ports.inference_port import InferencePort


class InferenceChatModelAdapter:
    """Bridge InferenceManager → Context summarizer/decision extractor Protocol."""

    def __init__(self, inference: InferencePort) -> None:
        self._inference = inference

    def complete(self, messages: list[dict[str, str]]) -> str:
        converted: list[Message] = []
        for m in messages:
            role = m.get("role") or "user"
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            converted.append(Message(role=role, content=m.get("content") or ""))  # type: ignore[arg-type]
        resp = self._inference.chat(InferenceRequest(messages=tuple(converted)))
        return resp.content or ""

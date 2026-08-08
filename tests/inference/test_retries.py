"""Manager retry behavior on transient errors."""

from __future__ import annotations

from src.config.schema import InferenceProviderConfig
from src.credentials import CredentialManager, MemoryStore
from src.inference import InferenceRequest, Message
from src.inference.errors import RateLimitExceeded
from src.inference.manager import InferenceManager
from src.inference.models.response import InferenceResponse
from src.inference.providers.fake import FakeInferenceProvider


class FlakyProvider(FakeInferenceProvider):
    def __init__(self) -> None:
        super().__init__(response_text="ok")
        self.attempts = 0

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        self.attempts += 1
        if self.attempts < 3:
            raise RateLimitExceeded("429")
        return super().chat(request)


def test_manager_retries_rate_limit() -> None:
    flaky = FlakyProvider()
    mgr = InferenceManager(
        InferenceProviderConfig(),
        CredentialManager(store=MemoryStore()),
        provider=flaky,
        max_retries=3,
    )
    resp = mgr.chat(InferenceRequest(messages=(Message(role="user", content="hi"),)))
    assert resp.content == "ok"
    assert flaky.attempts == 3

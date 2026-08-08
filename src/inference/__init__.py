"""Inference Subsystem — provider-agnostic chat/stream for the Neutrino Runtime."""

from src.inference.compat import InferenceChatModelAdapter
from src.inference.errors import (
    AuthenticationError,
    InferenceConfigError,
    InferenceConnectionError,
    InferenceError,
    ModelNotFound,
    ProviderUnavailable,
    RateLimitExceeded,
    StreamingError,
    Timeout,
    UnsupportedCapability,
)
from src.inference.manager import InferenceManager, build_inference
from src.inference.models import (
    HealthStatus,
    InferenceRequest,
    InferenceResponse,
    InferenceStreamEvent,
    Message,
    ModelInfo,
    ToolCall,
    ToolSpec,
    Usage,
)
from src.inference.ports import InferencePort
from src.inference.providers.fake import FakeInferenceProvider

__all__ = [
    "InferenceManager",
    "build_inference",
    "InferencePort",
    "InferenceChatModelAdapter",
    "FakeInferenceProvider",
    "InferenceRequest",
    "InferenceResponse",
    "InferenceStreamEvent",
    "Message",
    "ToolCall",
    "ToolSpec",
    "Usage",
    "HealthStatus",
    "ModelInfo",
    "InferenceError",
    "InferenceConfigError",
    "InferenceConnectionError",
    "AuthenticationError",
    "ProviderUnavailable",
    "ModelNotFound",
    "StreamingError",
    "Timeout",
    "RateLimitExceeded",
    "UnsupportedCapability",
]

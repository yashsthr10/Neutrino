"""Bootstrap helpers — canonical construction path for the Context Subsystem."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.context.config import ContextConfig
from src.context.conversation.conversation_manager import ConversationManager
from src.context.conversation.summarizer import ChatModelPort
from src.context.manager.context_manager import ContextManager


def build_context_subsystem(
    rna: Any,
    session_id: str,
    config: ContextConfig | None = None,
    *,
    repo_path: Path | None = None,
    chat_model: ChatModelPort | None = None,
) -> tuple[ContextManager, ConversationManager]:
    """Construct ContextManager + ConversationManager for one session.

    This is the recommended construction path for host applications / orchestrator.

    Pass ``chat_model`` for summarization / decision extraction. Prefer
    ``InferenceChatModelAdapter`` from ``src.inference`` wrapping an
    ``InferenceManager`` (see ``build_context_subsystem_with_inference``).
    """
    cfg = config or ContextConfig()
    path = repo_path
    if path is None and hasattr(rna, "repo_path"):
        path = Path(rna.repo_path)
    if path is None and hasattr(rna, "config") and hasattr(rna.config, "repo_path"):
        path = Path(rna.config.repo_path)

    conversation = ConversationManager(
        session_id=session_id,
        config=cfg,
        chat_model=chat_model,
        cache_dir=cfg.resolved_cache_dir(path),
    )
    context_manager = ContextManager(
        rna=rna,
        conversation=conversation,
        config=cfg,
        repo_path=path,
    )
    return context_manager, conversation


def build_context_subsystem_with_inference(
    rna: Any,
    session_id: str,
    settings: Any,
    *,
    config: ContextConfig | None = None,
    repo_path: Path | None = None,
    credentials: Any | None = None,
    provider: Any | None = None,
) -> tuple[ContextManager, ConversationManager, Any]:
    """Build Context + Conversation wired to Inference via ChatModelPort adapter.

    Returns ``(context_manager, conversation, inference_manager)``.
    """
    from src.inference import InferenceChatModelAdapter, build_inference

    inference = build_inference(settings, credentials, provider=provider)
    adapter = InferenceChatModelAdapter(inference)
    context_manager, conversation = build_context_subsystem(
        rna,
        session_id,
        config=config,
        repo_path=repo_path,
        chat_model=adapter,
    )
    return context_manager, conversation, inference

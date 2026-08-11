"""Validator — invariant checks before emitting a ContextPackage."""

from __future__ import annotations

from src.context.errors import ContextSecurityError
from src.context.models import ContextRequest
from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.repository_context import RepositoryContextItem


class Validator:
    def validate(
        self,
        request: ContextRequest,
        items: list[RepositoryContextItem],
        conversation: ConversationContext,
        *,
        tokens_estimate: int,
        token_budget: int,
        provenance: list[str],
        session_id: str | None = None,
    ) -> list[str]:
        prov = list(provenance)

        # 1. Scope boundary — conversation session must match request session if both set
        expected = request.session_id or session_id
        if expected is not None:
            # Decisions/messages are already session-scoped by ConversationManager;
            # detect leaked foreign session ids if metadata carries one.
            for msg in conversation.recent_messages + conversation.relevant_history:
                foreign = msg.metadata.get("session_id")
                if foreign and foreign != expected:
                    raise ContextSecurityError(
                        f"cross-session leak in conversation message {msg.id}: {foreign}"
                    )

        # 2. Contract completeness (soft — provenance only)
        kinds = {i.kind for i in items}
        agent = request.requesting_agent
        if agent == "verifier" and "test_link" not in kinds and "file" not in kinds:
            prov.append("verifier contract: no test_link items found for changed files")
        if agent == "planner" and request.file_hints and "file" not in kinds:
            prov.append("planner contract: expected file items for file_hints")
        if agent == "coder" and request.file_hints and "file" not in kinds:
            prov.append("coder contract: expected file items for file_hints")

        # 3. Budget compliance (soft assertion — record if over)
        if tokens_estimate > token_budget:
            prov.append(
                f"budget assertion: tokens_estimate={tokens_estimate} > budget={token_budget}"
            )

        return prov

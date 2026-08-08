"""Compressor — enforce token/file/line budgets on ranked context."""

from __future__ import annotations

from dataclasses import replace

from src.context.config import ContextConfig
from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.repository_context import RepositoryContextItem
from src.rna.models import FileSlice


class Compressor:
    def __init__(self, config: ContextConfig) -> None:
        self.config = config

    def compress(
        self,
        items: list[RepositoryContextItem],
        conversation: ConversationContext,
        *,
        token_budget: int | None = None,
    ) -> tuple[list[RepositoryContextItem], ConversationContext, list[str], bool]:
        budget = token_budget if token_budget is not None else self.config.max_context_tokens
        conv_budget = int(budget * self.config.conversation_reserve_ratio)
        repo_budget = budget - conv_budget

        kept_items: list[RepositoryContextItem] = []
        provenance: list[str] = []
        running = 0
        file_count = 0
        truncated = False

        for item in items:
            candidate = item
            if item.kind == "file":
                candidate = self._maybe_truncate_file(item)
                if candidate.tokens_estimate != item.tokens_estimate:
                    truncated = True
                    provenance.append(
                        f"{item.source_method}: truncated file content to "
                        f"{self.config.max_lines_per_file} lines"
                    )

            if candidate.kind == "file" and file_count >= self.config.max_files:
                truncated = True
                provenance.append(
                    f"{candidate.source_method}: dropped (max_files) - {candidate.kind}"
                )
                continue

            if running + candidate.tokens_estimate > repo_budget:
                truncated = True
                provenance.append(
                    f"{candidate.source_method}: dropped (budget) - {candidate.kind}"
                )
                continue

            kept_items.append(candidate)
            running += candidate.tokens_estimate
            if candidate.kind == "file":
                file_count += 1

        compressed_conv, conv_prov, conv_trunc = self._compress_conversation(
            conversation, conv_budget
        )
        provenance.extend(conv_prov)
        truncated = truncated or conv_trunc
        return kept_items, compressed_conv, provenance, truncated

    def _maybe_truncate_file(self, item: RepositoryContextItem) -> RepositoryContextItem:
        payload = item.payload
        if not isinstance(payload, FileSlice):
            return item
        lines = payload.content.splitlines(keepends=True)
        max_lines = self.config.max_lines_per_file
        if len(lines) <= max_lines:
            return item
        new_content = "".join(lines[:max_lines])
        new_slice = FileSlice(
            path=payload.path,
            start_line=payload.start_line,
            end_line=payload.start_line + max_lines - 1,
            content=new_content,
            total_lines=payload.total_lines,
            truncated=True,
        )
        tokens = max(1, len(new_content.split()))
        return replace(item, payload=new_slice, tokens_estimate=tokens)

    def _compress_conversation(
        self, conversation: ConversationContext, budget: int
    ) -> tuple[ConversationContext, list[str], bool]:
        provenance: list[str] = []
        truncated = False
        remaining = budget

        # Priority: recent (floor 4) > decisions > summary > relevant_history
        recent = list(conversation.recent_messages)
        floor = min(4, len(recent))
        kept_recent = recent[-floor:] if recent else []
        if len(recent) > floor:
            # Try to keep more if budget allows
            for m in reversed(recent[:-floor] if floor else recent):
                cost = max(1, len(m.content.split()))
                if remaining - cost < 0 and len(kept_recent) >= floor:
                    truncated = True
                    provenance.append(
                        "conversation.recent_messages: truncated "
                        f"(kept {len(kept_recent)} of {len(recent)})"
                    )
                    break
                kept_recent.insert(0, m)
                remaining -= cost
        else:
            remaining -= sum(max(1, len(m.content.split())) for m in kept_recent)

        decisions = list(conversation.decisions)
        decision_cost = sum(max(1, len(d.statement.split())) for d in decisions)
        if decision_cost > remaining and decisions:
            # Keep highest-confidence decisions that fit
            decisions_sorted = sorted(decisions, key=lambda d: d.confidence, reverse=True)
            kept_dec: list = []
            for d in decisions_sorted:
                c = max(1, len(d.statement.split()))
                if c <= remaining:
                    kept_dec.append(d)
                    remaining -= c
            decisions = kept_dec
            truncated = True
            provenance.append("conversation.decisions: truncated to fit budget")
        else:
            remaining -= decision_cost

        summary = conversation.summary
        if summary is not None:
            if summary.tokens_estimate <= remaining:
                remaining -= summary.tokens_estimate
            else:
                summary = None
                truncated = True
                provenance.append("conversation.summary: dropped (budget)")

        relevant = list(conversation.relevant_history)
        kept_rel: list = []
        for m in relevant:
            c = max(1, len(m.content.split()))
            if c <= remaining:
                kept_rel.append(m)
                remaining -= c
            else:
                truncated = True
                provenance.append(
                    f"conversation.relevant_history: truncated to {len(kept_rel)} messages "
                    "(floor priority)"
                )
                break

        tokens = (
            sum(max(1, len(m.content.split())) for m in kept_recent)
            + sum(max(1, len(d.statement.split())) for d in decisions)
            + (summary.tokens_estimate if summary else 0)
            + sum(max(1, len(m.content.split())) for m in kept_rel)
        )
        return (
            ConversationContext(
                recent_messages=tuple(kept_recent),
                summary=summary,
                relevant_history=tuple(kept_rel),
                decisions=tuple(decisions),
                tokens_estimate=tokens,
                truncated=truncated,
            ),
            provenance,
            truncated,
        )

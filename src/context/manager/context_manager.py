"""ContextManager — composes bounded, ranked context packages for one agent step."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.context.config import ContextConfig
from src.context.manager.aggregator import Aggregator
from src.context.manager.analyzer import RequirementAnalyzer
from src.context.manager.cache import PackageCache
from src.context.manager.compressor import Compressor
from src.context.manager.ranker import Ranker
from src.context.manager.retrieval_planner import RetrievalPlanner
from src.context.manager.validator import Validator
from src.context.models import (
    ContextMeta,
    ContextPackage,
    ContextRequest,
    ContextResult,
)
from src.context.observability import timed_call
from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.repository_context import RepositoryContext, RepositoryContextItem
from src.rna.repo_analyzer.fingerprint import content_hash


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_fingerprint(request: ContextRequest) -> str:
    payload = {
        "task_description": request.task_description,
        "task_complexity": request.task_complexity,
        "requesting_agent": request.requesting_agent,
        "file_hints": list(request.file_hints),
        "symbol_hints": list(request.symbol_hints),
        "conversation_query": request.conversation_query,
        "token_budget": request.token_budget,
        "capabilities": list(request.capabilities) if request.capabilities else None,
        "session_id": request.session_id,
    }
    return content_hash(json.dumps(payload, sort_keys=True))


def _package_to_dict(package: ContextPackage) -> dict[str, Any]:
    from src.context.runtime.execution_context import _to_jsonable

    return _to_jsonable(package)


def _package_from_dict(data: dict[str, Any]) -> ContextPackage:
    """Rebuild ContextPackage from cached JSON (payloads stay as dicts — fine for cache hits)."""
    from src.context.runtime.conversation_context import (
        ConversationSummary,
        Decision,
        Message,
    )

    req = data["request"]
    request = ContextRequest(
        task_description=req["task_description"],
        task_complexity=req["task_complexity"],
        requesting_agent=req["requesting_agent"],
        file_hints=tuple(req.get("file_hints") or ()),
        symbol_hints=tuple(req.get("symbol_hints") or ()),
        conversation_query=req.get("conversation_query"),
        token_budget=req.get("token_budget"),
        capabilities=tuple(req["capabilities"]) if req.get("capabilities") else None,
        session_id=req.get("session_id"),
    )
    repo_raw = data["repository"]
    items = tuple(
        RepositoryContextItem(
            kind=i["kind"],
            payload=i["payload"],
            relevance=i["relevance"],
            tokens_estimate=i["tokens_estimate"],
            source_method=i["source_method"],
        )
        for i in repo_raw.get("items") or ()
    )
    repository = RepositoryContext(
        items=items,
        tokens_estimate=repo_raw["tokens_estimate"],
        truncated=repo_raw["truncated"],
        degraded=repo_raw.get("degraded", False),
        reason=repo_raw.get("reason"),
    )
    conv_raw = data["conversation"]
    summary = None
    if conv_raw.get("summary"):
        s = conv_raw["summary"]
        summary = ConversationSummary(
            text=s["text"],
            covers_through_message_id=s["covers_through_message_id"],
            created_at=s["created_at"],
            tokens_estimate=s["tokens_estimate"],
        )
    conversation = ConversationContext(
        recent_messages=tuple(
            Message(
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
                id=m.get("id") or "",
                metadata=m.get("metadata") or {},
            )
            for m in conv_raw.get("recent_messages") or ()
        ),
        summary=summary,
        relevant_history=tuple(
            Message(
                role=m["role"],
                content=m["content"],
                created_at=m["created_at"],
                id=m.get("id") or "",
                metadata=m.get("metadata") or {},
            )
            for m in conv_raw.get("relevant_history") or ()
        ),
        decisions=tuple(
            Decision(
                category=d["category"],
                statement=d["statement"],
                source_message_id=d["source_message_id"],
                created_at=d["created_at"],
                confidence=d["confidence"],
                id=d.get("id") or "",
            )
            for d in conv_raw.get("decisions") or ()
        ),
        tokens_estimate=conv_raw["tokens_estimate"],
        truncated=conv_raw["truncated"],
    )
    return ContextPackage(
        request=request,
        repository=repository,
        conversation=conversation,
        tokens_estimate=data["tokens_estimate"],
        token_budget=data["token_budget"],
        truncated=data["truncated"],
        provenance=tuple(data.get("provenance") or ()),
        created_at=data["created_at"],
        cache_key=data["cache_key"],
    )


class ContextManager:
    """Composes a bounded, ranked context package. Never calls an LLM."""

    def __init__(
        self,
        rna: Any,
        conversation: Any,
        config: ContextConfig | None = None,
        *,
        repo_path: Path | None = None,
    ) -> None:
        self.rna = rna
        self.conversation = conversation
        self.config = config or ContextConfig()
        cache_root = self.config.resolved_cache_dir(repo_path)
        self._cache = PackageCache(
            cache_root,
            l1_size=self.config.l1_cache_size,
            enabled=self.config.cache_enabled,
        )
        self._analyzer = RequirementAnalyzer()
        self._planner = RetrievalPlanner(rna, conversation, self.config)
        self._aggregator = Aggregator()
        self._ranker = Ranker(self.config)
        self._compressor = Compressor(self.config)
        self._validator = Validator()
        self._repo_path = repo_path
        self.last_rna_calls: int = 0
        self.last_conversation_calls: int = 0

    def compose(
        self,
        *,
        repository: RepositoryContext | None = None,
        conversation: ConversationContext | None = None,
        budget: int | None = None,
        request: ContextRequest | None = None,
    ) -> ContextResult[ContextPackage]:
        with timed_call("compose", "compose") as log:
            req = request or ContextRequest(
                task_description="",
                task_complexity="MEDIUM",
                requesting_agent="planner",
            )
            repo_items = list(repository.items) if repository else []
            conv = conversation or ConversationContext(
                recent_messages=(),
                summary=None,
                relevant_history=(),
                decisions=(),
                tokens_estimate=0,
                truncated=False,
            )
            ranked = self._ranker.rank(repo_items, req)
            token_budget = budget or req.token_budget or self.config.max_context_tokens
            kept, conv_out, provenance, truncated = self._compressor.compress(
                ranked, conv, token_budget=token_budget
            )
            tokens = sum(i.tokens_estimate for i in kept) + conv_out.tokens_estimate
            provenance = self._validator.validate(
                req,
                kept,
                conv_out,
                tokens_estimate=tokens,
                token_budget=token_budget,
                provenance=provenance,
                session_id=getattr(self.conversation, "session_id", None),
            )
            degraded = bool(repository and repository.degraded)
            reason = repository.reason if repository else None
            package = ContextPackage(
                request=req,
                repository=RepositoryContext(
                    items=tuple(kept),
                    tokens_estimate=sum(i.tokens_estimate for i in kept),
                    truncated=truncated,
                    degraded=degraded,
                    reason=reason,
                ),
                conversation=conv_out,
                tokens_estimate=tokens,
                token_budget=token_budget,
                truncated=truncated,
                provenance=tuple(provenance),
                created_at=_now_iso(),
                cache_key="",
            )
            log.truncated = truncated
            log.degraded = degraded
            log.tokens_estimate = tokens
            log.sources = ("rna", "conversation")
            return ContextResult(
                data=package,
                meta=ContextMeta(
                    cost_ms=0.0,
                    cache_hit=False,
                    truncated=truncated,
                    degraded=degraded,
                    reason=reason,
                    tokens_estimate=tokens,
                    sources=("rna", "conversation"),
                ),
            )

    def resolve(self, request: ContextRequest) -> ContextResult[ContextPackage]:
        with timed_call("resolve", request.task_description[:80]) as log:
            log.requesting_agent = request.requesting_agent
            log.task_complexity = request.task_complexity

            repo_fp = self._repo_fingerprint()
            conv_hash = self._conversation_hash()
            req_fp = _request_fingerprint(request)
            key = self._cache.make_key(
                repo_fingerprint=repo_fp,
                conversation_state_hash=conv_hash,
                request_fingerprint=req_fp,
            )

            def compute() -> dict:
                return self._resolve_uncached(request, cache_key=key.as_str())

            payload, hit = self._cache.get_or_compute(key, compute, as_blob=True)
            package = _package_from_dict(payload) if isinstance(payload, dict) else payload
            if hit:
                self.last_rna_calls = 0
                self.last_conversation_calls = 0
            sources: tuple[str, ...] = ("cache",) if hit else ("rna", "conversation")
            log.cache_hit = hit
            log.truncated = package.truncated
            log.degraded = package.repository.degraded
            log.tokens_estimate = package.tokens_estimate
            log.sources = sources
            return ContextResult(
                data=package,
                meta=ContextMeta(
                    cost_ms=0.0,
                    cache_hit=hit,
                    truncated=package.truncated,
                    degraded=package.repository.degraded,
                    reason=package.repository.reason,
                    tokens_estimate=package.tokens_estimate,
                    sources=sources,
                ),
            )

    def expand(
        self, package: ContextPackage, *, additional: ContextRequest
    ) -> ContextResult[ContextPackage]:
        with timed_call("expand", additional.task_description[:80]) as log:
            # Re-resolve the delta and merge items
            delta = self.resolve(additional)
            merged_items = list(package.repository.items) + list(delta.data.repository.items)
            # Dedupe by (kind, source_method, str(payload)[:80])
            seen: set[str] = set()
            unique: list[RepositoryContextItem] = []
            for item in merged_items:
                k = f"{item.kind}:{item.source_method}:{str(item.payload)[:80]}"
                if k in seen:
                    continue
                seen.add(k)
                unique.append(item)
            merged_repo = RepositoryContext(
                items=tuple(unique),
                tokens_estimate=sum(i.tokens_estimate for i in unique),
                truncated=False,
                degraded=package.repository.degraded or delta.data.repository.degraded,
                reason=delta.data.repository.reason or package.repository.reason,
            )
            # Prefer fresher conversation
            conv = delta.data.conversation
            result = self.compose(
                repository=merged_repo,
                conversation=conv,
                budget=additional.token_budget or package.token_budget,
                request=additional,
            )
            log.truncated = result.meta.truncated
            log.tokens_estimate = result.meta.tokens_estimate
            return result

    def refresh(self, package: ContextPackage) -> ContextResult[ContextPackage]:
        scope = package.request.file_hints[0] if package.request.file_hints else None
        self.invalidate(scope)
        return self.resolve(package.request)

    def invalidate(self, scope: str | None = None) -> None:
        with timed_call("invalidate", f"scope={scope}"):
            # Full invalidate — scope-granular subject invalidation would need
            # tracking subject hashes per package; keep simple and correct.
            self._cache.invalidate_all()

    def cache(self, package: ContextPackage) -> None:
        with timed_call("cache", package.cache_key or "compose"):
            req_fp = _request_fingerprint(package.request)
            key = self._cache.make_key(
                repo_fingerprint=self._repo_fingerprint(),
                conversation_state_hash=self._conversation_hash(),
                request_fingerprint=req_fp,
            )
            packaged = ContextPackage(
                request=package.request,
                repository=package.repository,
                conversation=package.conversation,
                tokens_estimate=package.tokens_estimate,
                token_budget=package.token_budget,
                truncated=package.truncated,
                provenance=package.provenance,
                created_at=package.created_at,
                cache_key=key.as_str(),
            )
            self._cache.put(key, _package_to_dict(packaged), as_blob=True)

    def _resolve_uncached(self, request: ContextRequest, *, cache_key: str) -> dict:
        plan = self._analyzer.analyze(request)
        rna_results, conversation = self._planner.execute(plan, request)
        self.last_rna_calls = self._planner.last_rna_calls
        self.last_conversation_calls = self._planner.last_conversation_calls

        items = self._aggregator.aggregate(rna_results)
        repo = RepositoryContext(
            items=tuple(items),
            tokens_estimate=sum(i.tokens_estimate for i in items),
            truncated=False,
            degraded=self._planner.last_degraded,
            reason=self._planner.last_reason,
        )
        composed = self.compose(
            repository=repo,
            conversation=conversation,
            budget=request.token_budget,
            request=request,
        )
        package = ContextPackage(
            request=request,
            repository=composed.data.repository,
            conversation=composed.data.conversation,
            tokens_estimate=composed.data.tokens_estimate,
            token_budget=composed.data.token_budget,
            truncated=composed.data.truncated,
            provenance=composed.data.provenance,
            created_at=_now_iso(),
            cache_key=cache_key,
        )
        return _package_to_dict(package)

    def _repo_fingerprint(self) -> str:
        if self._repo_path is not None:
            try:
                from src.rna.repo_analyzer.fingerprint import repo_fingerprint

                return repo_fingerprint(self._repo_path)
            except Exception:
                return content_hash(str(self._repo_path))
        # FakeRna / tests — stable fingerprint
        return content_hash("no-repo")

    def _conversation_hash(self) -> str:
        if hasattr(self.conversation, "conversation_state_hash"):
            return self.conversation.conversation_state_hash()
        return "none"

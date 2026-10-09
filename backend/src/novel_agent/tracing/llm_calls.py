"""LLM call tracing with redaction (spec §11, §10.3)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.db.models import ContextItem, LlmCall, LlmCallContext

REDACTED = "[redacted]"
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "secret",
        "password",
        "access_token",
        "refresh_token",
        "session",
    }
)


def redact(value: Any) -> Any:
    """Recursively replace credentials before anything is persisted."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
                redacted[key] = REDACTED
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class TraceRecorder:
    """Persists llm_calls, context_items and llm_call_context rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_call(
        self,
        *,
        agent_key: str,
        model_profile_snapshot: dict[str, Any],
        request: dict[str, Any],
        run_id: UUID | None = None,
        node_id: UUID | None = None,
    ) -> LlmCall:
        call = LlmCall(
            run_id=run_id,
            node_id=node_id,
            agent_key=agent_key,
            model_profile_snapshot=redact(model_profile_snapshot),
            request_json=redact(request),
            usage_json={},
            status="pending",
        )
        self.session.add(call)
        await self.session.flush()
        return call

    async def complete_call(
        self,
        call: LlmCall,
        *,
        response: dict[str, Any],
        usage: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> LlmCall:
        call.response_json = redact(response)
        call.usage_json = redact(usage or {})
        call.latency_ms = latency_ms
        call.status = "succeeded"
        call.error = None
        await self.session.flush()
        return call

    async def fail_call(self, call: LlmCall, *, error: str, latency_ms: int | None = None) -> LlmCall:
        call.status = "failed"
        call.error = error[:2000]
        call.latency_ms = latency_ms
        await self.session.flush()
        return call

    async def record_context(
        self,
        call: LlmCall,
        *,
        project_id: UUID,
        items: list[dict[str, Any]],
    ) -> list[ContextItem]:
        """Persist retrieved context items and their rank/score for this call.

        Each item is a mapping with ``kind``, ``source_ref``, ``text``,
        ``metadata``, ``rank``, ``score`` and optional ``reason``. Items are
        deduplicated per (project, kind, source_ref) so the same project file is
        not stored once per agent call.
        """

        recorded: list[ContextItem] = []
        for item in items:
            context_item = (
                await self.session.execute(
                    select(ContextItem).where(
                        ContextItem.project_id == project_id,
                        ContextItem.kind == item["kind"],
                        ContextItem.source_ref == item["source_ref"],
                    )
                )
            ).scalar_one_or_none()
            metadata = item.get("metadata") or {}
            if context_item is None:
                context_item = ContextItem(
                    project_id=project_id,
                    kind=item["kind"],
                    source_ref=item["source_ref"],
                    text=item["text"],
                    item_metadata=metadata,
                )
                self.session.add(context_item)
                await self.session.flush()
            elif context_item.text != item["text"] or context_item.item_metadata != metadata:
                context_item.text = item["text"]
                context_item.item_metadata = metadata
                await self.session.flush()

            existing_link = await self.session.get(LlmCallContext, (call.id, context_item.id))
            if existing_link is None:
                self.session.add(
                    LlmCallContext(
                        llm_call_id=call.id,
                        context_item_id=context_item.id,
                        rank=int(item.get("rank", 0)),
                        score=float(item.get("score", 0.0)),
                        reason=item.get("reason"),
                    )
                )
            recorded.append(context_item)
        await self.session.flush()
        return recorded

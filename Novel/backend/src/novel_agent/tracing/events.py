"""Append-only event log and SSE serialization (spec §11)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.db.models import Event

# The spec (§11) requires at least these event types. Event types beyond the
# required list are additions allowed by "至少包括".
RUN_QUEUED = "run.queued"
RUN_STARTED = "run.started"
NODE_STARTED = "node.started"
LLM_CALL_STARTED = "llm_call.started"
LLM_CALL_COMPLETED = "llm_call.completed"
ARTIFACT_CREATED = "artifact.created"
QUALITY_GATE_FAILED = "quality_gate.failed"
NODE_COMPLETED = "node.completed"
RUN_WAITING_APPROVAL = "run.waiting_approval"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"

# Additions used by the M2 runtime.
RUN_CANCELLED = "run.cancelled"
RUN_REQUEUED = "run.requeued"
NODE_FAILED = "node.failed"
NODE_CANCELLED = "node.cancelled"
NODE_SKIPPED = "node.skipped"
NODE_RETRY_SCHEDULED = "node.retry_scheduled"
ARTIFACT_APPROVED = "artifact.approved"
ARTIFACT_REJECTED = "artifact.rejected"
ARTIFACT_SUPERSEDED = "artifact.superseded"

REQUIRED_EVENT_TYPES: tuple[str, ...] = (
    RUN_QUEUED,
    RUN_STARTED,
    NODE_STARTED,
    LLM_CALL_STARTED,
    LLM_CALL_COMPLETED,
    ARTIFACT_CREATED,
    QUALITY_GATE_FAILED,
    NODE_COMPLETED,
    RUN_WAITING_APPROVAL,
    RUN_COMPLETED,
    RUN_FAILED,
)

ADDITIONAL_EVENT_TYPES: tuple[str, ...] = (
    RUN_CANCELLED,
    RUN_REQUEUED,
    NODE_FAILED,
    NODE_CANCELLED,
    NODE_SKIPPED,
    NODE_RETRY_SCHEDULED,
    ARTIFACT_APPROVED,
    ARTIFACT_REJECTED,
    ARTIFACT_SUPERSEDED,
)

EVENT_TYPES: tuple[str, ...] = REQUIRED_EVENT_TYPES + ADDITIONAL_EVENT_TYPES


def _json_default(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def event_payload(event: Event) -> dict[str, Any]:
    """Serialize an event row for JSON APIs and SSE frames."""

    return {
        "id": str(event.id),
        "sequence": int(event.sequence),
        "project_id": str(event.project_id) if event.project_id else None,
        "run_id": str(event.run_id) if event.run_id else None,
        "node_id": str(event.node_id) if event.node_id else None,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "event_type": event.event_type,
        "payload": event.payload or {},
        "created_at": event.created_at.astimezone(timezone.utc).isoformat() if event.created_at else None,
    }


def to_sse(event: Event) -> str:
    """Render one event as an SSE frame with a resumable `id` (the sequence)."""

    body = json.dumps(event_payload(event), ensure_ascii=False, default=_json_default)
    return f"id: {int(event.sequence)}\nevent: {event.event_type}\ndata: {body}\n\n"


class EventLog:
    """Writes events inside the caller's transaction.

    Events are append-only: this class exposes no update or delete operation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def emit(
        self,
        event_type: str,
        *,
        project_id: UUID | None = None,
        run_id: UUID | None = None,
        node_id: UUID | None = None,
        actor_type: str = "system",
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unregistered event type: {event_type}")
        event = Event(
            project_id=project_id,
            run_id=run_id,
            node_id=node_id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event

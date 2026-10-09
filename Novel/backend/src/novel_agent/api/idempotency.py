"""Idempotency-Key support shared by all mutating endpoints (spec §5.3)."""

from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.core.errors import APIError
from novel_agent.db.models import Action


def idempotency_key(request: Request) -> str | None:
    value = request.headers.get("Idempotency-Key")
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 255:
        raise APIError("IDEMPOTENCY_KEY_TOO_LONG", "Idempotency-Key must be at most 255 characters.")
    return value


async def existing_action(session: AsyncSession, action_type: str, request: Request) -> Action | None:
    key = idempotency_key(request)
    if key is None:
        return None
    return (
        await session.execute(select(Action).where(Action.action_type == action_type, Action.request_id == key))
    ).scalar_one_or_none()


def record_action(
    session: AsyncSession,
    *,
    action_type: str,
    target_type: str,
    target_id: UUID,
    request: Request,
) -> None:
    session.add(
        Action(
            request_id=idempotency_key(request) or getattr(request.state, "request_id", None),
            actor_type="api",
            actor_id=None,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
        )
    )


async def commit_or_conflict(session: AsyncSession) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise APIError(
            "RESOURCE_CONFLICT",
            "The requested resource conflicts with an existing resource.",
            status_code=409,
        ) from exc


async def flush_or_conflict(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise APIError(
            "RESOURCE_CONFLICT",
            "The requested resource conflicts with an existing resource.",
            status_code=409,
        ) from exc

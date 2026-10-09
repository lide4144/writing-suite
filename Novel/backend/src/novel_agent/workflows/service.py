"""Run lifecycle service: creation, idempotency, production lock, cancel and retry."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.core.config import Settings
from novel_agent.core.errors import APIError
from novel_agent.db.models import Action, Event, Project, Run
from novel_agent.domain.states import ACTIVE_RUN_STATUSES, ensure_transition, is_terminal_run_status
from novel_agent.tracing.events import RUN_CANCELLED, RUN_QUEUED, RUN_REQUEUED, EventLog


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.events = EventLog(session)

    # ----------------------------------------------------------------- create
    async def create(
        self,
        *,
        project: Project,
        workflow_key: str,
        input_json: dict[str, Any] | None = None,
        mode: str = "normal",
        idempotency_key: str | None = None,
        request_id: str | None = None,
        actor_type: str = "api",
        actor_id: str | None = None,
        retry_of: UUID | None = None,
    ) -> tuple[Run, bool]:
        """Create a run. Returns (run, reused) where `reused` marks an idempotent replay."""

        if idempotency_key:
            existing = (
                await self.session.execute(
                    select(Action).where(
                        Action.action_type == "run.create", Action.request_id == idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None and existing.target_id is not None:
                run = await self.session.get(Run, existing.target_id)
                if run is not None:
                    return run, True

        input_payload = dict(input_json or {})
        if retry_of is not None:
            input_payload["retry_of"] = str(retry_of)
        chapter_number = input_payload.get("chapter_number")
        if chapter_number is not None:
            if not isinstance(chapter_number, int) or isinstance(chapter_number, bool) or chapter_number < 1:
                raise APIError(
                    "RUN_INPUT_INVALID",
                    "input.chapter_number must be a positive integer.",
                    status_code=422,
                )

        if project.kind == "production":
            await self._assert_no_active_run(project)

        run = Run(
            id=uuid4(),
            project_id=project.id,
            workflow_key=workflow_key,
            preset_version_id=project.active_preset_version_id,
            status="queued",
            mode=mode,
            idempotency_key=idempotency_key,
            input_json=input_payload,
        )
        self.session.add(run)
        await self.session.flush()
        if idempotency_key:
            self.session.add(
                Action(
                    request_id=idempotency_key,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    action_type="run.create",
                    target_type="run",
                    target_id=run.id,
                )
            )
        await self.events.emit(
            RUN_QUEUED,
            project_id=project.id,
            run_id=run.id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload={
                "workflow": workflow_key,
                "mode": mode,
                "request_id": request_id,
                "retry_of": str(retry_of) if retry_of else None,
            },
        )
        await self.session.commit()
        return run, False

    async def _assert_no_active_run(self, project: Project) -> None:
        """One mutating run per production project (spec §5.3).

        A transaction-scoped advisory lock serialises concurrent creations so two
        requests cannot both observe "no active run".
        """

        await self.session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"project-run:{project.id}"},
        )
        active = (
            await self.session.execute(
                select(Run.id)
                .where(Run.project_id == project.id, Run.status.in_(tuple(ACTIVE_RUN_STATUSES)))
                .limit(1)
            )
        ).scalar_one_or_none()
        if active is not None:
            raise APIError(
                "RUN_ALREADY_ACTIVE",
                "A mutating run is already active for this project.",
                status_code=409,
                details={"active_run_id": str(active)},
            )

    # ------------------------------------------------------------------- read
    async def get(self, run_id: UUID) -> Run:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise APIError("RUN_NOT_FOUND", "The requested run does not exist.", status_code=404)
        return run

    async def list_for_project(self, project_id: UUID, *, limit: int = 50) -> Sequence[Run]:
        statement = (
            select(Run)
            .where(Run.project_id == project_id)
            .order_by(Run.created_at.desc())
            .limit(limit)
        )
        return (await self.session.execute(statement)).scalars().all()

    async def events_since(self, run_id: UUID, *, after_sequence: int = 0, limit: int = 500) -> Sequence[Event]:
        statement = (
            select(Event)
            .where(Event.run_id == run_id, Event.sequence > after_sequence)
            .order_by(Event.sequence.asc())
            .limit(limit)
        )
        return (await self.session.execute(statement)).scalars().all()

    # ----------------------------------------------------------- transitions
    async def cancel(self, run_id: UUID, *, actor_type: str = "api", actor_id: str | None = None) -> Run:
        run = await self.get(run_id)
        if run.status in {"succeeded", "failed", "cancelled"}:
            return run
        ensure_transition("run", run.status, "cancelled")
        run.status = "cancelled"
        run.ended_at = _now()
        await self.events.emit(
            RUN_CANCELLED,
            project_id=run.project_id,
            run_id=run.id,
            actor_type=actor_type,
            actor_id=actor_id,
            payload={"previous_status": run.status if run.status == "cancelled" else "cancelled"},
        )
        await self.session.commit()
        return run

    async def retry(
        self, run_id: UUID, *, actor_type: str = "api", actor_id: str | None = None
    ) -> tuple[Run, bool]:
        """Retry a run.

        Returns ``(run, created_new)``.

        * `waiting_approval` resumes the same run (the state machine allows it).
        * `failed`/`cancelled` produce a **new** run: terminal states are final so
          the original attempt stays immutable and auditable.
        * active or successful runs cannot be retried.
        """

        run = await self.get(run_id)
        if run.status in {"queued", "running"}:
            raise APIError(
                "RUN_RETRY_NOT_ALLOWED",
                "The run is still active.",
                status_code=409,
                details={"run_id": str(run.id), "status": run.status},
            )
        if run.status == "succeeded":
            raise APIError(
                "RUN_RETRY_NOT_ALLOWED",
                "A successful run cannot be retried.",
                status_code=409,
                details={"run_id": str(run.id), "status": run.status},
            )

        if run.status == "waiting_approval":
            ensure_transition("run", "waiting_approval", "running")
            run.status = "running"
            run.error_code = None
            run.error_message = None
            run.ended_at = None
            await self.events.emit(
                RUN_REQUEUED,
                project_id=run.project_id,
                run_id=run.id,
                actor_type=actor_type,
                actor_id=actor_id,
                payload={"resume_from": run.current_node},
            )
            await self.session.commit()
            return run, False

        project = await self.session.get(Project, run.project_id)
        if project is None:
            raise APIError("PROJECT_NOT_FOUND", "The run's project does not exist.", status_code=404)
        input_json = dict(run.input_json or {})
        input_json.pop("retry_of", None)
        retried, _ = await self.create(
            project=project,
            workflow_key=run.workflow_key,
            input_json=input_json,
            mode=run.mode,
            actor_type=actor_type,
            actor_id=actor_id,
            retry_of=run.id,
        )
        return retried, True

    async def mark_failed(self, run_id: UUID, *, code: str, message: str) -> Run:
        run = await self.get(run_id)
        if is_terminal_run_status(run.status):
            return run
        run.status = "failed"
        run.error_code = code
        run.error_message = message
        run.ended_at = _now()
        await self.session.commit()
        return run

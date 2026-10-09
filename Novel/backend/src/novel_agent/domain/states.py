"""State machines for runs, nodes and artifacts (spec §5.2).

Every status change in the workflow runtime goes through :func:`ensure_transition`
so that illegal transitions are rejected instead of silently corrupting a run.
"""

from __future__ import annotations

from typing import Final

from novel_agent.core.errors import APIError

RUN_STATUSES: Final[tuple[str, ...]] = (
    "queued",
    "running",
    "waiting_approval",
    "succeeded",
    "failed",
    "cancelled",
)
NODE_STATUSES: Final[tuple[str, ...]] = (
    "pending",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "cancelled",
)
ARTIFACT_STATUSES: Final[tuple[str, ...]] = (
    "draft",
    "proposed",
    "approved",
    "rejected",
    "superseded",
)
CHAPTER_STATUSES: Final[tuple[str, ...]] = (
    "planned",
    "drafting",
    "reviewing",
    "approved",
    "published",
)

TERMINAL_RUN_STATUSES: Final[frozenset[str]] = frozenset({"succeeded", "failed", "cancelled"})
ACTIVE_RUN_STATUSES: Final[frozenset[str]] = frozenset({"queued", "running", "waiting_approval"})
TERMINAL_NODE_STATUSES: Final[frozenset[str]] = frozenset({"succeeded", "failed", "skipped", "cancelled"})

RUN_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "queued": frozenset({"running", "cancelled", "failed"}),
    "running": frozenset({"waiting_approval", "succeeded", "failed", "cancelled"}),
    # A waiting run resumes after an approval decision, or is abandoned.
    "waiting_approval": frozenset({"running", "succeeded", "failed", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
NODE_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "pending": frozenset({"running", "skipped", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "cancelled", "skipped"}),
    "succeeded": frozenset(),
    "failed": frozenset({"running", "cancelled"}),  # a new attempt reuses the row state machine
    "skipped": frozenset(),
    "cancelled": frozenset(),
}
ARTIFACT_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "draft": frozenset({"proposed", "approved", "rejected", "superseded"}),
    "proposed": frozenset({"approved", "rejected", "superseded"}),
    "approved": frozenset({"superseded"}),
    "rejected": frozenset({"superseded"}),
    "superseded": frozenset(),
}

_MACHINES: Final[dict[str, dict[str, frozenset[str]]]] = {
    "run": RUN_TRANSITIONS,
    "node": NODE_TRANSITIONS,
    "artifact": ARTIFACT_TRANSITIONS,
}


class IllegalStateTransition(APIError):
    """Raised when a caller attempts a transition the state machine forbids."""

    def __init__(self, machine: str, current: str, target: str) -> None:
        super().__init__(
            "ILLEGAL_STATE_TRANSITION",
            f"Cannot move {machine} from '{current}' to '{target}'.",
            status_code=409,
            details={"machine": machine, "current": current, "target": target},
        )
        self.machine = machine
        self.current = current
        self.target = target


def transitions_for(machine: str) -> dict[str, frozenset[str]]:
    try:
        return _MACHINES[machine]
    except KeyError as exc:  # pragma: no cover - programming error
        raise ValueError(f"Unknown state machine: {machine}") from exc


def allowed_targets(machine: str, current: str) -> frozenset[str]:
    return transitions_for(machine).get(current, frozenset())


def can_transition(machine: str, current: str, target: str) -> bool:
    if current == target:
        # Idempotent re-application of the same status is allowed; this keeps
        # at-least-once worker delivery from failing on a replayed transition.
        return current in transitions_for(machine)
    return target in allowed_targets(machine, current)


def ensure_transition(machine: str, current: str, target: str) -> None:
    """Raise :class:`IllegalStateTransition` unless ``current -> target`` is legal."""

    if not can_transition(machine, current, target):
        raise IllegalStateTransition(machine, current, target)


def is_terminal_run_status(status: str) -> bool:
    return status in TERMINAL_RUN_STATUSES


def is_active_run_status(status: str) -> bool:
    return status in ACTIVE_RUN_STATUSES

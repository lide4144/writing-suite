"""Domain layer: state machines and validation shared by API and worker."""

from novel_agent.domain.states import (
    ACTIVE_RUN_STATUSES,
    ARTIFACT_STATUSES,
    ARTIFACT_TRANSITIONS,
    CHAPTER_STATUSES,
    IllegalStateTransition,
    NODE_STATUSES,
    NODE_TRANSITIONS,
    RUN_STATUSES,
    RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    allowed_targets,
    can_transition,
    ensure_transition,
    is_active_run_status,
    is_terminal_run_status,
)

__all__ = [
    "ACTIVE_RUN_STATUSES",
    "ARTIFACT_STATUSES",
    "ARTIFACT_TRANSITIONS",
    "CHAPTER_STATUSES",
    "IllegalStateTransition",
    "NODE_STATUSES",
    "NODE_TRANSITIONS",
    "RUN_STATUSES",
    "RUN_TRANSITIONS",
    "TERMINAL_RUN_STATUSES",
    "allowed_targets",
    "can_transition",
    "ensure_transition",
    "is_active_run_status",
    "is_terminal_run_status",
]

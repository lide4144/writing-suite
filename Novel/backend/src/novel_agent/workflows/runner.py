"""Workflow runner: node execution, retries, cancellation and quality gates (spec §8, §16)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.artifacts.registry import ArtifactDraft, ArtifactRegistry
from novel_agent.core.config import Settings
from novel_agent.core.errors import APIError
from novel_agent.db.models import Artifact, PresetVersion, Project, Run, RunNode
from novel_agent.domain.states import ensure_transition
from novel_agent.projects.filesystem import ProjectFilesystem
from novel_agent.providers.base import LLMMessage, LLMRequest, ProviderError
from novel_agent.retrieval.context import ContextBuilder, ContextItemDraft, context_as_prompt_block
from novel_agent.tracing.events import (
    LLM_CALL_COMPLETED,
    LLM_CALL_STARTED,
    NODE_CANCELLED,
    NODE_COMPLETED,
    NODE_FAILED,
    NODE_RETRY_SCHEDULED,
    NODE_SKIPPED,
    NODE_STARTED,
    QUALITY_GATE_FAILED,
    RUN_CANCELLED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    RUN_WAITING_APPROVAL,
    EventLog,
)
from novel_agent.tracing.llm_calls import TraceRecorder
from novel_agent.workflows.definitions import (
    KIND_AGENT,
    KIND_APPROVAL,
    KIND_COMMIT,
    KIND_CONTEXT,
    KIND_GATE,
    KIND_TERMINAL,
    NodeSpec,
    WorkflowDefinition,
    get_workflow,
)

logger = logging.getLogger(__name__)

DEFAULT_QUALITY_GATE: dict[str, Any] = {
    "minimum": {
        "continuity": 0.95,
        "character_consistency": 0.85,
        "novelty": 0.65,
        "pacing": 0.65,
    },
    "hard_fail": (
        "forbidden_event_present",
        "required_fact_missing",
        "character_knows_unknown_fact",
        "style_editor_fact_change",
    ),
    "max_revision_iterations": 3,
}

AGENT_SYSTEM_PROMPTS: dict[str, str] = {
    "director": "You are the Director. Choose one candidate and justify it. Never let the Writer choose plot direction.",
    "plot_architect": "You maintain the rolling plan and the structure of the current chapter.",
    "idea": "You produce safe, moderate and wild candidates with risk, plausibility and canon dependencies.",
    "character": "You reason from the character's limited knowledge. Never grant knowledge they do not have.",
    "scene_planner": "You merge all constraints into one precise scene brief with explicit forbidden events.",
    "writer": "You write the fact-layer draft strictly inside the scene brief. Never contradict canon.",
    "continuity": "You check facts, timeline, knowledge state and character consistency, and report hard failures.",
    "critic": "You score tension, pacing, characterization, prose, novelty, emotional impact and continuity.",
    "revision": "You fix exactly the reported problems and never widen the scope of the draft.",
    "style_editor": "You change expression only. You must not add, remove or alter facts.",
    "canon_extractor": "You propose structured canon changes. You never apply them yourself.",
    "summarizer": "You summarize the approved chapter for future context.",
}


class NodeFailure(Exception):
    """A node exhausted its retries; the run must fail."""

    def __init__(self, node_key: str, code: str, message: str) -> None:
        super().__init__(message)
        self.node_key = node_key
        self.code = code
        self.message = message


@dataclass
class QualityGate:
    minimum: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_QUALITY_GATE["minimum"]))
    hard_fail: tuple[str, ...] = tuple(DEFAULT_QUALITY_GATE["hard_fail"])
    max_revision_iterations: int = int(DEFAULT_QUALITY_GATE["max_revision_iterations"])

    @classmethod
    def from_preset(cls, preset_content: dict[str, Any] | None) -> "QualityGate":
        gate = cls()
        if not preset_content:
            return gate
        raw = preset_content.get("quality_gate") or {}
        minimum = raw.get("minimum") or {}
        if isinstance(minimum, dict):
            gate.minimum.update({str(key): float(value) for key, value in minimum.items()})
        # The preset schema allows both `max_revision_iterations` and
        # `revision.max_iterations`; accept either.
        if isinstance(raw.get("max_revision_iterations"), int):
            gate.max_revision_iterations = int(raw["max_revision_iterations"])
        revision = raw.get("revision") or {}
        if isinstance(revision, dict) and isinstance(revision.get("max_iterations"), int):
            gate.max_revision_iterations = int(revision["max_iterations"])
        hard_fail = raw.get("hard_fail")
        if isinstance(hard_fail, list) and hard_fail:
            gate.hard_fail = tuple(str(item) for item in hard_fail)
        return gate

    def evaluate(self, *, continuity: dict[str, Any], critic: dict[str, Any]) -> dict[str, Any]:
        """Return a decision dict: passed, scores, failures, reasons."""

        scores: dict[str, float] = {}
        critic_scores = critic.get("scores") or {}
        for key, value in critic_scores.items():
            try:
                scores[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        if "continuity" not in scores and isinstance(continuity.get("score"), (int, float)):
            scores["continuity"] = float(continuity["score"])

        hard_failures = [str(item) for item in (continuity.get("hard_failures") or [])]
        unknown_failures = [item for item in hard_failures if item not in self.hard_fail]

        reasons: list[dict[str, Any]] = []
        for failure in hard_failures:
            reasons.append({"type": "hard_fail", "metric": failure})
        for metric, threshold in self.minimum.items():
            value = scores.get(metric)
            if value is None:
                continue
            if value < threshold:
                reasons.append({"type": "below_minimum", "metric": metric, "value": value, "minimum": threshold})

        return {
            "passed": not reasons,
            "scores": scores,
            "hard_failures": hard_failures,
            "unknown_hard_failures": unknown_failures,
            "reasons": reasons,
            "minimum": dict(self.minimum),
        }


@dataclass
class RunState:
    completed: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    revision_attempts: int = 0
    context_items: list[ContextItemDraft] = field(default_factory=list)
    context_item_ids: list[UUID] = field(default_factory=list)
    artifacts: dict[str, UUID] = field(default_factory=dict)

    @property
    def settled(self) -> set[str]:
        return self.completed | self.skipped


class RunExecutor:
    """Executes one workflow run inside the caller's session."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        provider: Any,
        *,
        auto_approve_sandbox: bool = True,
    ) -> None:
        self.session = session
        self.settings = settings
        self.provider = provider
        self.auto_approve_sandbox = auto_approve_sandbox
        self.registry = ArtifactRegistry(session, settings)
        self.filesystem = ProjectFilesystem(settings)
        self.events = EventLog(session)
        self.tracer = TraceRecorder(session)

    # ------------------------------------------------------------------ entry
    async def execute(self, run_id: UUID) -> Run:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise APIError("RUN_NOT_FOUND", "The requested run does not exist.", status_code=404)
        project = await self.session.get(Project, run.project_id)
        if project is None:
            raise APIError("PROJECT_NOT_FOUND", "The run's project does not exist.", status_code=404)

        preset_content = await self._preset_content(run.preset_version_id)
        gate = QualityGate.from_preset(preset_content)
        definition = get_workflow(run.workflow_key, max_revision_iterations=gate.max_revision_iterations)

        if run.status == "cancelled":
            return run
        origin = run.status
        ensure_transition("run", origin, "running")
        run.status = "running"
        run.started_at = run.started_at or _now()
        run.error_code = None
        run.error_message = None
        await self.session.commit()
        await self.events.emit(RUN_STARTED, project_id=run.project_id, run_id=run.id, payload={"mode": run.mode})
        await self.session.commit()

        state = RunState()
        await self._ensure_node_rows(run, definition)
        node_key = self._resume_entry(run, definition)
        try:
            while node_key is not None:
                if await self._is_cancelled(run):
                    await self._cancel_remaining(run, definition, state, node_key)
                    return await self._finish(run, "cancelled")
                spec = definition.node(node_key)
                decision = await self._execute_node(run=run, project=project, spec=spec, state=state, gate=gate)
                if decision == "escalate":
                    run.current_node = spec.key
                    await self.events.emit(
                        RUN_WAITING_APPROVAL,
                        project_id=run.project_id,
                        run_id=run.id,
                        payload={"node_key": spec.key, "reason": "revision_limit_exceeded"},
                    )
                    await self.session.commit()
                    return await self._finish(run, "waiting_approval")
                if decision == "await_approval":
                    run.current_node = spec.key
                    await self.session.commit()
                    return await self._finish(run, "waiting_approval")
                if decision == "rejected":
                    state.completed.add("canon_approval")
                    node_key = "keep_draft"
                    continue
                if decision == "revise":
                    # §8 routes the revision back into "Continuity + Critic" (Q),
                    # so the verifiers run again before the gate re-evaluates. The
                    # gate itself stays un-completed for the same reason.
                    state.completed.discard("continuity")
                    state.completed.discard("critic")
                    node_key = "revision"
                    continue
                if decision == "approved":
                    state.completed.add("canon_approval")
                    node_key = "canon_manager"
                    continue

                state.completed.add(spec.key)
                run.current_node = spec.key
                await self.session.commit()
                if spec.ends_workflow:
                    # Approval branches are exclusive and finish the workflow.
                    node_key = None
                    continue
                next_spec = definition.next_node_after(spec.key, state.settled)
                node_key = next_spec.key if next_spec else None

            return await self._finish(run, "succeeded")
        except NodeFailure as failure:
            run.error_code = failure.code
            run.error_message = failure.message
            await self.events.emit(
                RUN_FAILED,
                project_id=run.project_id,
                run_id=run.id,
                payload={"node_key": failure.node_key, "code": failure.code, "message": failure.message},
            )
            await self.session.commit()
            return await self._finish(run, "failed")
        except APIError as exc:
            run.error_code = exc.code
            run.error_message = exc.message
            await self.events.emit(
                RUN_FAILED,
                project_id=run.project_id,
                run_id=run.id,
                payload={"code": exc.code, "message": exc.message},
            )
            await self.session.commit()
            return await self._finish(run, "failed")

    # ------------------------------------------------------------- node kinds
    async def _execute_node(
        self,
        *,
        run: Run,
        project: Project,
        spec: NodeSpec,
        state: RunState,
        gate: QualityGate,
    ) -> str:
        if spec.kind == KIND_CONTEXT:
            return await self._run_context_node(run=run, project=project, spec=spec, state=state)
        if spec.kind == KIND_AGENT:
            return await self._run_agent_node(run=run, project=project, spec=spec, state=state)
        if spec.kind == KIND_GATE:
            return await self._run_gate_node(run=run, project=project, spec=spec, state=state, gate=gate)
        if spec.kind == KIND_APPROVAL:
            return await self._run_approval_node(run=run, project=project, spec=spec, state=state)
        if spec.kind == KIND_COMMIT:
            return await self._run_commit_node(run=run, project=project, spec=spec, state=state)
        if spec.kind == KIND_TERMINAL:
            return await self._run_terminal_node(run=run, project=project, spec=spec, state=state)
        raise NodeFailure(spec.key, "NODE_KIND_UNSUPPORTED", f"Unsupported node kind '{spec.kind}'.")

    async def _run_context_node(self, *, run: Run, project: Project, spec: NodeSpec, state: RunState) -> str:
        node = await self._start_node(run, spec, state, attempt=await self._next_attempt(run, spec.key))
        chapter_number = int((run.input_json or {}).get("chapter_number") or 1)
        builder = ContextBuilder(
            Path(project.root_path),
            token_budget=int(self.settings.context_token_budget),
            top_k=int(self.settings.context_retrieve_top_k),
        )
        items = builder.collect(query=f"chapter {chapter_number}")
        state.context_items = items
        node.status = "succeeded"
        node.ended_at = _now()
        node.output_artifact_ids = []
        await self.events.emit(
            NODE_COMPLETED,
            project_id=run.project_id,
            run_id=run.id,
            node_id=node.id,
            payload={"node_key": spec.key, "context_items": len(items), "sources": [i.source_ref for i in items]},
        )
        await self.session.commit()
        return "ok"

    async def _run_agent_node(self, *, run: Run, project: Project, spec: NodeSpec, state: RunState) -> str:
        attempt = await self._next_attempt(run, spec.key)
        node = await self._start_node(run, spec, state, attempt=attempt)
        agent_key = spec.agent_key or spec.key
        input_ids = [str(artifact_id) for artifact_id in state.artifacts.values()]
        # Provider retries are counted per execution, independent of the run_node
        # attempt number (which also grows across revision rounds).
        retries_left = max(spec.max_attempts - 1, 0)

        while True:
            request = self._build_request(spec, state, run)
            call = await self.tracer.start_call(
                agent_key=agent_key,
                model_profile_snapshot={
                    "model_name": request.model,
                    "provider": getattr(self.provider, "name", "unknown"),
                    "params": request.params,
                },
                request=request.as_trace_payload(),
                run_id=run.id,
                node_id=node.id,
            )
            await self.events.emit(
                LLM_CALL_STARTED,
                project_id=run.project_id,
                run_id=run.id,
                node_id=node.id,
                payload={"agent_key": agent_key, "llm_call_id": str(call.id), "attempt": attempt},
            )
            await self.session.commit()

            # Record the actual context each call saw (spec §11): sources, rank
            # and score are attached to the call, not just to the run.
            if state.context_items:
                recorded = await self.tracer.record_context(
                    call,
                    project_id=project.id,
                    items=[item.as_record() for item in state.context_items],
                )
                state.context_item_ids = [item.id for item in recorded]
                await self.session.commit()

            try:
                response = await self.provider.complete(request)
            except ProviderError as exc:
                await self.tracer.fail_call(call, error=f"{exc.code}: {exc.message}")
                if exc.retryable and retries_left > 0:
                    retries_left -= 1
                    node.status = "failed"
                    node.error_code = exc.code
                    node.error_message = exc.message
                    node.ended_at = _now()
                    await self.events.emit(
                        NODE_RETRY_SCHEDULED,
                        project_id=run.project_id,
                        run_id=run.id,
                        node_id=node.id,
                        payload={"node_key": spec.key, "attempt": attempt, "error_code": exc.code},
                    )
                    await self.session.commit()
                    attempt = await self._next_attempt(run, spec.key)
                    node = await self._start_node(run, spec, state, attempt=attempt)
                    continue
                node.status = "failed"
                node.error_code = exc.code
                node.error_message = exc.message
                node.ended_at = _now()
                await self.events.emit(
                    NODE_FAILED,
                    project_id=run.project_id,
                    run_id=run.id,
                    node_id=node.id,
                    payload={"node_key": spec.key, "attempt": attempt, "error_code": exc.code, "message": exc.message},
                )
                await self.session.commit()
                raise NodeFailure(spec.key, exc.code, exc.message) from exc

            await self.tracer.complete_call(
                call,
                response={"content": response.content, "raw": response.raw},
                usage=response.usage,
                latency_ms=response.latency_ms,
            )

            artifact_type = spec.produces[0]
            provenance = {
                "input_artifact_ids": input_ids,
                "context_item_ids": [str(item_id) for item_id in state.context_item_ids],
                "llm_call_ids": [str(call.id)],
            }
            parent_id = self._parent_for(artifact_type, state, spec)
            artifact = await self.registry.create(
                project=project,
                draft=ArtifactDraft(
                    type=artifact_type,
                    content=response.content,
                    producer=agent_key,
                    status="proposed" if artifact_type == "canon_patch" else "draft",
                    provenance=provenance,
                ),
                run_id=run.id,
                node_id=node.id,
                parent_id=parent_id,
            )
            state.artifacts[artifact_type] = artifact.id

            # Style Editor fact protection (spec §7): a fact change is a hard
            # failure that preserves the Writer/Revision draft.
            if artifact_type == "style_edit_result":
                fact_diff = (response.content or {}).get("fact_diff") or {}
                changed_keys = [key for key in ("added", "removed", "changed") if fact_diff.get(key)]
                if changed_keys:
                    node.status = "failed"
                    node.error_code = "STYLE_EDITOR_FACT_CHANGE"
                    node.error_message = f"Style Editor changed facts: {', '.join(changed_keys)}"
                    node.ended_at = _now()
                    node.output_artifact_ids = [str(artifact.id)]
                    await self.events.emit(
                        NODE_FAILED,
                        project_id=run.project_id,
                        run_id=run.id,
                        node_id=node.id,
                        payload={
                            "node_key": spec.key,
                            "attempt": attempt,
                            "error_code": node.error_code,
                            "fact_diff": fact_diff,
                        },
                    )
                    await self.session.commit()
                    raise NodeFailure(spec.key, node.error_code, node.error_message)

            node.status = "succeeded"
            node.ended_at = _now()
            node.output_artifact_ids = [str(artifact.id)]
            node.input_artifact_ids = input_ids
            await self.events.emit(
                LLM_CALL_COMPLETED,
                project_id=run.project_id,
                run_id=run.id,
                node_id=node.id,
                payload={
                    "agent_key": agent_key,
                    "llm_call_id": str(call.id),
                    "latency_ms": response.latency_ms,
                    "usage": response.usage,
                },
            )
            await self.events.emit(
                NODE_COMPLETED,
                project_id=run.project_id,
                run_id=run.id,
                node_id=node.id,
                payload={
                    "node_key": spec.key,
                    "attempt": attempt,
                    "artifact_id": str(artifact.id),
                    "artifact_type": artifact.type,
                },
            )
            await self.session.commit()

            if artifact_type == "canon_patch":
                await self._record_canon_patch_targets(project, artifact, state)
            return "ok"

    async def _run_gate_node(
        self, *, run: Run, project: Project, spec: NodeSpec, state: RunState, gate: QualityGate
    ) -> str:
        node = await self._start_node(run, spec, state, attempt=await self._next_attempt(run, spec.key))
        continuity = await self.registry.latest_for_run(run.id, "continuity_report")
        critic = await self.registry.latest_for_run(run.id, "critic_report")
        continuity_content = continuity.content_json if continuity else {}
        critic_content = critic.content_json if critic else {}

        # style_editor fact protection is evaluated when the style node ran.
        style_artifact = state.artifacts.get("style_edit_result")
        if style_artifact is not None:
            style = await self.session.get(Artifact, style_artifact)
            fact_diff = (style.content_json or {}).get("fact_diff") or {}
            if any(fact_diff.get(key) for key in ("added", "removed", "changed")):
                continuity_content = dict(continuity_content)
                continuity_content["hard_failures"] = list(continuity_content.get("hard_failures") or []) + [
                    "style_editor_fact_change"
                ]

        decision = gate.evaluate(continuity=continuity_content, critic=critic_content)
        node.input_artifact_ids = [
            str(artifact.id) for artifact in (continuity, critic) if artifact is not None
        ]
        node.ended_at = _now()
        node.status = "succeeded"

        if decision["passed"]:
            await self.events.emit(
                NODE_COMPLETED,
                project_id=run.project_id,
                run_id=run.id,
                node_id=node.id,
                payload={"node_key": spec.key, "decision": "pass", "scores": decision["scores"]},
            )
            await self.session.commit()
            return "pass"

        await self.events.emit(
            QUALITY_GATE_FAILED,
            project_id=run.project_id,
            run_id=run.id,
            node_id=node.id,
            payload={
                "node_key": spec.key,
                "reasons": decision["reasons"],
                "scores": decision["scores"],
                "hard_failures": decision["hard_failures"],
                "revision_attempts": state.revision_attempts,
                "max_revision_iterations": gate.max_revision_iterations,
            },
        )
        if state.revision_attempts < gate.max_revision_iterations:
            state.revision_attempts += 1
            await self.session.commit()
            return "revise"
        await self.session.commit()
        return "escalate"

    async def _run_approval_node(self, *, run: Run, project: Project, spec: NodeSpec, state: RunState) -> str:
        node = await self._start_node(run, spec, state, attempt=await self._next_attempt(run, spec.key))
        patch_id = state.artifacts.get("canon_patch")
        patch = await self.session.get(Artifact, patch_id) if patch_id else None
        if patch is None:
            patch = await self.registry.latest_for_run(run.id, "canon_patch")
        if patch is not None:
            state.artifacts["canon_patch"] = patch.id
            node.input_artifact_ids = [str(patch.id)]

        if patch is not None and patch.status == "approved":
            node.status = "succeeded"
            node.ended_at = _now()
            await self.session.commit()
            return "approved"
        if patch is not None and patch.status == "rejected":
            node.status = "succeeded"
            node.ended_at = _now()
            await self.session.commit()
            return "rejected"

        if project.kind == "sandbox" and self.auto_approve_sandbox and patch is not None:
            await self.registry.approve(patch.id, actor_type="system", actor_id="sandbox_auto_approval")
            node.status = "succeeded"
            node.ended_at = _now()
            await self.events.emit(
                NODE_COMPLETED,
                project_id=run.project_id,
                run_id=run.id,
                node_id=node.id,
                payload={"node_key": spec.key, "decision": "auto_approved", "artifact_id": str(patch.id)},
            )
            await self.session.commit()
            return "approved"

        node.status = "succeeded"
        node.ended_at = _now()
        await self.session.commit()
        # Production projects wait for an explicit approval decision.
        return "await_approval"

    async def _run_commit_node(self, *, run: Run, project: Project, spec: NodeSpec, state: RunState) -> str:
        node = await self._start_node(run, spec, state, attempt=await self._next_attempt(run, spec.key))
        chapter_number = int((run.input_json or {}).get("chapter_number") or 1)
        directory = f"chapters/{chapter_number:04d}"
        root = Path(project.root_path)
        artifact_ids: list[str] = []

        draft = await self._artifact_from_state(state, "chapter_draft")
        style = await self._artifact_from_state(state, "style_edit_result")
        summary = await self._artifact_from_state(state, "chapter_summary")
        brief = await self._artifact_from_state(state, "scene_brief")

        final_text = None
        if style is not None:
            final_text = (style.content_json or {}).get("text")
        if not final_text and draft is not None:
            final_text = (draft.content_json or {}).get("text")

        if final_text:
            self.filesystem.write_text(root, f"{directory}/final.md", final_text)
        if draft is not None:
            self.filesystem.write_text(
                root, f"{directory}/draft.md", str((draft.content_json or {}).get("text") or "")
            )
            artifact_ids.append(str(draft.id))
        if brief is not None:
            self.filesystem.write_json(root, f"{directory}/brief.json", brief.content_json)
            artifact_ids.append(str(brief.id))

        if summary is None:
            summary = await self._summarize(run=run, project=project, node=node, state=state, draft=draft)
        if summary is not None:
            self.filesystem.write_text(
                root, f"{directory}/summary.md", str((summary.content_json or {}).get("summary") or "")
            )
            artifact_ids.append(str(summary.id))

        patch = await self._artifact_from_state(state, "canon_patch")
        if patch is not None:
            artifact_ids.append(str(patch.id))
            self.filesystem.write_json(root, f"{directory}/canon_patch.json", patch.content_json)
            await self._apply_canon_patch(project, patch)

        commit = self.filesystem.commit_paths(
            root,
            [directory],
            f"feat(chapter): generate chapter {chapter_number}\n\n"
            f"Run-Id: {run.id}\n"
            f"Artifact-Ids: {', '.join(artifact_ids)}\n",
        )
        node.status = "succeeded"
        node.ended_at = _now()
        node.output_artifact_ids = artifact_ids
        await self.events.emit(
            NODE_COMPLETED,
            project_id=run.project_id,
            run_id=run.id,
            node_id=node.id,
            payload={"node_key": spec.key, "git_commit": commit, "chapter_number": chapter_number},
        )
        await self.session.commit()
        return "ok"

    async def _run_terminal_node(self, *, run: Run, project: Project, spec: NodeSpec, state: RunState) -> str:
        node = await self._start_node(run, spec, state, attempt=await self._next_attempt(run, spec.key))
        node.status = "succeeded"
        node.ended_at = _now()
        await self.events.emit(
            NODE_COMPLETED,
            project_id=run.project_id,
            run_id=run.id,
            node_id=node.id,
            payload={"node_key": spec.key, "decision": "keep_draft_for_human_edit"},
        )
        await self.session.commit()
        return "ok"

    # --------------------------------------------------------------- helpers
    async def _summarize(
        self, *, run: Run, project: Project, node: RunNode, state: RunState, draft: Artifact | None
    ) -> Artifact | None:
        """Generate the chapter summary when the workflow definition has no node for it."""

        if draft is None:
            return None
        request = LLMRequest(
            agent_key="summarizer",
            node_key="canon_manager",
            messages=[
                LLMMessage(role="system", content=AGENT_SYSTEM_PROMPTS["summarizer"]),
                LLMMessage(role="user", content=f"Summarize chapter {run.input_json.get('chapter_number')}."),
            ],
            model=self._model_for("summarizer"),
            params=self._params(),
        )
        call = await self.tracer.start_call(
            agent_key="summarizer",
            model_profile_snapshot={
                "model_name": request.model,
                "provider": getattr(self.provider, "name", "unknown"),
                "params": request.params,
            },
            request=request.as_trace_payload(),
            run_id=run.id,
            node_id=node.id,
        )
        try:
            response = await self.provider.complete(request)
        except ProviderError as exc:
            await self.tracer.fail_call(call, error=f"{exc.code}: {exc.message}")
            await self.session.commit()
            return None
        await self.tracer.complete_call(
            call, response={"content": response.content}, usage=response.usage, latency_ms=response.latency_ms
        )
        artifact = await self.registry.create(
            project=project,
            draft=ArtifactDraft(
                type="chapter_summary",
                content=response.content,
                producer="summarizer",
                provenance={"llm_call_ids": [str(call.id)], "input_artifact_ids": [str(draft.id)]},
            ),
            run_id=run.id,
            node_id=node.id,
            parent_id=None,
        )
        state.artifacts["chapter_summary"] = artifact.id
        await self.session.commit()
        return artifact

    async def _apply_canon_patch(self, project: Project, patch: Artifact) -> None:
        """Apply an approved canon patch to the project's canon files (Canon Manager is the only writer)."""

        root = Path(project.root_path)
        operations = (patch.content_json or {}).get("operations") or []
        facts_path = root / "canon" / "facts.yaml"
        try:
            import yaml

            current = yaml.safe_load(facts_path.read_text(encoding="utf-8")) or {}
        except (OSError, Exception):  # noqa: BLE001 - a missing/invalid canon file starts empty
            current = {}
        if not isinstance(current, dict):
            current = {}
        facts = list(current.get("facts") or [])
        applied = 0
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            name = str(operation.get("canonical_name") or "")
            if not name:
                continue
            entry = {
                "name": name,
                "entity_type": operation.get("entity_type"),
                "data": operation.get("data") or {},
                "source_artifact_id": str(patch.id),
            }
            if operation.get("op") == "delete":
                facts = [fact for fact in facts if fact.get("name") != name]
            else:
                facts = [fact for fact in facts if fact.get("name") != name]
                facts.append(entry)
            applied += 1
        current["facts"] = facts
        self.filesystem.write_text(
            root,
            "canon/facts.yaml",
            yaml.safe_dump(current, allow_unicode=True, sort_keys=False),
        )
        logger.info("applied canon patch", extra={"applied_operations": applied})

    async def _record_canon_patch_targets(self, project: Project, artifact: Artifact, state: RunState) -> None:
        # Reserved for M3 canon conflict checks; M2 only records the proposal.
        return None

    async def _artifact_from_state(self, state: RunState, artifact_type: str) -> Artifact | None:
        artifact_id = state.artifacts.get(artifact_type)
        if artifact_id is None:
            return None
        return await self.session.get(Artifact, artifact_id)

    def _parent_for(self, artifact_type: str, state: RunState, spec: NodeSpec) -> UUID | None:
        if spec.agent_key == "revision":
            return state.artifacts.get("chapter_draft")
        return None

    def _build_request(self, spec: NodeSpec, state: RunState, run: Run) -> LLMRequest:
        agent_key = spec.agent_key or spec.key
        chapter_number = int((run.input_json or {}).get("chapter_number") or 1)
        context_block = context_as_prompt_block(state.context_items)
        required = ", ".join(spec.produces)
        user_content = (
            f"Chapter {chapter_number}. Produce a valid '{required}' object.\n\n"
            f"Project context:\n{context_block or '(no context)'}"
        )
        return LLMRequest(
            agent_key=agent_key,
            node_key=spec.key,
            messages=[
                LLMMessage(role="system", content=AGENT_SYSTEM_PROMPTS.get(agent_key, "You are a novel agent.")),
                LLMMessage(role="user", content=user_content),
            ],
            model=self._model_for(agent_key),
            params=self._params(),
        )

    def _model_for(self, agent_key: str) -> str:
        return f"fake::{agent_key}"

    def _params(self) -> dict[str, Any]:
        # Deterministic debug mode: temperature 0 (spec §11.1).
        return {"temperature": 0, "top_p": 1, "seed": 0}

    async def _start_node(self, run: Run, spec: NodeSpec, state: RunState, *, attempt: int) -> RunNode:
        """Move a node to `running`.

        Pending rows are created for every workflow node when the run starts, so
        cancellation can propagate to nodes that never began and the UI can show
        the full node list immediately.
        """

        node = (
            await self.session.execute(
                select(RunNode).where(
                    RunNode.run_id == run.id,
                    RunNode.node_key == spec.key,
                    RunNode.attempt == attempt,
                )
            )
        ).scalar_one_or_none()
        if node is None:
            node = RunNode(
                run_id=run.id,
                node_key=spec.key,
                attempt=attempt,
                status="running",
                input_artifact_ids=[],
                output_artifact_ids=[],
                started_at=_now(),
            )
            self.session.add(node)
        else:
            ensure_transition("node", node.status, "running")
            node.status = "running"
            node.started_at = node.started_at or _now()
        await self.session.flush()
        run.current_node = spec.key
        await self.events.emit(
            NODE_STARTED,
            project_id=run.project_id,
            run_id=run.id,
            node_id=node.id,
            payload={"node_key": spec.key, "attempt": attempt, "kind": spec.kind},
        )
        await self.session.commit()
        return node

    async def _ensure_node_rows(self, run: Run, definition: WorkflowDefinition) -> None:
        existing = set(
            (
                await self.session.execute(select(RunNode.node_key).where(RunNode.run_id == run.id))
            ).scalars().all()
        )
        created = False
        for spec in definition.topological_order():
            if spec.key in existing:
                continue
            self.session.add(
                RunNode(
                    run_id=run.id,
                    node_key=spec.key,
                    attempt=1,
                    status="pending",
                    input_artifact_ids=[],
                    output_artifact_ids=[],
                )
            )
            created = True
        if created:
            await self.session.flush()
            await self.session.commit()

    async def _next_attempt(self, run: Run, node_key: str) -> int:
        """Lowest attempt number that is not finished yet."""

        rows = (
            await self.session.execute(
                select(RunNode.attempt, RunNode.status).where(
                    RunNode.run_id == run.id, RunNode.node_key == node_key
                )
            )
        ).all()
        if not rows:
            return 1
        last_attempt, last_status = max(rows, key=lambda row: row[0])
        return int(last_attempt) if last_status == "pending" else int(last_attempt) + 1

    async def _is_cancelled(self, run: Run) -> bool:
        await self.session.refresh(run, attribute_names=["status"])
        return run.status == "cancelled"

    async def _cancel_remaining(
        self, run: Run, definition: WorkflowDefinition, state: RunState, current_key: str
    ) -> None:
        rows = (
            await self.session.execute(select(RunNode).where(RunNode.run_id == run.id))
        ).scalars().all()
        for node in rows:
            if node.status in {"pending", "running"}:
                node.status = "cancelled"
                node.ended_at = node.ended_at or _now()
                await self.events.emit(
                    NODE_CANCELLED,
                    project_id=run.project_id,
                    run_id=run.id,
                    node_id=node.id,
                    payload={"node_key": node.node_key},
                )
        await self.events.emit(
            RUN_CANCELLED,
            project_id=run.project_id,
            run_id=run.id,
            actor_type="api",
            payload={"cancelled_at_node": current_key},
        )
        await self.session.commit()

    async def _finish(self, run: Run, target: str) -> Run:
        # `waiting_approval` is a pause, not an end: its nodes must stay pending
        # so the resumed run can still execute them.
        if target in {"succeeded", "failed", "cancelled"}:
            await self._skip_unreached_nodes(run)
        ensure_transition("run", run.status, target)
        run.status = target
        if target in {"succeeded", "failed", "cancelled"}:
            run.ended_at = _now()
        await self.session.flush()
        if target == "succeeded":
            await self.events.emit(
                RUN_COMPLETED,
                project_id=run.project_id,
                run_id=run.id,
                payload={"current_node": run.current_node},
            )
        await self.session.commit()
        return run

    async def _skip_unreached_nodes(self, run: Run) -> None:
        """Nodes that no branch selected end as `skipped`, never as stale `pending`."""

        rows = (
            await self.session.execute(
                select(RunNode).where(RunNode.run_id == run.id, RunNode.status == "pending")
            )
        ).scalars().all()
        for node in rows:
            node.status = "skipped"
            node.ended_at = _now()
            await self.events.emit(
                NODE_SKIPPED,
                project_id=run.project_id,
                run_id=run.id,
                node_id=node.id,
                payload={"node_key": node.node_key, "reason": "branch_not_taken"},
            )
        if rows:
            await self.session.flush()

    def _resume_entry(self, run: Run, definition: WorkflowDefinition) -> str:
        """Decide where to start: fresh run, or resume after an approval decision."""

        if not run.current_node or run.current_node == "director":
            return definition.topological_order()[0].key
        if run.current_node == "canon_approval":
            return "canon_approval"
        return run.current_node

    async def _preset_content(self, preset_version_id: UUID | None) -> dict[str, Any] | None:
        if preset_version_id is None:
            return None
        preset_version = await self.session.get(PresetVersion, preset_version_id)
        if preset_version is None:
            return None
        return preset_version.content_json


def _now() -> datetime:
    return datetime.now(timezone.utc)

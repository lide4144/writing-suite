"""Built-in workflow definitions and DAG validation (spec §8, §5.1)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from novel_agent.core.errors import APIError

WORKFLOW_SCHEMA_VERSION = "1.0"

# Node kinds understood by the runner.
KIND_CONTEXT = "context"
KIND_AGENT = "agent"
KIND_GATE = "gate"
KIND_APPROVAL = "approval"
KIND_COMMIT = "commit"
KIND_TERMINAL = "terminal"

ENTRY_NODE = "director"


@dataclass(frozen=True)
class NodeSpec:
    key: str
    kind: str
    depends_on: tuple[str, ...] = ()
    agent_key: str | None = None
    produces: tuple[str, ...] = ()
    max_attempts: int = 1
    optional: bool = False
    branch_only: bool = False
    ends_workflow: bool = False
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "depends_on": list(self.depends_on),
            "agent_key": self.agent_key,
            "produces": list(self.produces),
            "max_attempts": self.max_attempts,
            "optional": self.optional,
            "branch_only": self.branch_only,
            "ends_workflow": self.ends_workflow,
            "description": self.description,
            "config": self.config,
        }


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    nodes: tuple[NodeSpec, ...]
    schema_version: str = WORKFLOW_SCHEMA_VERSION

    def node(self, key: str) -> NodeSpec:
        for spec in self.nodes:
            if spec.key == key:
                return spec
        raise APIError("WORKFLOW_NODE_NOT_FOUND", f"Unknown workflow node '{key}'.", status_code=404)

    def node_keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.nodes)

    def validate(self) -> None:
        keys = self.node_keys()
        if len(set(keys)) != len(keys):
            raise APIError("WORKFLOW_DEFINITION_INVALID", "Workflow node keys must be unique.", status_code=500)
        known = set(keys)
        for spec in self.nodes:
            for dependency in spec.depends_on:
                if dependency not in known:
                    raise APIError(
                        "WORKFLOW_DEFINITION_INVALID",
                        f"Node '{spec.key}' depends on unknown node '{dependency}'.",
                        status_code=500,
                    )
            if spec.kind == KIND_AGENT and not spec.agent_key:
                raise APIError(
                    "WORKFLOW_DEFINITION_INVALID",
                    f"Agent node '{spec.key}' must declare an agent_key.",
                    status_code=500,
                )
        # Cycle detection over the declared dependency edges.
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(node_key: str) -> None:
            if node_key in permanent:
                return
            if node_key in temporary:
                raise APIError(
                    "WORKFLOW_DEFINITION_INVALID",
                    f"Workflow contains a dependency cycle at '{node_key}'.",
                    status_code=500,
                )
            temporary.add(node_key)
            for dependency in self.node(node_key).depends_on:
                visit(dependency)
            temporary.discard(node_key)
            permanent.add(node_key)

        for key in keys:
            visit(key)

    def topological_order(self) -> list[NodeSpec]:
        """Stable topological order (declaration order breaks ties)."""

        ordered: list[NodeSpec] = []
        placed: set[str] = set()
        remaining = list(self.nodes)
        while remaining:
            progressed = False
            for spec in list(remaining):
                if all(dependency in placed for dependency in spec.depends_on):
                    ordered.append(spec)
                    placed.add(spec.key)
                    remaining.remove(spec)
                    progressed = True
            if not progressed:  # pragma: no cover - validate() rejects cycles first
                raise APIError("WORKFLOW_DEFINITION_INVALID", "Workflow is not a DAG.", status_code=500)
        return ordered

    def dependents_of(self, key: str) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.nodes if key in spec.depends_on)

    def next_node_after(self, key: str, completed: Iterable[str]) -> NodeSpec | None:
        """Next node whose dependencies are all satisfied, in stable order.

        Branch-only nodes (revision, keep_draft) are never selected here: they are
        reached exclusively through an explicit quality-gate or approval decision.
        """

        done = set(completed)
        done.add(key)
        for spec in self.topological_order():
            if spec.key in done or spec.branch_only:
                continue
            if all(dependency in done for dependency in spec.depends_on):
                return spec
        return None

    def to_dag_json(self) -> dict[str, Any]:
        return {
            "workflow_key": self.key,
            "schema_version": self.schema_version,
            "entry_node": ENTRY_NODE,
            "nodes": [spec.as_dict() for spec in self.nodes],
        }

    def content_hash(self) -> str:
        canonical = json.dumps(self.to_dag_json(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def chapter_generation_workflow(*, max_revision_iterations: int = 3) -> WorkflowDefinition:
    """The §8 chapter generation DAG, parameterised by the preset quality gate."""

    nodes = (
        NodeSpec(
            key="director",
            kind=KIND_AGENT,
            agent_key="director",
            produces=("director_decision",),
            description="Decide the goal, branch and whether to retry or pause.",
            max_attempts=2,
        ),
        NodeSpec(
            key="retrieve_context",
            kind=KIND_CONTEXT,
            depends_on=("director",),
            description="Collect only the context this chapter needs.",
        ),
        NodeSpec(
            key="plot_architect",
            kind=KIND_AGENT,
            depends_on=("director", "retrieve_context"),
            agent_key="plot_architect",
            produces=("plot_plan",),
            description="Maintain the rolling plan and chapter structure.",
            max_attempts=2,
        ),
        NodeSpec(
            key="idea",
            kind=KIND_AGENT,
            depends_on=("plot_architect",),
            agent_key="idea",
            produces=("idea_candidates",),
            description="Produce safe/moderate/wild candidates (at least 10).",
            max_attempts=2,
        ),
        NodeSpec(
            key="character",
            kind=KIND_AGENT,
            depends_on=("plot_architect",),
            agent_key="character",
            produces=("character_intent",),
            description="Derive intent and reaction from limited character knowledge.",
            max_attempts=2,
        ),
        NodeSpec(
            key="scene_planner",
            kind=KIND_AGENT,
            depends_on=("idea", "character"),
            agent_key="scene_planner",
            produces=("scene_brief",),
            description="Merge constraints into a precise scene brief.",
            max_attempts=2,
        ),
        NodeSpec(
            key="writer",
            kind=KIND_AGENT,
            depends_on=("scene_planner",),
            agent_key="writer",
            produces=("chapter_draft",),
            description="Write the fact-layer draft inside the brief sandbox.",
            max_attempts=2,
        ),
        NodeSpec(
            key="continuity",
            kind=KIND_AGENT,
            depends_on=("writer",),
            agent_key="continuity",
            produces=("continuity_report",),
            description="Check facts, timeline, knowledge state and character consistency.",
            max_attempts=2,
        ),
        NodeSpec(
            key="critic",
            kind=KIND_AGENT,
            depends_on=("writer",),
            agent_key="critic",
            produces=("critic_report",),
            description="Score tension, pacing, novelty and prose.",
            max_attempts=2,
        ),
        NodeSpec(
            key="quality_gate",
            kind=KIND_GATE,
            depends_on=("continuity", "critic"),
            description="Merge verifier output and decide pass / revise / escalate.",
            config={"max_revision_iterations": max_revision_iterations},
        ),
        NodeSpec(
            key="revision",
            kind=KIND_AGENT,
            depends_on=("quality_gate",),
            agent_key="revision",
            produces=("chapter_draft",),
            branch_only=True,
            description="Revise only the reported problems; never widen scope.",
            max_attempts=2,
        ),
        NodeSpec(
            key="style_editor",
            kind=KIND_AGENT,
            depends_on=("quality_gate",),
            agent_key="style_editor",
            produces=("style_edit_result",),
            description="Change expression only; facts must not change.",
            max_attempts=2,
        ),
        NodeSpec(
            key="canon_extractor",
            kind=KIND_AGENT,
            depends_on=("style_editor",),
            agent_key="canon_extractor",
            produces=("canon_patch",),
            description="Propose structured canon changes from the approved draft.",
            max_attempts=2,
        ),
        NodeSpec(
            key="canon_approval",
            kind=KIND_APPROVAL,
            depends_on=("canon_extractor",),
            description="Human (production) or automatic (sandbox) approval of the canon patch.",
        ),
        NodeSpec(
            key="canon_manager",
            kind=KIND_COMMIT,
            depends_on=("canon_approval",),
            branch_only=True,
            ends_workflow=True,
            description="Apply the approved patch, write chapter files and commit to Git.",
        ),
        NodeSpec(
            key="keep_draft",
            kind=KIND_TERMINAL,
            depends_on=("canon_approval",),
            branch_only=True,
            ends_workflow=True,
            description="Keep the draft for human editing when the patch is rejected.",
        ),
    )
    definition = WorkflowDefinition(key="chapter_generation", nodes=nodes)
    definition.validate()
    return definition


BUILTIN_WORKFLOWS: dict[str, Any] = {
    "chapter_generation": chapter_generation_workflow,
}


def get_workflow(workflow_key: str, *, max_revision_iterations: int = 3) -> WorkflowDefinition:
    if workflow_key != "chapter_generation":
        raise APIError("WORKFLOW_NOT_FOUND", f"Unknown workflow '{workflow_key}'.", status_code=404)
    return chapter_generation_workflow(max_revision_iterations=max_revision_iterations)

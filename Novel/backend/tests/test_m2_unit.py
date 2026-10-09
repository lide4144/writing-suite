"""Pure M2 unit tests: state machines, workflow DAG, quality gate, retrieval,
providers, redaction and content hashing.

Every test in this module is self-contained and side-effect free: no database,
no Redis, no HTTP, no filesystem writes outside ``tmp_path``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from novel_agent.artifacts.registry import canonical_content_hash
from novel_agent.artifacts.schemas import ArtifactSchemaRegistry
from novel_agent.core.errors import APIError
from novel_agent.domain.states import (
    ACTIVE_RUN_STATUSES,
    ARTIFACT_STATUSES,
    ARTIFACT_TRANSITIONS,
    NODE_STATUSES,
    NODE_TRANSITIONS,
    RUN_STATUSES,
    RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    IllegalStateTransition,
    allowed_targets,
    can_transition,
    ensure_transition,
    is_active_run_status,
    is_terminal_run_status,
    transitions_for,
)
from novel_agent.providers.base import LLMMessage, LLMRequest, ProviderError
from novel_agent.providers.fake import FAULT_TYPES, FakeProvider
from novel_agent.providers.recorded import RecordedProvider
from novel_agent.retrieval.context import ContextBuilder, estimate_tokens
from novel_agent.tracing.llm_calls import REDACTED, redact
from novel_agent.workflows.definitions import NodeSpec, chapter_generation_workflow
from novel_agent.workflows.runner import DEFAULT_QUALITY_GATE, QualityGate

ARTIFACT_SCHEMAS_ROOT = Path("/home/lide/Novel/schemas/artifacts")

_MACHINE_TABLES: dict[str, dict[str, frozenset[str]]] = {
    "run": RUN_TRANSITIONS,
    "node": NODE_TRANSITIONS,
    "artifact": ARTIFACT_TRANSITIONS,
}

_MACHINE_STATUSES: dict[str, tuple[str, ...]] = {
    "run": RUN_STATUSES,
    "node": NODE_STATUSES,
    "artifact": ARTIFACT_STATUSES,
}


def _request(agent_key: str, *, node_key: str = "test_node") -> LLMRequest:
    return LLMRequest(
        agent_key=agent_key,
        node_key=node_key,
        messages=[LLMMessage(role="user", content="unit test prompt")],
    )


# ---------------------------------------------------------------------------
# 1. State machines
# ---------------------------------------------------------------------------
def _declared_transitions() -> list[tuple[str, str, str]]:
    return [
        (machine, current, target)
        for machine, table in _MACHINE_TABLES.items()
        for current, targets in table.items()
        for target in sorted(targets)
    ]


@pytest.mark.parametrize(
    ("machine", "current", "target"),
    _declared_transitions(),
    ids=lambda value: str(value),
)
def test_declared_transition_is_allowed(machine: str, current: str, target: str) -> None:
    assert can_transition(machine, current, target) is True
    assert target in allowed_targets(machine, current)
    ensure_transition(machine, current, target)  # must not raise


_ILLEGAL_TRANSITIONS: list[tuple[str, str, str]] = [
    ("run", "succeeded", "running"),
    ("run", "succeeded", "queued"),
    ("run", "failed", "waiting_approval"),
    ("run", "cancelled", "running"),
    ("run", "queued", "waiting_approval"),
    ("run", "queued", "succeeded"),
    ("run", "waiting_approval", "queued"),
    ("node", "pending", "succeeded"),
    ("node", "succeeded", "running"),
    ("node", "skipped", "running"),
    ("node", "cancelled", "failed"),
    ("artifact", "superseded", "approved"),
    ("artifact", "approved", "rejected"),
    ("artifact", "proposed", "draft"),
    ("artifact", "rejected", "proposed"),
]


@pytest.mark.parametrize(("machine", "current", "target"), _ILLEGAL_TRANSITIONS)
def test_illegal_transition_raises_with_code_and_details(machine: str, current: str, target: str) -> None:
    assert can_transition(machine, current, target) is False

    with pytest.raises(IllegalStateTransition) as excinfo:
        ensure_transition(machine, current, target)

    error = excinfo.value
    assert error.code == "ILLEGAL_STATE_TRANSITION"
    assert error.status_code == 409
    assert error.details == {"machine": machine, "current": current, "target": target}
    assert error.machine == machine
    assert error.current == current
    assert error.target == target
    assert current in error.message and target in error.message
    assert isinstance(error, APIError)


@pytest.mark.parametrize("machine", sorted(_MACHINE_STATUSES))
def test_reapplying_the_same_status_is_allowed(machine: str) -> None:
    for status in _MACHINE_STATUSES[machine]:
        assert can_transition(machine, status, status) is True
        ensure_transition(machine, status, status)  # idempotent replay must not raise


def test_reapplying_an_unknown_status_is_rejected() -> None:
    assert can_transition("run", "bogus", "bogus") is False
    with pytest.raises(IllegalStateTransition):
        ensure_transition("run", "bogus", "bogus")


@pytest.mark.parametrize("status", sorted(TERMINAL_RUN_STATUSES))
def test_terminal_run_statuses_have_no_outgoing_transitions(status: str) -> None:
    assert allowed_targets("run", status) == frozenset()
    for target in RUN_STATUSES:
        if target == status:
            continue
        with pytest.raises(IllegalStateTransition) as excinfo:
            ensure_transition("run", status, target)
        assert excinfo.value.details == {"machine": "run", "current": status, "target": target}


@pytest.mark.parametrize("status", RUN_STATUSES)
def test_run_status_classification(status: str) -> None:
    assert is_terminal_run_status(status) is (status in TERMINAL_RUN_STATUSES)
    assert is_active_run_status(status) is (status in ACTIVE_RUN_STATUSES)
    # Terminal and active statuses are mutually exclusive partitions of RUN_STATUSES.
    assert not (is_terminal_run_status(status) and is_active_run_status(status))
    assert is_terminal_run_status(status) or is_active_run_status(status)


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_terminal_run_status_membership(status: str) -> None:
    assert is_terminal_run_status(status) is True
    assert is_active_run_status(status) is False


@pytest.mark.parametrize("status", ["queued", "running", "waiting_approval"])
def test_active_run_status_membership(status: str) -> None:
    assert is_active_run_status(status) is True
    assert is_terminal_run_status(status) is False


def test_unknown_run_status_is_neither_active_nor_terminal() -> None:
    assert is_terminal_run_status("archived") is False
    assert is_active_run_status("archived") is False
    assert TERMINAL_RUN_STATUSES | ACTIVE_RUN_STATUSES == set(RUN_STATUSES)


@pytest.mark.parametrize("machine", sorted(_MACHINE_TABLES))
def test_allowed_targets_returns_frozensets(machine: str) -> None:
    declared = set(_MACHINE_STATUSES[machine])
    for status in _MACHINE_STATUSES[machine]:
        targets = allowed_targets(machine, status)
        assert isinstance(targets, frozenset)
        assert targets <= declared
    unknown = allowed_targets(machine, "does-not-exist")
    assert isinstance(unknown, frozenset)
    assert unknown == frozenset()


def test_transitions_for_unknown_machine_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown state machine"):
        transitions_for("timeline")


# ---------------------------------------------------------------------------
# 2. Workflow DAG
# ---------------------------------------------------------------------------
def _replace_nodes(definition: Any, replacements: dict[str, NodeSpec]) -> Any:
    nodes = tuple(replacements.get(spec.key, spec) for spec in definition.nodes)
    return dataclasses.replace(definition, nodes=nodes)


def test_chapter_generation_workflow_validates_with_unique_node_keys() -> None:
    workflow = chapter_generation_workflow()
    workflow.validate()  # must not raise
    keys = workflow.node_keys()
    assert len(set(keys)) == len(keys)
    assert len(workflow.nodes) == len(keys)
    assert "director" in keys


def test_topological_order_places_every_dependency_before_its_dependent() -> None:
    workflow = chapter_generation_workflow()
    order = [spec.key for spec in workflow.topological_order()]

    assert sorted(order) == sorted(workflow.node_keys())
    position = {key: index for index, key in enumerate(order)}
    for spec in workflow.nodes:
        for dependency in spec.depends_on:
            assert position[dependency] < position[spec.key], f"{dependency} must precede {spec.key}"


def test_topological_order_is_stable_across_constructions() -> None:
    first = [spec.key for spec in chapter_generation_workflow().topological_order()]
    second = [spec.key for spec in chapter_generation_workflow().topological_order()]
    assert first == second


def test_content_hash_is_stable_and_parameter_sensitive() -> None:
    baseline = chapter_generation_workflow(max_revision_iterations=3)
    same = chapter_generation_workflow(max_revision_iterations=3)
    changed = chapter_generation_workflow(max_revision_iterations=4)

    assert baseline.content_hash() == same.content_hash()
    assert len(baseline.content_hash()) == 64
    assert baseline.content_hash() != changed.content_hash()
    # The parameter is embedded in the gate node config, not merely in the key.
    assert baseline.node("quality_gate").config["max_revision_iterations"] == 3
    assert changed.node("quality_gate").config["max_revision_iterations"] == 4


def test_to_dag_json_round_trips_the_node_list() -> None:
    workflow = chapter_generation_workflow()
    dag = workflow.to_dag_json()

    assert dag["workflow_key"] == "chapter_generation"
    assert dag["schema_version"] == "1.0"
    assert dag["entry_node"] == "director"
    assert dag["nodes"] == [spec.as_dict() for spec in workflow.nodes]

    rebuilt = [
        NodeSpec(
            **{**raw, "depends_on": tuple(raw["depends_on"]), "produces": tuple(raw["produces"])}
        )
        for raw in dag["nodes"]
    ]
    assert rebuilt == list(workflow.nodes)
    # A DAG dump survives a JSON round trip unchanged.
    assert json.loads(json.dumps(dag)) == dag


def test_next_node_after_follows_the_writer_diamond() -> None:
    workflow = chapter_generation_workflow()
    completed = {"director", "retrieve_context", "plot_architect", "idea", "character", "scene_planner"}

    completed.add("writer")
    after_writer = workflow.next_node_after("writer", completed)
    assert after_writer is not None and after_writer.key == "continuity"

    completed.add("continuity")
    after_continuity = workflow.next_node_after("continuity", completed)
    assert after_continuity is not None and after_continuity.key == "critic"

    completed.add("critic")
    after_critic = workflow.next_node_after("critic", completed)
    assert after_critic is not None and after_critic.key == "quality_gate"


def test_next_node_after_never_selects_branch_only_nodes() -> None:
    workflow = chapter_generation_workflow()
    # Branch-only nodes are reached exclusively through an explicit gate or
    # approval decision: revision (gate says "revise") and the two mutually
    # exclusive ends of the approval branch.
    branch_only = {spec.key for spec in workflow.nodes if spec.branch_only}
    assert branch_only == {"revision", "canon_manager", "keep_draft"}
    ends_workflow = {spec.key for spec in workflow.nodes if spec.ends_workflow}
    assert ends_workflow == {"canon_manager", "keep_draft"}

    # quality_gate is satisfied by continuity + critic; the next node must be
    # style_editor even though `revision` also declares quality_gate as a dependency.
    satisfied = {
        "director",
        "retrieve_context",
        "plot_architect",
        "idea",
        "character",
        "scene_planner",
        "writer",
        "continuity",
        "critic",
        "quality_gate",
    }
    nxt = workflow.next_node_after("quality_gate", satisfied)
    assert nxt is not None and nxt.key == "style_editor"

    # Greedy walk of the whole DAG skips branch-only nodes entirely.
    completed: set[str] = set()
    visited: list[str] = ["director"]
    current = "director"
    while True:
        completed.add(current)
        following = workflow.next_node_after(current, completed)
        if following is None:
            break
        assert following.key not in branch_only
        visited.append(following.key)
        current = following.key
        assert len(visited) <= len(workflow.nodes), "next_node_after looped"

    assert set(visited) == set(workflow.node_keys()) - branch_only
    assert "canon_extractor" in visited
    assert "canon_manager" not in visited


def test_unknown_node_raises_workflow_node_not_found() -> None:
    workflow = chapter_generation_workflow()
    with pytest.raises(APIError) as excinfo:
        workflow.node("nope")

    assert excinfo.value.code == "WORKFLOW_NODE_NOT_FOUND"
    assert excinfo.value.status_code == 404
    assert "nope" in excinfo.value.message


def test_validate_rejects_unknown_dependency_built_with_replace() -> None:
    workflow = chapter_generation_workflow()
    broken_node = dataclasses.replace(workflow.node("idea"), depends_on=("ghost_node",))
    assert broken_node.key == "idea"
    broken = _replace_nodes(workflow, {"idea": broken_node})

    with pytest.raises(APIError) as excinfo:
        broken.validate()

    assert excinfo.value.code == "WORKFLOW_DEFINITION_INVALID"
    assert excinfo.value.status_code == 500
    assert "ghost_node" in excinfo.value.message


def test_validate_rejects_dependency_cycle_built_with_replace() -> None:
    workflow = chapter_generation_workflow()
    broken = _replace_nodes(
        workflow,
        {
            "idea": dataclasses.replace(workflow.node("idea"), depends_on=("character",)),
            "character": dataclasses.replace(workflow.node("character"), depends_on=("idea",)),
        },
    )

    with pytest.raises(APIError) as excinfo:
        broken.validate()

    assert excinfo.value.code == "WORKFLOW_DEFINITION_INVALID"
    assert excinfo.value.status_code == 500
    assert "cycle" in excinfo.value.message


# ---------------------------------------------------------------------------
# 3. Quality gate
# ---------------------------------------------------------------------------
def test_quality_gate_defaults_match_default_quality_gate() -> None:
    gate = QualityGate()

    assert gate.minimum == DEFAULT_QUALITY_GATE["minimum"]
    assert gate.hard_fail == tuple(DEFAULT_QUALITY_GATE["hard_fail"])
    assert gate.max_revision_iterations == DEFAULT_QUALITY_GATE["max_revision_iterations"] == 3
    # Defaults are copied per instance; a customised gate cannot poison the module constant.
    gate.minimum["novelty"] = 0.01
    assert DEFAULT_QUALITY_GATE["minimum"]["novelty"] == 0.65
    assert QualityGate().minimum["novelty"] == 0.65
    assert QualityGate().minimum is not QualityGate().minimum


def test_quality_gate_from_preset_reads_minimum_and_iterations() -> None:
    gate = QualityGate.from_preset(
        {
            "quality_gate": {
                "minimum": {"novelty": 0.9, "pacing": 0.8},
                "max_revision_iterations": 5,
            }
        }
    )

    assert gate.max_revision_iterations == 5
    assert gate.minimum["novelty"] == 0.9
    assert gate.minimum["pacing"] == 0.8
    # Unspecified thresholds keep their defaults.
    assert gate.minimum["continuity"] == DEFAULT_QUALITY_GATE["minimum"]["continuity"]
    assert gate.hard_fail == tuple(DEFAULT_QUALITY_GATE["hard_fail"])


def test_quality_gate_from_preset_reads_revision_max_iterations() -> None:
    gate = QualityGate.from_preset({"quality_gate": {"revision": {"max_iterations": 7}}})
    assert gate.max_revision_iterations == 7
    assert gate.minimum == DEFAULT_QUALITY_GATE["minimum"]


def test_quality_gate_from_preset_prefers_revision_max_iterations() -> None:
    gate = QualityGate.from_preset(
        {"quality_gate": {"max_revision_iterations": 2, "revision": {"max_iterations": 9}}}
    )
    assert gate.max_revision_iterations == 9


@pytest.mark.parametrize(
    "preset_content",
    [
        None,
        {},
        {"quality_gate": None},
        {"quality_gate": {}},
        {"quality_gate": {"minimum": "not-a-mapping", "max_revision_iterations": "5"}},
        {"quality_gate": {"minimum": ["novelty"], "revision": "nope"}},
        {"quality_gate": {"max_revision_iterations": 2.5, "revision": {"max_iterations": None}}},
        {"quality_gate": {"hard_fail": []}},
        {"quality_gate": {"hard_fail": "required_fact_missing"}},
        {"other_section": {"minimum": {"novelty": 0.1}}},
    ],
)
def test_quality_gate_from_preset_ignores_malformed_values(preset_content: dict[str, Any] | None) -> None:
    gate = QualityGate.from_preset(preset_content)

    assert gate.minimum == DEFAULT_QUALITY_GATE["minimum"]
    assert gate.hard_fail == tuple(DEFAULT_QUALITY_GATE["hard_fail"])
    assert gate.max_revision_iterations == DEFAULT_QUALITY_GATE["max_revision_iterations"]


def test_quality_gate_from_preset_does_not_ignore_non_numeric_minimum_values() -> None:
    # Only a non-mapping `minimum` is ignored; a mapping with an unparseable
    # value is coerced with float() and therefore raises.
    with pytest.raises(ValueError, match="could not convert string to float"):
        QualityGate.from_preset({"quality_gate": {"minimum": {"novelty": "high"}}})


def test_quality_gate_from_preset_accepts_custom_hard_fail_list() -> None:
    gate = QualityGate.from_preset({"quality_gate": {"hard_fail": ["custom_failure", 7]}})
    assert gate.hard_fail == ("custom_failure", "7")


def test_evaluate_passes_when_all_thresholds_are_met() -> None:
    gate = QualityGate()
    result = gate.evaluate(
        continuity={"score": 0.99, "hard_failures": []},
        critic={
            "scores": {
                "continuity": 0.99,
                "character_consistency": 0.9,
                "novelty": 0.7,
                "pacing": 0.65,
                "prose": 0.75,
            }
        },
    )

    assert result["passed"] is True
    assert result["reasons"] == []
    assert result["hard_failures"] == []
    assert result["unknown_hard_failures"] == []
    assert result["minimum"] == dict(gate.minimum)
    assert result["scores"]["pacing"] == 0.65
    assert result["scores"]["prose"] == 0.75


def test_evaluate_fails_below_minimum_and_names_the_metric() -> None:
    result = QualityGate().evaluate(
        continuity={"score": 0.99, "hard_failures": []},
        critic={"scores": {"continuity": 0.99, "character_consistency": 0.9, "novelty": 0.9, "pacing": 0.4}},
    )

    assert result["passed"] is False
    below = [reason for reason in result["reasons"] if reason["type"] == "below_minimum"]
    assert below == [{"type": "below_minimum", "metric": "pacing", "value": 0.4, "minimum": 0.65}]
    assert result["unknown_hard_failures"] == []


def test_evaluate_uses_continuity_score_when_critic_omits_it() -> None:
    result = QualityGate().evaluate(
        continuity={"score": 0.5},
        critic={"scores": {"novelty": 0.9, "pacing": 0.9, "character_consistency": 0.9}},
    )

    assert result["scores"]["continuity"] == 0.5
    assert result["passed"] is False
    metrics = {reason["metric"] for reason in result["reasons"] if reason["type"] == "below_minimum"}
    assert metrics == {"continuity"}


def test_evaluate_fails_on_known_hard_failures() -> None:
    result = QualityGate().evaluate(
        continuity={"score": 0.99, "hard_failures": ["required_fact_missing", "forbidden_event_present"]},
        critic={"scores": {"continuity": 0.99, "character_consistency": 0.9, "novelty": 0.9, "pacing": 0.9}},
    )

    assert result["passed"] is False
    assert result["hard_failures"] == ["required_fact_missing", "forbidden_event_present"]
    assert result["unknown_hard_failures"] == []
    assert {"type": "hard_fail", "metric": "required_fact_missing"} in result["reasons"]
    assert all(reason["type"] == "hard_fail" for reason in result["reasons"])


def test_evaluate_reports_unknown_hard_failures() -> None:
    result = QualityGate().evaluate(
        continuity={"score": 0.99, "hard_failures": ["style_editor_fact_change", "totally_new_failure"]},
        critic={"scores": {"continuity": 0.99, "character_consistency": 0.9, "novelty": 0.9, "pacing": 0.9}},
    )

    assert result["passed"] is False
    assert result["unknown_hard_failures"] == ["totally_new_failure"]
    assert result["hard_failures"] == ["style_editor_fact_change", "totally_new_failure"]


def test_evaluate_tolerates_metrics_missing_from_both_reports() -> None:
    empty = QualityGate().evaluate(continuity={}, critic={})
    assert empty["passed"] is True
    assert empty["scores"] == {}
    assert empty["reasons"] == []

    non_numeric = QualityGate().evaluate(
        continuity={"score": "high"},
        critic={"scores": {"pacing": None, "novelty": "excellent", "continuity": 0.99}},
    )
    assert non_numeric["scores"] == {"continuity": 0.99}
    assert non_numeric["passed"] is True


def test_evaluate_respects_a_customised_gate() -> None:
    gate = QualityGate(minimum={"novelty": 0.99}, hard_fail=(), max_revision_iterations=1)
    result = gate.evaluate(
        continuity={"score": 0.1, "hard_failures": ["forbidden_event_present"]},
        critic={"scores": {"novelty": 0.9}},
    )

    assert result["passed"] is False
    # "continuity" is no longer a minimum, so the only below_minimum reason is novelty.
    below = [reason for reason in result["reasons"] if reason["type"] == "below_minimum"]
    assert below == [{"type": "below_minimum", "metric": "novelty", "value": 0.9, "minimum": 0.99}]
    # A hard_fail tuple that no longer lists the reported failure only changes the
    # classification (unknown), not the fact that the gate fails.
    assert result["unknown_hard_failures"] == ["forbidden_event_present"]
    assert {"type": "hard_fail", "metric": "forbidden_event_present"} in result["reasons"]


# ---------------------------------------------------------------------------
# 4. Context builder
# ---------------------------------------------------------------------------
_PROJECT_FILES: dict[str, str] = {
    "canon/world.md": "The archive has no window. The ledger is chained to the desk.",
    "plot/rolling_plan.yaml": "chapter: 1\ngoal: open the archive\n",
    "characters/alice.yaml": "name: alice\nknows: [K19]\n",
    "chapters/0001/summary.md": "Alice enters the archive and finds fresh scratches.",
}

_EXPECTED_DEFAULT_ORDER = [
    "canon/world.md",
    "chapters/0001/summary.md",
    "characters/alice.yaml",
    "plot/rolling_plan.yaml",
]


def _write_project(root: Path) -> Path:
    for relative, text in _PROJECT_FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_context_builder_orders_deterministically_with_source_ref_tie_break(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    first = ContextBuilder(root).collect()
    second = ContextBuilder(root).collect()

    refs = [item.source_ref for item in first]
    assert refs == _EXPECTED_DEFAULT_ORDER
    assert refs == sorted(refs)  # all scores tie at 0.0 -> source_ref ascending
    assert [item.source_ref for item in second] == refs
    assert [item.score for item in first] == [0.0] * len(refs)
    assert all(item.reason == "project_default" for item in first)
    assert first[0].metadata == {"path": "canon/world.md"}
    assert first[0].kind == "canon"
    assert {item.kind for item in first} == {"canon", "chapter", "character", "plot"}


def test_context_builder_assigns_contiguous_one_based_ranks(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    items = ContextBuilder(root).collect()

    assert len(items) == len(_PROJECT_FILES)
    assert [item.rank for item in items] == list(range(1, len(items) + 1))


def test_context_builder_respects_top_k(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    items = ContextBuilder(root, top_k=2).collect()

    assert [item.source_ref for item in items] == _EXPECTED_DEFAULT_ORDER[:2]
    assert [item.rank for item in items] == [1, 2]


def test_context_builder_respects_the_token_budget(tmp_path: Path) -> None:
    for index in range(4):
        path = tmp_path / "canon" / f"doc{index}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a" * 400, encoding="utf-8")  # 400 chars -> 100 estimated tokens

    unbudgeted = ContextBuilder(tmp_path).collect()
    assert len(unbudgeted) == 4

    budgeted = ContextBuilder(tmp_path, token_budget=250).collect()
    assert [item.source_ref for item in budgeted] == [
        "canon/doc0.md",
        "canon/doc1.md",
    ]
    assert sum(estimate_tokens(item.text) for item in budgeted) <= 250


def test_context_builder_always_keeps_at_least_one_item(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    items = ContextBuilder(root, token_budget=1).collect()

    assert len(items) == 1
    assert items[0].source_ref == "canon/world.md"
    assert items[0].rank == 1
    assert estimate_tokens(items[0].text) > 1


def test_context_builder_query_terms_raise_a_matching_score(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    plain = {item.source_ref: item for item in ContextBuilder(root).collect()}
    matched = ContextBuilder(root).collect(query="archive ledger")
    scored = {item.source_ref: item for item in matched}

    assert plain["canon/world.md"].score == 0.0
    assert scored["canon/world.md"].score > plain["canon/world.md"].score
    assert scored["canon/world.md"].score > scored["plot/rolling_plan.yaml"].score
    assert matched[0].source_ref == "canon/world.md"
    assert matched[0].rank == 1
    assert matched[0].reason == "keyword_overlap"
    assert scored["characters/alice.yaml"].score == 0.0
    assert scored["characters/alice.yaml"].reason == "project_default"
    # Equal scores fall back to source_ref ordering: chapters/... before plot/...
    assert [item.source_ref for item in matched] == [
        "canon/world.md",
        "chapters/0001/summary.md",
        "plot/rolling_plan.yaml",
        "characters/alice.yaml",
    ]


def test_context_builder_ignores_empty_files(tmp_path: Path) -> None:
    _write_project(tmp_path)
    (tmp_path / "canon" / "empty.md").write_text("   \n\n", encoding="utf-8")

    refs = [item.source_ref for item in ContextBuilder(tmp_path).collect()]
    assert refs == _EXPECTED_DEFAULT_ORDER


def test_estimate_tokens_is_monotonic_in_text_length() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("x") == 1

    lengths = [0, 1, 3, 4, 7, 8, 40, 400]
    estimates = [estimate_tokens("x" * length) for length in lengths]
    assert estimates == sorted(estimates)
    assert estimates[-1] > estimates[0]

    values = [estimate_tokens("x" * length) for length in range(0, 200)]
    assert all(earlier <= later for earlier, later in zip(values, values[1:]))


# ---------------------------------------------------------------------------
# 5. Fake provider
# ---------------------------------------------------------------------------
_AGENT_ARTIFACT_PAIRS: list[tuple[str, str]] = [
    ("director", "director_decision"),
    ("plot_architect", "plot_plan"),
    ("idea", "idea_candidates"),
    ("character", "character_intent"),
    ("scene_planner", "scene_brief"),
    ("writer", "chapter_draft"),
    ("revision", "chapter_draft"),
    ("continuity", "continuity_report"),
    ("critic", "critic_report"),
    ("style_editor", "style_edit_result"),
    ("canon_extractor", "canon_patch"),
    ("summarizer", "chapter_summary"),
]


@pytest.fixture(scope="module")
def schema_registry() -> ArtifactSchemaRegistry:
    return ArtifactSchemaRegistry(ARTIFACT_SCHEMAS_ROOT)


@pytest.mark.parametrize(("agent_key", "artifact_type"), _AGENT_ARTIFACT_PAIRS, ids=lambda value: value)
async def test_fake_generated_content_validates_against_its_schema(
    agent_key: str, artifact_type: str, schema_registry: ArtifactSchemaRegistry
) -> None:
    response = await FakeProvider().complete(_request(agent_key))

    assert schema_registry.supports(artifact_type)
    schema_registry.validate(artifact_type, response.content)  # must not raise
    assert response.provider == "fake"


@pytest.mark.parametrize(("agent_key", "artifact_type"), _AGENT_ARTIFACT_PAIRS, ids=lambda value: value)
async def test_fake_provider_output_is_deterministic(agent_key: str, artifact_type: str) -> None:
    first = await FakeProvider().complete(_request(agent_key))
    second = await FakeProvider().complete(_request(agent_key))

    assert first.content == second.content
    assert first.usage == second.usage
    assert first.content == FakeProvider().generate(artifact_type, attempt=1, request=_request(agent_key))


async def test_fake_idea_candidates_has_at_least_ten_unique_candidates(schema_registry: ArtifactSchemaRegistry) -> None:
    response = await FakeProvider().complete(_request("idea"))

    candidates = response.content["candidates"]
    assert len(candidates) >= 10
    assert len({candidate["candidate_id"] for candidate in candidates}) == len(candidates)
    assert len(candidates) >= _artifact_schema("idea_candidates")["properties"]["candidates"]["minItems"]
    assert {candidate["risk_level"] for candidate in candidates} == {"safe", "moderate", "wild"}
    schema_registry.validate("idea_candidates", response.content)


def _artifact_schema(artifact_type: str) -> dict[str, Any]:
    return json.loads((ARTIFACT_SCHEMAS_ROOT / f"{artifact_type}.json").read_text(encoding="utf-8"))


async def test_fake_scene_brief_has_exactly_the_required_schema_keys() -> None:
    response = await FakeProvider().complete(_request("scene_planner"))
    schema = _artifact_schema("scene_brief")

    assert set(response.content) == set(schema["required"])
    assert schema["additionalProperties"] is False
    assert response.content["target_words"] >= schema["properties"]["target_words"]["minimum"]
    assert isinstance(response.content["required_facts"], list) and response.content["required_facts"]
    assert isinstance(response.content["forbidden_events"], list)


_FAULT_EXPECTATIONS: dict[str, tuple[str, bool]] = {
    "timeout": ("provider_timeout", True),
    "rate_limited": ("provider_rate_limited", True),
    "server_error": ("provider_server_error", True),
    "malformed_json": ("provider_malformed_response", False),
    "stream_interrupted": ("provider_stream_interrupted", True),
    "slow_response": ("provider_slow_response", True),
}


def test_every_declared_fault_type_is_covered_by_expectations() -> None:
    assert set(_FAULT_EXPECTATIONS) == set(FAULT_TYPES)


@pytest.mark.parametrize(("fault", "expected"), sorted(_FAULT_EXPECTATIONS.items()))
async def test_injected_fault_raises_documented_provider_error(fault: str, expected: tuple[str, bool]) -> None:
    code, retryable = expected
    provider = FakeProvider(faults=[fault])

    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_request("writer"))

    error = excinfo.value
    assert error.code == code
    assert error.retryable is retryable
    assert fault in error.message
    assert provider.faults == []  # the scripted fault is consumed


async def test_transient_and_permanent_faults_are_classified() -> None:
    retryable = {fault for fault, (_, can_retry) in _FAULT_EXPECTATIONS.items() if can_retry}
    permanent = set(FAULT_TYPES) - retryable

    assert permanent == {"malformed_json"}
    assert "malformed_json" in permanent
    for fault in sorted(retryable):
        with pytest.raises(ProviderError) as excinfo:
            await FakeProvider(faults=[fault]).complete(_request("critic"))
        assert excinfo.value.retryable is True
    for fault in sorted(permanent):
        with pytest.raises(ProviderError) as excinfo:
            await FakeProvider(faults=[fault]).complete(_request("critic"))
        assert excinfo.value.retryable is False


async def test_faults_by_agent_only_affects_the_targeted_agent() -> None:
    provider = FakeProvider(faults_by_agent={"writer": ["timeout"]})

    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_request("writer"))
    assert excinfo.value.code == "provider_timeout"

    healthy = await provider.complete(_request("critic"))
    assert "scores" in healthy.content

    # The per-agent queue only had one entry: the next writer call succeeds too.
    recovered = await provider.complete(_request("writer"))
    assert "text" in recovered.content
    assert provider.faults == []


async def test_per_agent_fault_queue_takes_priority_over_the_shared_queue() -> None:
    provider = FakeProvider(faults=["server_error"], faults_by_agent={"writer": ["timeout"]})

    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_request("writer"))
    assert excinfo.value.code == "provider_timeout"
    assert provider.faults == ["server_error"]  # the shared queue is untouched

    # The shared queue serves every agent; `critic` is not protected by faults_by_agent.
    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_request("critic"))
    assert excinfo.value.code == "provider_server_error"
    assert provider.faults == []


async def test_unknown_agent_key_raises_provider_schema_error() -> None:
    provider = FakeProvider()

    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_request("not_an_agent"))

    assert excinfo.value.code == "provider_schema_error"
    assert excinfo.value.retryable is False
    assert "not_an_agent" in excinfo.value.message
    assert len(provider.calls) == 1


async def test_unknown_fault_name_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown fake fault"):
        await FakeProvider(faults=["not_a_fault"]).complete(_request("writer"))


# ---------------------------------------------------------------------------
# 6. Recorded provider
# ---------------------------------------------------------------------------
@dataclass
class _FakeLlmCall:
    agent_key: str
    response_json: dict[str, Any] | None
    usage_json: dict[str, Any] | None = None
    model_profile_snapshot: dict[str, Any] | None = None


async def test_recorded_provider_replays_entries_in_order_per_agent() -> None:
    provider = RecordedProvider(
        [
            {"agent_key": "writer", "content": {"text": "first"}},
            {"agent_key": "writer", "content": {"text": "second"}},
            {"agent_key": "critic", "content": {"scores": {"novelty": 0.9}}},
            {"agent_key": "critic", "content": {"scores": {"novelty": 0.5}}},
        ]
    )

    first = await provider.complete(_request("writer"))
    second = await provider.complete(_request("writer"))
    critic_first = await provider.complete(_request("critic"))
    critic_second = await provider.complete(_request("critic"))

    assert first.content == {"text": "first"}
    assert second.content == {"text": "second"}
    assert critic_first.content == {"scores": {"novelty": 0.9}}
    assert critic_second.content == {"scores": {"novelty": 0.5}}
    assert first.provider == "recorded"
    assert critic_second.provider == "recorded"


@pytest.mark.parametrize("agent_key", ["writer", "never_recorded"])
async def test_recorded_provider_raises_when_exhausted(agent_key: str) -> None:
    provider = RecordedProvider([{"agent_key": "writer", "content": {"text": "only"}}])
    if agent_key == "writer":
        await provider.complete(_request("writer"))

    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_request(agent_key))

    assert excinfo.value.code == "provider_replay_exhausted"
    assert excinfo.value.retryable is False
    assert agent_key in excinfo.value.message


async def test_recorded_provider_from_llm_calls_skips_calls_without_stored_response() -> None:
    calls = [
        _FakeLlmCall(
            "writer",
            {"content": {"text": "first"}},
            {"total_tokens": 11},
            {"model_name": "recorded-model-x"},
        ),
        _FakeLlmCall("writer", None),  # failed call: nothing stored
        _FakeLlmCall("writer", {}),  # stored envelope without content
        _FakeLlmCall("writer", {"content": {"text": "second"}}),
    ]
    provider = RecordedProvider.from_llm_calls(calls)

    first = await provider.complete(_request("writer"))
    assert first.content == {"text": "first"}
    assert first.model == "recorded-model-x"
    assert first.usage == {"total_tokens": 11}

    second = await provider.complete(_request("writer"))
    assert second.content == {"text": "second"}
    assert second.model == "recorded-model"
    assert second.usage == {}

    with pytest.raises(ProviderError) as excinfo:
        await provider.complete(_request("writer"))
    assert excinfo.value.code == "provider_replay_exhausted"


async def test_recorded_provider_groups_entries_by_agent_regardless_of_insertion_order() -> None:
    provider = RecordedProvider(
        [
            {"agent_key": "writer", "content": {"text": "w1"}},
            {"agent_key": "critic", "content": {"text": "c1"}},
            {"agent_key": "writer", "content": {"text": "w2"}},
        ]
    )

    assert (await provider.complete(_request("writer"))).content == {"text": "w1"}
    assert (await provider.complete(_request("critic"))).content == {"text": "c1"}
    assert (await provider.complete(_request("writer"))).content == {"text": "w2"}


# ---------------------------------------------------------------------------
# 7. Redaction
# ---------------------------------------------------------------------------
_SENSITIVE_KEYS = [
    "authorization",
    "Authorization",
    "AUTHORIZATION",
    "api_key",
    "API_KEY",
    "apikey",
    "x-api-key",
    "X-Api-Key",
    "cookie",
    "Set-Cookie",
    "password",
    "PASSWORD",
    "secret",
    "access_token",
    "refresh_token",
    "session",
]


@pytest.mark.parametrize("key", _SENSITIVE_KEYS)
def test_redact_replaces_sensitive_keys_case_insensitively(key: str) -> None:
    payload = {key: "super-secret-value", "agent_key": "writer"}
    redacted = redact(payload)

    assert redacted[key] == REDACTED
    assert redacted["agent_key"] == "writer"
    assert "super-secret-value" not in json.dumps(redacted)


def test_redact_walks_nested_dicts_and_lists() -> None:
    payload = {
        "request": {
            "messages": [{"role": "system", "content": "hello"}],
            "headers": {"Authorization": "Bearer abc", "X-Request-Id": "req-1"},
            "endpoints": [
                {"name": "primary", "api_key": "k-1"},
                {"name": "fallback", "api_key": "k-2", "nested": {"Password": "p"}},
            ],
        },
        "usage": {"total_tokens": 3},
    }

    redacted = redact(payload)

    assert redacted["request"]["headers"]["Authorization"] == REDACTED
    assert redacted["request"]["headers"]["X-Request-Id"] == "req-1"
    assert [endpoint["api_key"] for endpoint in redacted["request"]["endpoints"]] == [REDACTED, REDACTED]
    assert redacted["request"]["endpoints"][1]["nested"]["Password"] == REDACTED
    assert redacted["request"]["messages"] == [{"role": "system", "content": "hello"}]
    assert redacted["usage"] == {"total_tokens": 3}
    assert isinstance(redacted["request"]["endpoints"], list)


def test_redact_keeps_tuples_as_lists_and_preserves_scalars() -> None:
    redacted = redact({"items": ("plain", {"token": "t", "password": "p"}), "count": 3, "flag": True, "none": None})

    assert redacted["items"] == ["plain", {"token": "t", "password": REDACTED}]
    assert redacted["count"] == 3
    assert redacted["flag"] is True
    assert redacted["none"] is None
    assert redact("plain string") == "plain string"
    assert redact(42) == 42


def test_redact_does_not_mutate_its_input() -> None:
    payload: dict[str, Any] = {
        "authorization": "Bearer abc",
        "nested": {"api_key": "k", "list": [{"password": "p"}, "keep"]},
        "plain": "keep",
    }
    snapshot = json.loads(json.dumps(payload))

    redacted = redact(payload)

    assert payload == snapshot
    assert redacted is not payload
    assert redacted["nested"] is not payload["nested"]
    assert redacted["nested"]["api_key"] == REDACTED
    assert payload["nested"]["api_key"] == "k"
    assert payload["nested"]["list"][0]["password"] == "p"


def test_redact_only_matches_exact_key_names() -> None:
    payload = {"api_key_id": "not-a-credential", "my_password_field": "still-visible", "padding": "visible"}
    redacted = redact(payload)

    assert redacted == payload
    assert REDACTED not in redacted.values()


def test_redact_preserves_non_string_keys() -> None:
    redacted = redact({1: "one", "password": "p"})
    assert redacted[1] == "one"
    assert redacted["password"] == REDACTED


# ---------------------------------------------------------------------------
# 8. Canonical content hash
# ---------------------------------------------------------------------------
_DRAFT_CONTENT: dict[str, Any] = {
    "chapter_number": 1,
    "title": "Chapter 1",
    "text": "地下室里没有窗。",
    "word_count": 9,
    "scene_ids": ["1-1", "1-2"],
}


def test_canonical_hash_is_order_insensitive_for_the_same_logical_content() -> None:
    first = {"outer": {"b": 1, "a": 2}, "items": [{"y": 1, "x": 2}], "title": "t"}
    second = {"title": "t", "items": [{"x": 2, "y": 1}], "outer": {"a": 2, "b": 1}}

    assert canonical_content_hash("chapter_draft", "1.0", first) == canonical_content_hash(
        "chapter_draft", "1.0", second
    )


def test_canonical_hash_is_identical_for_equal_content_copied_around() -> None:
    baseline = canonical_content_hash("chapter_draft", "1.0", _DRAFT_CONTENT)
    copy = json.loads(json.dumps(_DRAFT_CONTENT))

    assert canonical_content_hash("chapter_draft", "1.0", copy) == baseline
    assert len(baseline) == 64
    assert baseline == baseline.lower()
    assert set(baseline) <= set("0123456789abcdef")


def test_canonical_hash_changes_with_content_type_or_schema_version() -> None:
    baseline = canonical_content_hash("chapter_draft", "1.0", _DRAFT_CONTENT)

    different_content = {**_DRAFT_CONTENT, "word_count": 10}
    reordered_list = {**_DRAFT_CONTENT, "scene_ids": ["1-2", "1-1"]}

    assert canonical_content_hash("chapter_draft", "1.0", different_content) != baseline
    assert canonical_content_hash("chapter_draft", "1.0", reordered_list) != baseline
    assert canonical_content_hash("chapter_summary", "1.0", _DRAFT_CONTENT) != baseline
    assert canonical_content_hash("chapter_draft", "1.1", _DRAFT_CONTENT) != baseline


def test_canonical_hash_matches_the_documented_canonical_json() -> None:
    expected = hashlib.sha256(
        json.dumps(
            {"type": "chapter_draft", "schema_version": "1.0", "content": _DRAFT_CONTENT},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert canonical_content_hash("chapter_draft", "1.0", _DRAFT_CONTENT) == expected


def test_canonical_hash_ignores_run_provenance_metadata() -> None:
    # Only the three documented arguments participate, so re-hashing the same
    # logical content after a run replayed it with new provenance/timestamps
    # reproduces an identical digest.
    parameters = list(inspect.signature(canonical_content_hash).parameters)
    assert parameters == ["artifact_type", "schema_version", "content"]
    assert "provenance" not in parameters

    run_one_provenance = {"run_id": "11111111-1111-1111-1111-111111111111", "created_at": "2024-01-01T00:00:00Z"}
    run_two_provenance = {"run_id": "22222222-2222-2222-2222-222222222222", "created_at": "2025-06-30T12:00:00Z"}
    assert run_one_provenance != run_two_provenance

    baseline = canonical_content_hash("chapter_draft", "1.0", _DRAFT_CONTENT)
    replayed = canonical_content_hash("chapter_draft", "1.0", dict(_DRAFT_CONTENT))

    assert replayed == baseline

"""Deterministic fake provider with fault injection (spec §8.1, §16.4).

The fake provider is the M2 acceptance path: a complete chapter workflow must run
without any real LLM, including failure and cancellation branches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from novel_agent.providers.base import LLMRequest, LLMResponse, ProviderError

FAULT_TYPES: tuple[str, ...] = (
    "timeout",
    "rate_limited",
    "server_error",
    "malformed_json",
    "stream_interrupted",
    "slow_response",
)

_FAULT_TO_ERROR = {
    "timeout": "provider_timeout",
    "rate_limited": "provider_rate_limited",
    "server_error": "provider_server_error",
    "malformed_json": "provider_malformed_response",
    "stream_interrupted": "provider_stream_interrupted",
    "slow_response": "provider_slow_response",
}

_AGENT_TO_ARTIFACT = {
    "director": "director_decision",
    "plot_architect": "plot_plan",
    "idea": "idea_candidates",
    "character": "character_intent",
    "scene_planner": "scene_brief",
    "writer": "chapter_draft",
    "revision": "chapter_draft",
    "continuity": "continuity_report",
    "critic": "critic_report",
    "style_editor": "style_edit_result",
    "canon_extractor": "canon_patch",
    "summarizer": "chapter_summary",
}


@dataclass
class FakeScenario:
    """Knobs used by tests to drive the quality gate deterministically."""

    continuity_scores: list[float] = field(default_factory=lambda: [0.99])
    pacing_scores: list[float] = field(default_factory=lambda: [0.9])
    novelty_scores: list[float] = field(default_factory=lambda: [0.9])
    character_consistency_scores: list[float] = field(default_factory=lambda: [0.9])
    hard_failures: list[list[str]] = field(default_factory=lambda: [[]])
    word_count: int = 900
    # Style Editor fact protection (spec §7): any non-empty entry here makes the
    # style pass an illegal fact change.
    style_fact_diff: dict[str, list[str]] = field(
        default_factory=lambda: {"added": [], "removed": [], "changed": []}
    )

    def _pick(self, values: list[Any], attempt: int, default: Any) -> Any:
        if not values:
            return default
        return values[min(max(attempt - 1, 0), len(values) - 1)]

    def continuity_score(self, attempt: int) -> float:
        return float(self._pick(self.continuity_scores, attempt, 0.99))

    def pacing_score(self, attempt: int) -> float:
        return float(self._pick(self.pacing_scores, attempt, 0.9))

    def novelty_score(self, attempt: int) -> float:
        return float(self._pick(self.novelty_scores, attempt, 0.9))

    def character_consistency_score(self, attempt: int) -> float:
        return float(self._pick(self.character_consistency_scores, attempt, 0.9))

    def failures(self, attempt: int) -> list[str]:
        return list(self._pick(self.hard_failures, attempt, []))


class FakeProvider:
    """Deterministic provider keyed by agent, with a scriptable fault queue."""

    name = "fake"

    def __init__(
        self,
        *,
        scenario: FakeScenario | None = None,
        faults: list[str] | None = None,
        faults_by_agent: dict[str, list[str]] | None = None,
        chapter_number: int = 1,
    ) -> None:
        self.scenario = scenario or FakeScenario()
        self.faults = list(faults or [])
        self.faults_by_agent = {key: list(value) for key, value in (faults_by_agent or {}).items()}
        self.chapter_number = chapter_number
        self.calls: list[LLMRequest] = []
        self._attempts: dict[str, int] = {}

    # ------------------------------------------------------------------ faults
    def _next_fault(self, agent_key: str) -> str | None:
        queue = self.faults_by_agent.get(agent_key)
        if queue:
            return queue.pop(0)
        if self.faults:
            return self.faults.pop(0)
        return None

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        self._attempts[request.agent_key] = self._attempts.get(request.agent_key, 0) + 1
        attempt = self._attempts[request.agent_key]

        fault = self._next_fault(request.agent_key)
        if fault is not None:
            if fault not in _FAULT_TO_ERROR:
                raise ValueError(f"Unknown fake fault: {fault}")
            raise ProviderError(_FAULT_TO_ERROR[fault], f"Injected fake provider fault: {fault}")

        artifact_type = _AGENT_TO_ARTIFACT.get(request.agent_key)
        if artifact_type is None:
            raise ProviderError("provider_schema_error", f"No fake content generator for '{request.agent_key}'.")

        content = self.generate(artifact_type, attempt=attempt, request=request)
        return LLMResponse(
            content=content,
            raw={"provider": "fake", "agent_key": request.agent_key, "model": request.model},
            usage={"prompt_tokens": 128, "completion_tokens": 256, "total_tokens": 384},
            latency_ms=5,
            provider="fake",
            model=request.model,
        )

    # --------------------------------------------------------------- content
    def generate(self, artifact_type: str, *, attempt: int, request: LLMRequest) -> dict[str, Any]:
        chapter = self.chapter_number
        if artifact_type == "director_decision":
            return {
                "selected_candidate_id": f"candidate-{chapter}-1",
                "rationale": "Highest plausibility with a contained risk profile.",
                "risk_level": "moderate",
                "retry_requested": False,
            }
        if artifact_type == "plot_plan":
            return {
                "chapter_number": chapter,
                "chapter_goal": f"Chapter {chapter}: the archive is opened.",
                "scenes": [
                    {"scene_id": f"{chapter}-1", "purpose": "Set the压抑 tone and the locked door."},
                    {"scene_id": f"{chapter}-2", "purpose": "Reveal the earlier visitor."},
                ],
                "rolling_plan_notes": "Keep the father's identity unresolved.",
            }
        if artifact_type == "idea_candidates":
            return {
                "candidates": [
                    {
                        "candidate_id": f"candidate-{chapter}-{index}",
                        "summary": f"Candidate {index}: approach the archive from a different angle.",
                        "risk_level": ("safe", "moderate", "wild")[index % 3],
                        "plausibility": round(0.5 + (index % 5) * 0.1, 2),
                        "surprise": round(0.4 + (index % 4) * 0.1, 2),
                        "canon_dependencies": ["archive_room_has_no_window"],
                        "side_effects": [] if index % 2 else ["delays the reveal of the ledger"],
                    }
                    for index in range(1, 11)
                ]
            }
        if artifact_type == "character_intent":
            return {
                "character_id": "alice",
                "knowledge_scope": ["档案编号 K19"],
                "motivation": "Find the archive her father left behind.",
                "reaction": "She catalogues every痕迹 before touching anything.",
                "constraints": ["does not yet know who visited first"],
            }
        if artifact_type == "scene_brief":
            return {
                "scene_id": f"{chapter}-2",
                "pov_character_id": "alice",
                "location_id": "black_tower_basement",
                "objective": "寻找父亲留下的档案",
                "conflict": "发现有人先来过",
                "required_facts": ["房间没有窗", "档案编号 K19"],
                "forbidden_events": ["揭示父亲身份", "出现魔法", "角色死亡"],
                "tone": ["压抑", "安静", "逐渐不安"],
                "target_words": self.scenario.word_count,
            }
        if artifact_type == "chapter_draft":
            revision_note = "" if attempt == 1 else f" (revision {attempt - 1})"
            text = (
                f"第 {chapter} 章{revision_note}\n\n"
                "地下室里没有窗。爱丽丝把手电压低，光柱扫过一排排铁柜，"
                "最后停在编号 K19 的抽屉上。锁扣上有新的划痕——有人比她先到。\n\n"
                "她没有立刻拉开抽屉，而是先数了一遍地面的灰尘脚印。"
            )
            return {
                "chapter_number": chapter,
                "title": f"Chapter {chapter}",
                "text": text,
                "word_count": len(text),
                "scene_ids": [f"{chapter}-1", f"{chapter}-2"],
            }
        if artifact_type == "continuity_report":
            failures = self.scenario.failures(attempt)
            score = self.scenario.continuity_score(attempt)
            return {
                "score": score,
                "issues": [
                    {
                        "severity": "medium",
                        "type": "timeline",
                        "description": "The earlier visitor is not placed on the timeline.",
                        "location": "scene_2",
                        "evidence": "锁扣上有新的划痕",
                    }
                ]
                if failures
                else [],
                "facts_checked": ["房间没有窗", "档案编号 K19"],
                "hard_failures": failures,
            }
        if artifact_type == "critic_report":
            return {
                "scores": {
                    "tension": 0.78,
                    "pacing": self.scenario.pacing_score(attempt),
                    "characterization": 0.84,
                    "prose": 0.75,
                    "novelty": self.scenario.novelty_score(attempt),
                    "emotional_impact": 0.71,
                    "continuity": self.scenario.continuity_score(attempt),
                },
                "problems": [
                    {
                        "severity": "medium",
                        "location": "scene_2",
                        "type": "pacing",
                        "description": "解释性对白过长",
                        "evidence": "她数了一遍地面的灰尘脚印",
                        "suggested_action": "压缩对白并外化冲突",
                    }
                ],
            }
        if artifact_type == "style_edit_result":
            return {
                "text": "地下室里没有窗。爱丽丝把手电压低，光柱扫过铁柜，停在编号 K19 的抽屉上。锁扣留着新划痕——有人先她一步。",
                "word_count": self.scenario.word_count,
                "fact_diff": {
                    "added": list(self.scenario.style_fact_diff.get("added", [])),
                    "removed": list(self.scenario.style_fact_diff.get("removed", [])),
                    "changed": list(self.scenario.style_fact_diff.get("changed", [])),
                },
                "style_notes": ["tightened rhythm"],
            }
        if artifact_type == "canon_patch":
            return {
                "operations": [
                    {
                        "op": "add",
                        "entity_type": "fact",
                        "canonical_name": "archive_room_has_no_window",
                        "data": {"description": "档案室没有窗", "confidence": 0.9},
                    }
                ],
                "rationale": "Established by the approved draft.",
            }
        if artifact_type == "chapter_summary":
            return {
                "chapter_number": chapter,
                "summary": "爱丽丝进入档案室，发现有人先到过。",
                "key_events": ["archive room entered", "signs of an earlier visitor"],
                "character_states": [{"character_id": "alice", "state": "alert"}],
                "open_threads": ["who visited first"],
            }
        raise ProviderError("provider_schema_error", f"Unsupported artifact type '{artifact_type}'.")


class RecordingProvider:
    """Wraps a provider and records responses as replayable entries."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.recorded: list[dict[str, Any]] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await self.inner.complete(request)
        self.recorded.append(
            {
                "agent_key": request.agent_key,
                "node_key": request.node_key,
                "content": response.content,
                "usage": response.usage,
                "model": response.model,
            }
        )
        return response

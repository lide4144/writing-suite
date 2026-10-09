"""Provider selection per run mode (spec §11.1, §16.4)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from novel_agent.core.config import Settings
from novel_agent.core.errors import APIError
from novel_agent.db.models import LlmCall, Run
from novel_agent.providers.base import LLMProvider
from novel_agent.providers.fake import FakeProvider, FakeScenario
from novel_agent.providers.recorded import RecordedProvider

MODE_NORMAL = "normal"
MODE_REPLAY_RECORDED = "replay_recorded"
MODE_REPLAY_LIVE = "replay_live"
RUN_MODES: tuple[str, ...] = (MODE_NORMAL, MODE_REPLAY_RECORDED, MODE_REPLAY_LIVE)


def scenario_from_input(input_json: dict[str, Any]) -> FakeScenario:
    """Build a deterministic fake scenario from run input.

    `fake_scenario` and `fake_faults` are automation knobs: they let tests and
    the automation API drive quality-gate and provider-failure branches without a
    real model (spec §16.4). They are ignored outside development/sandbox runs.
    """

    raw = input_json.get("fake_scenario") or {}
    scenario = FakeScenario()
    if isinstance(raw, dict):
        for field in (
            "continuity_scores",
            "pacing_scores",
            "novelty_scores",
            "character_consistency_scores",
            "hard_failures",
        ):
            value = raw.get(field)
            if isinstance(value, list) and value:
                setattr(scenario, field, value)
        if isinstance(raw.get("word_count"), int):
            scenario.word_count = int(raw["word_count"])
        style_diff = raw.get("style_fact_diff")
        if isinstance(style_diff, dict):
            scenario.style_fact_diff = {
                key: [str(item) for item in style_diff.get(key) or []]
                for key in ("added", "removed", "changed")
            }
    return scenario


async def build_provider(session: AsyncSession, settings: Settings, run: Run) -> LLMProvider:
    input_json = run.input_json or {}
    chapter_number = int(input_json.get("chapter_number") or 1)

    if run.mode == MODE_REPLAY_RECORDED:
        source_run_id = input_json.get("replay_of") or input_json.get("source_run_id")
        if not source_run_id:
            raise APIError(
                "RUN_REPLAY_SOURCE_MISSING",
                "Recorded replay requires input.replay_of pointing at the original run.",
                status_code=422,
            )
        calls = (
            await session.execute(
                select(LlmCall).where(LlmCall.run_id == source_run_id).order_by(LlmCall.created_at.asc())
            )
        ).scalars().all()
        if not calls:
            raise APIError(
                "RUN_REPLAY_SOURCE_EMPTY",
                "The original run has no recorded LLM calls to replay.",
                status_code=422,
            )
        return RecordedProvider.from_llm_calls(calls)

    scenario = scenario_from_input(input_json)
    faults = input_json.get("fake_faults") or []
    faults_by_agent = input_json.get("fake_faults_by_agent") or {}
    if settings.app_env == "production" and (faults or faults_by_agent or input_json.get("fake_scenario")):
        raise APIError(
            "RUN_FAULT_INJECTION_FORBIDDEN",
            "Fault injection is not available when APP_ENV=production.",
            status_code=403,
        )
    return FakeProvider(
        scenario=scenario,
        faults=[str(item) for item in faults],
        faults_by_agent={str(key): [str(item) for item in value] for key, value in faults_by_agent.items()},
        chapter_number=chapter_number,
    )

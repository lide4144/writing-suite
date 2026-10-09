"""Recorded provider: offline replay of previously saved LLM responses (spec §11.1)."""

from __future__ import annotations

from typing import Any, Iterable

from novel_agent.providers.base import LLMRequest, LLMResponse, ProviderError


class RecordedProvider:
    """Replays recorded responses in order, per agent.

    Used for `recorded` replay: orchestration, parsing, storage and UI are
    exercised without calling a real model.
    """

    name = "recorded"

    def __init__(self, entries: Iterable[dict[str, Any]]) -> None:
        self._entries: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            self._entries.setdefault(str(entry["agent_key"]), []).append(entry)
        self._cursor: dict[str, int] = {}

    @classmethod
    def from_llm_calls(cls, calls: Iterable[Any]) -> "RecordedProvider":
        entries: list[dict[str, Any]] = []
        for call in calls:
            response = call.response_json or {}
            content = response.get("content") if isinstance(response, dict) else None
            if content is None:
                continue
            entries.append(
                {
                    "agent_key": call.agent_key,
                    "node_key": None,
                    "content": content,
                    "usage": call.usage_json or {},
                    "model": (call.model_profile_snapshot or {}).get("model_name", "recorded-model"),
                }
            )
        return cls(entries)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        queue = self._entries.get(request.agent_key)
        if not queue:
            raise ProviderError(
                "provider_replay_exhausted",
                f"No recorded response for agent '{request.agent_key}'.",
                retryable=False,
            )
        index = self._cursor.get(request.agent_key, 0)
        if index >= len(queue):
            raise ProviderError(
                "provider_replay_exhausted",
                f"Recorded responses for agent '{request.agent_key}' are exhausted.",
                retryable=False,
            )
        self._cursor[request.agent_key] = index + 1
        entry = queue[index]
        return LLMResponse(
            content=entry["content"],
            raw={"provider": "recorded", "agent_key": request.agent_key},
            usage=entry.get("usage") or {},
            latency_ms=0,
            provider="recorded",
            model=entry.get("model") or request.model,
        )

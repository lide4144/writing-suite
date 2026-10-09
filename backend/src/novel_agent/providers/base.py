"""Provider abstraction for OpenAI-compatible and test providers (spec §9, §16.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LLMMessage:
    role: str
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMRequest:
    agent_key: str
    node_key: str
    messages: list[LLMMessage]
    model: str = "fake-model"
    params: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] | None = None
    template_version: str = "1.0"
    context_item_ids: list[str] = field(default_factory=list)

    def as_trace_payload(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "node_key": self.node_key,
            "model": self.model,
            "params": self.params,
            "template_version": self.template_version,
            "messages": [message.as_dict() for message in self.messages],
            "response_schema_id": (self.response_schema or {}).get("$id"),
        }


@dataclass
class LLMResponse:
    content: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    provider: str = "fake"
    model: str = "fake-model"


class ProviderError(Exception):
    """Provider failure with an explicit retry classification (spec §16.4)."""

    def __init__(self, code: str, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = TRANSIENT_PROVIDER_ERRORS.get(code, False) if retryable is None else retryable


# Transient failures may be retried; schema/permission failures must not be.
TRANSIENT_PROVIDER_ERRORS: dict[str, bool] = {
    "provider_timeout": True,
    "provider_rate_limited": True,
    "provider_server_error": True,
    "provider_stream_interrupted": True,
    "provider_slow_response": True,
    "provider_malformed_response": False,
    "provider_schema_error": False,
    "provider_permission_denied": False,
}


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse:  # pragma: no cover - protocol
        ...

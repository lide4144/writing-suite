"""Provider adapters (spec §9): OpenAI-compatible today, fake/recorded for tests."""

from novel_agent.providers.base import (
    LLMMessage,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    TRANSIENT_PROVIDER_ERRORS,
)
from novel_agent.providers.fake import FAULT_TYPES, FakeProvider, FakeScenario, RecordingProvider
from novel_agent.providers.recorded import RecordedProvider

__all__ = [
    "FAULT_TYPES",
    "FakeProvider",
    "FakeScenario",
    "LLMMessage",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "ProviderError",
    "RecordingProvider",
    "RecordedProvider",
    "TRANSIENT_PROVIDER_ERRORS",
]

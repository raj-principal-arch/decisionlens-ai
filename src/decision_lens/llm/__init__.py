"""Model providers.

A vendor-neutral boundary between DecisionLens and whatever answers its calls.
Skills depend on `ModelProvider`, never on a vendor SDK, so the workflow can be
evaluated against a live model or replayed offline without changing a line of
analysis code.

Implemented at Phase 5:

    base.py            the contract, typed errors, structured-output parsing
    cached_provider.py deterministic offline replay, no API key required

Live adapters (Anthropic, OpenAI) arrive in Phase 6 and only with explicit
approval. Nothing here reaches the network.
"""

from decision_lens.llm.base import (
    DEFAULT_TIMEOUT_SECONDS,
    BaseModelProvider,
    ModelError,
    ModelOutputError,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelTimeout,
    ModelUnavailable,
    ModelUsage,
    parse_structured,
)
from decision_lens.llm.cached_provider import (
    DEFAULT_CACHE_PATH,
    PROVIDER_ID,
    CachedDemoProvider,
    CachedResponse,
    CacheMissError,
    DemoCache,
)

__all__ = [
    "DEFAULT_CACHE_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "PROVIDER_ID",
    "BaseModelProvider",
    "CacheMissError",
    "CachedDemoProvider",
    "CachedResponse",
    "DemoCache",
    "ModelError",
    "ModelOutputError",
    "ModelProvider",
    "ModelRequest",
    "ModelResponse",
    "ModelTimeout",
    "ModelUnavailable",
    "ModelUsage",
    "parse_structured",
]

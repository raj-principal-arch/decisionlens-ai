"""Model providers.

A vendor-neutral boundary between DecisionLens and whatever answers its calls.
Skills depend on `ModelProvider`, never on a vendor SDK, so the workflow can be
evaluated against a live model or replayed offline without changing a line of
analysis code.

    base.py              the contract, typed errors, structured-output parsing
    cached_provider.py   deterministic offline replay, no API key required
    anthropic_provider.py optional live adapter, needs the `live` extra
    factory.py           the single place cached-or-live is decided

The default path reaches no network and needs no credential. Importing this
package does not import any vendor SDK: the live adapter imports ``anthropic``
only when one is actually constructed.
"""

from decision_lens.llm.anthropic_provider import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    AnthropicNotInstalled,
    AnthropicProvider,
)
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
from decision_lens.llm.factory import build_provider

__all__ = [
    "DEFAULT_CACHE_PATH",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_TIMEOUT_SECONDS",
    "PROVIDER_ID",
    "AnthropicNotInstalled",
    "AnthropicProvider",
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
    "build_provider",
    "parse_structured",
]

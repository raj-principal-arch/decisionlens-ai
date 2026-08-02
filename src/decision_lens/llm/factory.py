"""Provider selection: the one place cached-or-live is decided.

Both rules live here rather than at each call site, because a rule enforced in
four places is a rule that will eventually be enforced in three:

*   **Live is opted into, never inferred.** Only ``MODEL_PROVIDER=anthropic``
    selects a paid provider. An ``ANTHROPIC_API_KEY`` sitting in the environment
    is not consent to spend money.
*   **No silent fallback.** Asking for live with a missing key, a malformed key,
    or the SDK uninstalled raises with instructions. It does not quietly serve
    recorded output while the reviewer believes they watched a live run — a brief
    whose provenance is wrong is worse than one that failed to generate.
"""

from __future__ import annotations

from pathlib import Path

from decision_lens.config import DEFAULT_ANTHROPIC_MODEL, ProviderChoice, Settings
from decision_lens.llm.anthropic_provider import AnthropicProvider
from decision_lens.llm.base import ModelProvider
from decision_lens.llm.cached_provider import CachedDemoProvider


def build_provider(
    settings: Settings | None = None,
    *,
    cache_path: Path | None = None,
) -> ModelProvider:
    """Construct the provider the settings ask for.

    Args:
        settings: Resolved configuration. Loaded from ``.env`` and the environment
            when omitted.
        cache_path: Override for the recorded-response file. Cached provider only.

    Raises:
        ConfigError: Live was requested but the credential is missing or malformed.
        AnthropicNotInstalled: Live was requested but the optional SDK is absent.
    """
    resolved = settings if settings is not None else Settings.load()

    if resolved.provider is ProviderChoice.ANTHROPIC:
        return AnthropicProvider(
            resolved.require_anthropic_key(),
            model=resolved.model_name or DEFAULT_ANTHROPIC_MODEL,
        )

    return CachedDemoProvider(cache_path)

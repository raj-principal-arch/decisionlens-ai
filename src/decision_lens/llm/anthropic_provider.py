"""Live Anthropic adapter.

The optional half of the pair. :class:`~decision_lens.llm.cached_provider.CachedDemoProvider`
replays recorded output for free and offline; this calls a real model and costs
real money. Which one runs is decided in :mod:`decision_lens.config`, explicitly,
never by inference.

What this adapter is careful about:

*   **The deadline is real, not decorative.** ``timeout_seconds`` is handed to the
    HTTP transport, so an overrunning call is cancelled rather than merely
    detected after the fact by :class:`~decision_lens.llm.base.BaseModelProvider`.
*   **No hidden retries.** SDK-level retrying is switched off. A transient overload
    surfaces as a named failed stage instead of silently tripling the wall clock
    and then being discarded by the base class for exceeding its own deadline.
    DecisionLens retries where retrying is meaningful — at the skill level, when a
    response is malformed — and nowhere else.
*   **Refusals and truncation are failures, not text.** ``stop_reason`` is checked
    before the content is read. A refused or cut-off response is not usable output,
    and letting either through as if it were an answer is the failure mode this
    product exists to prevent.
*   **The key is never logged.** It reaches the SDK constructor and nothing else.

Requires the optional dependency::

    pip install -e ".[live]"
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from decision_lens.config import DEFAULT_ANTHROPIC_MODEL
from decision_lens.llm.base import (
    BaseModelProvider,
    ModelOutputError,
    ModelRequest,
    ModelTimeout,
    ModelUnavailable,
    ModelUsage,
)

PROVIDER_ID = "anthropic"

#: Caps thinking plus response text together on current models. Sized to leave
#: adaptive thinking room while staying under the SDK's non-streaming timeout
#: guidance, since every skill returns a single compact JSON object.
DEFAULT_MAX_OUTPUT_TOKENS = 16_000


class AnthropicNotInstalled(ModelUnavailable):
    """The optional ``anthropic`` dependency is not installed."""


def _import_sdk(importer: Callable[[str], Any] = importlib.import_module) -> Any:
    """Import the optional SDK, turning its absence into an actionable message.

    The importer is a parameter so both outcomes are testable on a machine where
    the SDK is installed and on one where it is not.
    """
    try:
        return importer("anthropic")
    except ImportError as exc:
        raise AnthropicNotInstalled(
            "Live mode needs the Anthropic SDK, which is an optional dependency.\n"
            '  Install it with:  pip install -e ".[live]"\n'
            "  Or unset MODEL_PROVIDER to run the recorded demo, which needs nothing."
        ) from exc


@dataclass(frozen=True)
class _ErrorTypes:
    """The SDK exception classes this adapter maps onto DecisionLens errors.

    Resolved once from the SDK module rather than referenced inline, so the
    adapter can be exercised without the SDK installed and so the mapping is
    stated in one readable place.
    """

    timeout: type[BaseException]
    connection: type[BaseException]
    authentication: type[BaseException]
    permission: type[BaseException]
    not_found: type[BaseException]
    rate_limit: type[BaseException]
    status: type[BaseException]

    @classmethod
    def from_sdk(cls, sdk: Any) -> _ErrorTypes:
        return cls(
            timeout=sdk.APITimeoutError,
            connection=sdk.APIConnectionError,
            authentication=sdk.AuthenticationError,
            permission=sdk.PermissionDeniedError,
            not_found=sdk.NotFoundError,
            rate_limit=sdk.RateLimitError,
            status=sdk.APIStatusError,
        )


class AnthropicProvider(BaseModelProvider):
    """Calls a real Anthropic model.

    Args:
        api_key: Validated upstream by
            :meth:`~decision_lens.config.Settings.require_anthropic_key`. Passed
            to the SDK and held nowhere else.
        model: Model identifier. Defaults to
            :data:`~decision_lens.config.DEFAULT_ANTHROPIC_MODEL`.
        max_output_tokens: Per-call ceiling when the request does not set one.
        sdk: The ``anthropic`` module. The single seam for testing — supplying a
            stand-in keeps the whole suite offline, which is what lets these tests
            run in CI with no credential and no network.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        sdk: Any | None = None,
    ) -> None:
        resolved = sdk if sdk is not None else _import_sdk()
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._errors = _ErrorTypes.from_sdk(resolved)
        # max_retries=0: see the module docstring. Retrying belongs where it can
        # be reasoned about, not hidden inside the transport.
        self._client = resolved.Anthropic(api_key=api_key, max_retries=0)

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    @property
    def model_id(self) -> str:
        return self._model

    # -- request ------------------------------------------------------------- #

    def _payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": request.max_output_tokens or self._max_output_tokens,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.system:
            payload["system"] = request.system
        # `temperature` is deliberately absent. Current Anthropic models reject
        # it outright, and passing it would turn every call into a 400. A caller
        # who set one is told it was dropped rather than left to assume it applied.
        return payload

    def _call(self, request: ModelRequest) -> Any:
        client = self._client.with_options(timeout=request.timeout_seconds)
        try:
            return client.messages.create(**self._payload(request))
        except self._errors.timeout as exc:
            raise ModelTimeout(
                f"anthropic/{self._model} did not answer within "
                f"{request.timeout_seconds}s for skill {request.skill!r}: {exc}"
            ) from exc
        except self._errors.authentication as exc:
            raise ModelUnavailable(
                "Anthropic rejected the API key. Check the ANTHROPIC_API_KEY value in "
                f"your .env file. ({exc})"
            ) from exc
        except self._errors.permission as exc:
            raise ModelUnavailable(
                f"This API key is not permitted to use {self._model!r}. ({exc})"
            ) from exc
        except self._errors.not_found as exc:
            raise ModelUnavailable(
                f"Anthropic does not recognise the model {self._model!r}. Set MODEL_NAME "
                f"in your .env file to a model your key can reach. ({exc})"
            ) from exc
        except self._errors.rate_limit as exc:
            raise ModelUnavailable(
                f"Anthropic rate-limited the request for skill {request.skill!r}. "
                f"DecisionLens does not retry silently — rerun when the limit clears. ({exc})"
            ) from exc
        except self._errors.connection as exc:
            raise ModelUnavailable(f"Could not reach Anthropic: {exc}") from exc
        except self._errors.status as exc:
            raise ModelUnavailable(f"Anthropic returned an error: {exc}") from exc

    # -- response ------------------------------------------------------------ #

    @staticmethod
    def _text_of(response: Any) -> str:
        """Concatenate the text blocks, ignoring thinking and any other block type."""
        parts: list[str] = []
        for block in response.content or ():
            if getattr(block, "type", "") == "text":
                parts.append(str(block.text))
        return "".join(parts)

    def _check_stop_reason(self, response: Any, request: ModelRequest) -> None:
        stop_reason = getattr(response, "stop_reason", None)

        if stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) or "unspecified"
            raise ModelUnavailable(
                f"The model declined the request for skill {request.skill!r} "
                f"(category: {category}). No output was produced."
            )

        if stop_reason == "max_tokens":
            raise ModelOutputError(
                f"anthropic/{self._model} hit its output ceiling of "
                f"{request.max_output_tokens or self._max_output_tokens} tokens on skill "
                f"{request.skill!r}, so the response is cut off and its JSON is incomplete. "
                "Raise max_output_tokens for this call."
            )

    @staticmethod
    def _usage_of(response: Any) -> ModelUsage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return ModelUsage()

        def count(name: str) -> int | None:
            value = getattr(usage, name, None)
            return int(value) if isinstance(value, int) else None

        return ModelUsage(input_tokens=count("input_tokens"), output_tokens=count("output_tokens"))

    def _complete(self, request: ModelRequest) -> tuple[str, ModelUsage, tuple[str, ...]]:
        response = self._call(request)
        self._check_stop_reason(response, request)

        text = self._text_of(response)
        if not text.strip():
            raise ModelOutputError(
                f"anthropic/{self._model} returned no text for skill {request.skill!r}. "
                f"Stop reason: {getattr(response, 'stop_reason', None)!r}."
            )

        warnings: list[str] = []
        if request.temperature:
            warnings.append(
                f"temperature={request.temperature} was not sent. Current Anthropic models "
                "reject the parameter; steer the model through the prompt instead."
            )

        return text, self._usage_of(response), tuple(warnings)

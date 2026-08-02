"""The live Anthropic adapter, driven entirely offline.

Every test here runs against a stand-in for the SDK. Nothing imports the real
``anthropic`` package, nothing needs a credential, and nothing opens a socket —
which is the only way an adapter for a paid API can be tested in CI at all.

The stand-in mirrors the real exception hierarchy (``APITimeoutError`` under
``APIConnectionError``; the 4xx errors under ``APIStatusError``) so the ordering
of the adapter's handlers is genuinely exercised rather than assumed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from decision_lens.config import ProviderChoice, Settings
from decision_lens.llm import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    AnthropicNotInstalled,
    AnthropicProvider,
    CachedDemoProvider,
    ModelOutputError,
    ModelProvider,
    ModelRequest,
    ModelTimeout,
    ModelUnavailable,
    build_provider,
)
from decision_lens.llm.anthropic_provider import _import_sdk

KEY = "sk-ant-api03-REDACTEDTESTVALUE-9xyz"


# --------------------------------------------------------------------------- #
# A stand-in for the SDK
# --------------------------------------------------------------------------- #


class FakeAPIConnectionError(Exception):
    pass


class FakeAPITimeoutError(FakeAPIConnectionError):
    """Subclasses the connection error, as the real one does."""


class FakeAPIStatusError(Exception):
    pass


class FakeAuthenticationError(FakeAPIStatusError):
    pass


class FakePermissionDeniedError(FakeAPIStatusError):
    pass


class FakeNotFoundError(FakeAPIStatusError):
    pass


class FakeRateLimitError(FakeAPIStatusError):
    pass


class Block:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text


class Usage:
    def __init__(self, input_tokens: object = 1200, output_tokens: object = 340) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class StopDetails:
    def __init__(self, category: str) -> None:
        self.category = category


#: Sentinel so a test can ask for "no usage reported" without colliding with the
#: default of "usage reported normally".
_UNSET = object()


class Response:
    def __init__(
        self,
        content: list[Block] | None = None,
        *,
        stop_reason: str = "end_turn",
        usage: Any = _UNSET,
        stop_details: StopDetails | None = None,
    ) -> None:
        self.content = content if content is not None else [Block("text", '{"ok":true}')]
        self.stop_reason = stop_reason
        self.usage = Usage() if usage is _UNSET else usage
        self.stop_details = stop_details


class FakeStream:
    """Mirrors the SDK's streaming context manager.

    The adapter streams so it can request a large output ceiling without risking
    an HTTP timeout; it does not consume tokens as they arrive, so the double
    only needs the context-manager shape and `get_final_message`.
    """

    def __init__(self, response: Response) -> None:
        self._response = response

    def __enter__(self) -> FakeStream:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get_final_message(self) -> Response:
        return self._response


class FakeMessages:
    def __init__(self, client: FakeClient) -> None:
        self._client = client

    def stream(self, **kwargs: Any) -> FakeStream:
        self._client.calls.append(kwargs)
        if self._client.raises is not None:
            raise self._client.raises
        return FakeStream(self._client.response)


class FakeClient:
    def __init__(self, **construction: Any) -> None:
        self.construction = construction
        self.calls: list[dict[str, Any]] = []
        self.timeouts: list[float] = []
        self.response = Response()
        self.raises: Exception | None = None
        self.messages = FakeMessages(self)

    def with_options(self, *, timeout: float) -> FakeClient:
        self.timeouts.append(timeout)
        return self


class FakeSDK:
    """Exposes exactly the surface the adapter is allowed to depend on."""

    APIConnectionError = FakeAPIConnectionError
    APITimeoutError = FakeAPITimeoutError
    APIStatusError = FakeAPIStatusError
    AuthenticationError = FakeAuthenticationError
    PermissionDeniedError = FakePermissionDeniedError
    NotFoundError = FakeNotFoundError
    RateLimitError = FakeRateLimitError

    def __init__(self) -> None:
        self.client = FakeClient()

    def Anthropic(self, **kwargs: Any) -> FakeClient:  # noqa: N802 - mirrors the SDK
        self.client.construction = kwargs
        return self.client


@pytest.fixture
def sdk() -> FakeSDK:
    return FakeSDK()


@pytest.fixture
def provider(sdk: FakeSDK) -> AnthropicProvider:
    return AnthropicProvider(KEY, sdk=sdk)


def _request(**overrides: object) -> ModelRequest:
    base: dict[str, object] = {
        "skill": "contradictions",
        "prompt_version": "v1",
        "system": "You surface contradictions.",
        "user": "Find contradictions in the evidence.",
        "case_id": "sample_delivery_exceptions",
        "timeout_seconds": 90.0,
    }
    return ModelRequest(**{**base, **overrides})


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #


def test_it_satisfies_the_provider_contract(provider: AnthropicProvider) -> None:
    assert isinstance(provider, ModelProvider)
    assert provider.provider_id == "anthropic"
    assert provider.model_id == "claude-opus-5"
    assert provider.serves_cached_responses is False


def test_the_model_can_be_overridden(sdk: FakeSDK) -> None:
    assert AnthropicProvider(KEY, model="claude-sonnet-5", sdk=sdk).model_id == "claude-sonnet-5"


def test_sdk_retries_are_switched_off(provider: AnthropicProvider, sdk: FakeSDK) -> None:
    """Retrying belongs where it can be reasoned about, not inside the transport."""
    assert sdk.client.construction["max_retries"] == 0
    assert sdk.client.construction["api_key"] == KEY


def test_the_provider_does_not_retain_the_key_itself(provider: AnthropicProvider) -> None:
    assert "api_key" not in vars(provider)
    assert KEY not in repr(provider)


def test_a_missing_sdk_explains_how_to_install_it() -> None:
    def importer(_name: str) -> Any:
        raise ImportError("No module named 'anthropic'")

    with pytest.raises(AnthropicNotInstalled, match=r"\[live\]"):
        _import_sdk(importer)


def test_a_present_sdk_is_returned_unchanged(sdk: FakeSDK) -> None:
    assert _import_sdk(lambda _name: sdk) is sdk


# --------------------------------------------------------------------------- #
# The request
# --------------------------------------------------------------------------- #


def test_the_deadline_is_handed_to_the_transport(provider: AnthropicProvider, sdk: FakeSDK) -> None:
    """Cancelled, not merely detected after the fact."""
    provider.complete(_request(timeout_seconds=45.0))
    assert sdk.client.timeouts == [45.0]


def test_the_payload_carries_model_system_and_user(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    provider.complete(_request())
    (call,) = sdk.client.calls
    assert call["model"] == "claude-opus-5"
    assert call["system"] == "You surface contradictions."
    assert call["messages"] == [{"role": "user", "content": "Find contradictions in the evidence."}]


def test_an_empty_system_prompt_is_omitted_rather_than_sent_blank(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    provider.complete(_request(system=""))
    assert "system" not in sdk.client.calls[0]


def test_temperature_is_never_sent(provider: AnthropicProvider, sdk: FakeSDK) -> None:
    """Current Anthropic models reject it; sending it would 400 every call."""
    provider.complete(_request(temperature=0.7))
    assert "temperature" not in sdk.client.calls[0]


def test_a_dropped_temperature_is_reported_rather_than_swallowed(
    provider: AnthropicProvider,
) -> None:
    response = provider.complete(_request(temperature=0.7))
    assert any("temperature=0.7 was not sent" in w for w in response.warnings)


def test_no_warning_when_temperature_was_left_at_its_default(
    provider: AnthropicProvider,
) -> None:
    assert provider.complete(_request()).warnings == ()


def test_the_default_output_ceiling_applies(provider: AnthropicProvider, sdk: FakeSDK) -> None:
    provider.complete(_request())
    assert sdk.client.calls[0]["max_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS


def test_a_request_may_set_its_own_output_ceiling(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    provider.complete(_request(max_output_tokens=2048))
    assert sdk.client.calls[0]["max_tokens"] == 2048


def test_the_construction_default_can_be_lowered(sdk: FakeSDK) -> None:
    AnthropicProvider(KEY, max_output_tokens=4096, sdk=sdk).complete(_request())
    assert sdk.client.calls[0]["max_tokens"] == 4096


# --------------------------------------------------------------------------- #
# The response
# --------------------------------------------------------------------------- #


def test_a_successful_call_is_labelled_live_and_traceable(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    sdk.client.response = Response([Block("text", '{"ok":true}')])
    response = provider.complete(_request())

    assert response.text == '{"ok":true}'
    assert response.is_cached is False
    assert response.usage.input_tokens == 1200
    assert response.usage.output_tokens == 340

    stage = response.to_stage("contradictions")
    assert (stage.provider, stage.model) == ("anthropic", "claude-opus-5")
    assert stage.prompt_version == "v1"


def test_thinking_blocks_are_skipped_and_text_blocks_joined(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    sdk.client.response = Response(
        [Block("thinking", "internal reasoning"), Block("text", '{"a":'), Block("text", "1}")]
    )
    assert provider.complete(_request()).text == '{"a":1}'


def test_missing_usage_is_reported_as_unknown_not_zero(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    sdk.client.response = Response(usage=None)
    usage = provider.complete(_request()).usage
    assert usage.input_tokens is None
    assert usage.total_tokens is None


def test_non_integer_token_counts_are_discarded(provider: AnthropicProvider, sdk: FakeSDK) -> None:
    sdk.client.response = Response(usage=Usage(input_tokens=None, output_tokens="lots"))
    usage = provider.complete(_request()).usage
    assert usage.input_tokens is None
    assert usage.output_tokens is None


def test_a_refusal_is_a_failure_not_an_answer(provider: AnthropicProvider, sdk: FakeSDK) -> None:
    sdk.client.response = Response([], stop_reason="refusal", stop_details=StopDetails("cyber"))
    with pytest.raises(ModelUnavailable, match="cyber"):
        provider.complete(_request())


def test_a_refusal_without_a_category_still_fails_clearly(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    sdk.client.response = Response([], stop_reason="refusal")
    with pytest.raises(ModelUnavailable, match="unspecified"):
        provider.complete(_request())


def test_truncated_output_is_rejected_rather_than_parsed(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    """Cut-off JSON is not partial output; it is unusable output."""
    sdk.client.response = Response([Block("text", '{"ok":')], stop_reason="max_tokens")
    with pytest.raises(ModelOutputError, match="cut off"):
        provider.complete(_request())


def test_an_empty_response_is_an_error(provider: AnthropicProvider, sdk: FakeSDK) -> None:
    sdk.client.response = Response([Block("text", "   ")])
    with pytest.raises(ModelOutputError, match="returned no text"):
        provider.complete(_request())


def test_a_response_with_no_content_at_all_is_an_error(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    sdk.client.response = Response([])
    with pytest.raises(ModelOutputError, match="returned no text"):
        provider.complete(_request())


# --------------------------------------------------------------------------- #
# Failure mapping
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raised", "expected", "match"),
    [
        (FakeAPITimeoutError("slow"), ModelTimeout, "did not answer within 90.0s"),
        (FakeAuthenticationError("401"), ModelUnavailable, "rejected the API key"),
        (FakePermissionDeniedError("403"), ModelUnavailable, "not permitted"),
        (FakeNotFoundError("404"), ModelUnavailable, "does not recognise the model"),
        (FakeRateLimitError("429"), ModelUnavailable, "rate-limited"),
        (FakeAPIConnectionError("dns"), ModelUnavailable, "Could not reach Anthropic"),
        (FakeAPIStatusError("529"), ModelUnavailable, "returned an error"),
    ],
)
def test_sdk_failures_map_to_typed_model_errors(
    provider: AnthropicProvider,
    sdk: FakeSDK,
    raised: Exception,
    expected: type[Exception],
    match: str,
) -> None:
    sdk.client.raises = raised
    with pytest.raises(expected, match=match):
        provider.complete(_request())


def test_a_timeout_is_not_misreported_as_a_connection_failure(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    """APITimeoutError subclasses APIConnectionError, so handler order matters."""
    sdk.client.raises = FakeAPITimeoutError("slow")
    with pytest.raises(ModelTimeout):
        provider.complete(_request())


def test_an_auth_failure_is_not_misreported_as_a_generic_status_error(
    provider: AnthropicProvider, sdk: FakeSDK
) -> None:
    sdk.client.raises = FakeAuthenticationError("401")
    with pytest.raises(ModelUnavailable, match="rejected the API key"):
        provider.complete(_request())


# --------------------------------------------------------------------------- #
# Provider selection
# --------------------------------------------------------------------------- #


def test_the_default_build_is_the_cached_provider(tmp_path: Path) -> None:
    cache = tmp_path / "cache.json"
    cache.write_text('{"responses":{}}', encoding="utf-8")
    assert isinstance(build_provider(Settings(), cache_path=cache), CachedDemoProvider)


def test_a_key_alone_does_not_build_a_live_provider(tmp_path: Path) -> None:
    """The whole point of explicit selection, asserted at the factory too."""
    cache = tmp_path / "cache.json"
    cache.write_text('{"responses":{}}', encoding="utf-8")
    settings = Settings(anthropic_api_key=KEY)
    assert isinstance(build_provider(settings, cache_path=cache), CachedDemoProvider)


def test_selecting_anthropic_builds_the_live_provider(
    sdk: FakeSDK, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: dict[str, Any] = {}

    def spy(api_key: str, *, model: str) -> AnthropicProvider:
        built["api_key"] = api_key
        built["model"] = model
        return AnthropicProvider(api_key, model=model, sdk=sdk)

    monkeypatch.setattr("decision_lens.llm.factory.AnthropicProvider", spy)
    settings = Settings(
        provider=ProviderChoice.ANTHROPIC, anthropic_api_key=KEY, model_name="claude-sonnet-5"
    )
    provider = build_provider(settings)

    assert isinstance(provider, AnthropicProvider)
    assert built == {"api_key": KEY, "model": "claude-sonnet-5"}


def test_live_without_a_key_fails_instead_of_falling_back_to_cache() -> None:
    """A brief whose provenance is wrong is worse than one that failed to build."""
    from decision_lens.config import ConfigError

    with pytest.raises(ConfigError):
        build_provider(Settings(provider=ProviderChoice.ANTHROPIC))


def test_build_provider_loads_settings_when_none_are_passed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("MODEL_PROVIDER=\n", encoding="utf-8")
    cache = tmp_path / "cache.json"
    cache.write_text('{"responses":{}}', encoding="utf-8")
    assert isinstance(build_provider(cache_path=cache), CachedDemoProvider)

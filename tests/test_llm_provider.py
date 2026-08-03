"""The model-provider contract and the cached demo provider.

No test here touches the network, and one test enforces that by breaking sockets
for the duration of a real provider call.
"""

from __future__ import annotations

import socket
import time
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from decision_lens.llm import (
    BaseModelProvider,
    CachedDemoProvider,
    CachedResponse,
    CacheMissError,
    DemoCache,
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
from decision_lens.llm.cached_provider import DEFAULT_CACHE_PATH

RECORDED_AT = datetime(2026, 8, 1, 12, 0, 0)


def _request(**overrides: object) -> ModelRequest:
    base: dict[str, object] = {
        "skill": "contradictions",
        "prompt_version": "v1",
        "user": "Find contradictions in the evidence.",
        "case_id": "sample_delivery_exceptions",
    }
    return ModelRequest(**{**base, **overrides})


def _entry(key: str, text: str = '{"ok": true}', fingerprint: str = "abc123") -> CachedResponse:
    return CachedResponse(
        key=key,
        text=text,
        recorded_from_model="claude-opus-5",
        recorded_at=RECORDED_AT,
        prompt_fingerprint=fingerprint,
        input_tokens=1200,
        output_tokens=340,
    )


def _provider(*entries: CachedResponse) -> CachedDemoProvider:
    cache = DemoCache()
    for entry in entries:
        cache.add(entry)
    return CachedDemoProvider(cache_path=Path("unused.json"), cache=cache)


class TestRequestIdentity:
    def test_cache_key_excludes_prompt_wording(self) -> None:
        # Keying on rendered prompt text would invalidate every recorded response
        # on a typo fix and silently break the offline demo.
        a = _request(user="Find contradictions.")
        b = _request(user="Please identify any contradictions in the evidence below.")
        assert a.cache_key == b.cache_key

    def test_cache_key_separates_skill_case_and_version(self) -> None:
        base = _request()
        assert base.cache_key != _request(skill="alternatives").cache_key
        assert base.cache_key != _request(case_id="other_case").cache_key
        assert base.cache_key != _request(prompt_version="v2").cache_key

    def test_missing_case_id_still_produces_a_key(self) -> None:
        assert _request(case_id="").cache_key.startswith("default::")

    def test_empty_user_prompt_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _request(user="")

    def test_timeout_and_temperature_are_bounded(self) -> None:
        with pytest.raises(ValidationError):
            _request(timeout_seconds=0)
        with pytest.raises(ValidationError):
            _request(temperature=5.0)


class TestProtocolConformance:
    def test_cached_provider_satisfies_the_protocol(self) -> None:
        assert isinstance(_provider(), ModelProvider)

    def test_inheritance_is_not_required(self) -> None:
        class Adapter:
            @property
            def provider_id(self) -> str:
                return "vendor"

            @property
            def model_id(self) -> str:
                return "vendor-1"

            def complete(self, request: ModelRequest) -> ModelResponse:
                raise NotImplementedError

        assert isinstance(Adapter(), ModelProvider)

    def test_runtime_check_does_not_verify_signatures(self) -> None:
        # Same limitation as EvidenceSource: runtime_checkable tests attribute
        # presence only. Pinned so the suite does not imply stronger safety.
        class WrongShape:
            provider_id = "x"
            model_id = "y"

            def complete(self, wrong: int) -> str:
                return "not a ModelResponse"

        assert isinstance(WrongShape(), ModelProvider)

    def test_a_provider_is_not_cached_unless_it_says_so(self) -> None:
        # The default matters: any future live adapter reports live output as
        # live without having to remember to.
        class Live(BaseModelProvider):
            @property
            def provider_id(self) -> str:
                return "live"

            @property
            def model_id(self) -> str:
                return "live-1"

            def _complete(self, request: ModelRequest) -> tuple[str, ModelUsage, tuple[str, ...]]:
                return "{}", ModelUsage(), ()

        assert Live().serves_cached_responses is False
        assert Live().complete(_request()).is_cached is False

    def test_base_class_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            BaseModelProvider()  # type: ignore[abstract]


class TestCachedRetrieval:
    def test_a_recorded_response_is_returned(self) -> None:
        request = _request()
        provider = _provider(_entry(request.cache_key, text='{"found": 4}'))
        response = provider.complete(request)
        assert response.text == '{"found": 4}'
        assert response.skill == "contradictions"
        assert response.prompt_version == "v1"

    def test_repeated_calls_are_identical(self) -> None:
        request = _request()
        provider = _provider(_entry(request.cache_key))
        first, second = provider.complete(request), provider.complete(request)
        assert first.text == second.text
        assert first.is_cached == second.is_cached
        assert first.recorded_at == second.recorded_at

    def test_usage_is_carried_through(self) -> None:
        request = _request()
        response = _provider(_entry(request.cache_key)).complete(request)
        assert response.usage.input_tokens == 1200
        assert response.usage.output_tokens == 340
        assert response.usage.total_tokens == 1540

    def test_latency_is_measured_not_invented(self) -> None:
        request = _request()
        response = _provider(_entry(request.cache_key)).complete(request)
        assert response.latency_ms >= 0

    def test_the_cache_path_is_reported(self) -> None:
        assert _provider().cache_path == Path("unused.json")

    def test_known_keys_are_reported(self) -> None:
        provider = _provider(_entry("a::x::v1"), _entry("b::y::v1"))
        assert provider.known_keys() == ("a::x::v1", "b::y::v1")


class TestHonestLabelling:
    def test_a_cached_response_is_always_marked_cached(self) -> None:
        request = _request()
        assert _provider(_entry(request.cache_key)).complete(request).is_cached is True

    def test_provider_id_names_the_replay(self) -> None:
        assert _provider().provider_id == "cached-demo"

    def test_model_id_does_not_impersonate_a_model(self) -> None:
        # Reporting a real model id here would let a run trace read as though
        # that model had been called.
        assert _provider().model_id == "recorded-replay"

    def test_every_response_warns_that_it_is_replayed(self) -> None:
        request = _request()
        response = _provider(_entry(request.cache_key)).complete(request)
        assert any("Not a live model result" in w for w in response.warnings)
        assert any("claude-opus-5" in w for w in response.warnings)

    def test_the_recording_date_is_reported(self) -> None:
        request = _request()
        response = _provider(_entry(request.cache_key)).complete(request)
        assert response.recorded_at == RECORDED_AT

    def test_cached_status_reaches_the_run_trace(self) -> None:
        request = _request()
        response = _provider(_entry(request.cache_key)).complete(request)
        stage = response.to_stage("detect-contradictions")
        assert stage.provider == "cached-demo"
        assert stage.model == "recorded-replay"
        assert stage.prompt_version == "v1"
        assert stage.input_tokens == 1200
        assert stage.succeeded

    def test_a_failed_stage_records_the_error(self) -> None:
        request = _request()
        response = _provider(_entry(request.cache_key)).complete(request)
        stage = response.to_stage("detect-contradictions", error="provider timeout")
        assert not stage.succeeded


class TestPromptDrift:
    def test_a_changed_prompt_still_serves_but_warns(self) -> None:
        # The demo must not break on a prompt edit, but the drift must be visible.
        request = _request(prompt_fingerprint="new-fingerprint")
        provider = _provider(_entry(request.cache_key, fingerprint="old-fingerprint"))
        response = provider.complete(request)
        assert response.text
        assert any("prompt has changed" in w for w in response.warnings)

    def test_a_matching_prompt_produces_no_drift_warning(self) -> None:
        request = _request(prompt_fingerprint="same")
        response = _provider(_entry(request.cache_key, fingerprint="same")).complete(request)
        assert not any("prompt has changed" in w for w in response.warnings)

    def test_absent_fingerprints_do_not_warn(self) -> None:
        request = _request()
        response = _provider(_entry(request.cache_key, fingerprint="")).complete(request)
        assert not any("prompt has changed" in w for w in response.warnings)

    def test_the_warning_reaches_the_run_trace(self) -> None:
        """The gap that let two stale prompts run unnoticed for an evening.

        Everything above passed the whole time. The warning was built correctly
        and then dropped at the trace boundary, because `to_stage` did not carry
        it and `RunStage` had nowhere to put it. A warning that stops at the
        provider is not a warning anyone receives.
        """
        request = _request(prompt_fingerprint="new-fingerprint")
        provider = _provider(_entry(request.cache_key, fingerprint="old-fingerprint"))
        stage = provider.complete(request).to_stage("contradictions")
        assert any("prompt has changed" in w for w in stage.warnings)

    def test_a_clean_replay_still_says_it_was_a_replay(self) -> None:
        """The other warning must survive too, or the trace stops saying "cached"."""
        request = _request(prompt_fingerprint="same")
        stage = (
            _provider(_entry(request.cache_key, fingerprint="same"))
            .complete(request)
            .to_stage("contradictions")
        )
        assert any("Replayed from cache" in w for w in stage.warnings)
        assert not any("prompt has changed" in w for w in stage.warnings)


class TestCacheMiss:
    def test_a_miss_raises_rather_than_returning_a_placeholder(self) -> None:
        # A plausible stub flowing into a DecisionBrief is exactly the failure
        # this product exists to prevent.
        with pytest.raises(CacheMissError):
            _provider().complete(_request())

    def test_the_error_names_the_missing_key_and_what_is_available(self) -> None:
        provider = _provider(_entry("other::skill::v1"))
        with pytest.raises(CacheMissError) as exc:
            provider.complete(_request())
        message = str(exc.value)
        assert "sample_delivery_exceptions::contradictions::v1" in message
        assert "other::skill::v1" in message
        assert "placeholder is not" in message

    def test_an_empty_cache_says_so(self) -> None:
        with pytest.raises(CacheMissError, match="cache is empty"):
            _provider().complete(_request())

    def test_a_missing_cache_file_raises_clearly(self, tmp_path: Path) -> None:
        with pytest.raises(CacheMissError, match="No demo cache"):
            CachedDemoProvider(cache_path=tmp_path / "absent.json")

    def test_a_corrupt_cache_file_raises_clearly(self, tmp_path: Path) -> None:
        bad = tmp_path / "cache.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(CacheMissError, match="not readable"):
            CachedDemoProvider(cache_path=bad)


class TestCachePersistence:
    def test_a_cache_round_trips_through_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "cache.json"
        cache = DemoCache()
        cache.add(_entry("k::s::v1", text='{"n": 1}'))
        cache.save(path)

        provider = CachedDemoProvider(cache_path=path)
        response = provider.complete(_request(case_id="k", skill="s", prompt_version="v1"))
        assert response.text == '{"n": 1}'

    def test_the_shipped_cache_is_present_and_loadable(self) -> None:
        # The offline demo has to work from a fresh install with no API key.
        assert DEFAULT_CACHE_PATH.is_file()
        cache = DemoCache.load(DEFAULT_CACHE_PATH)
        assert "not live model results" in cache.notice.lower()

    def test_recording_overwrites_by_key(self) -> None:
        cache = DemoCache()
        cache.add(_entry("k::s::v1", text='{"n": 1}'))
        cache.add(_entry("k::s::v1", text='{"n": 2}'))
        assert len(cache.responses) == 1
        assert cache.responses["k::s::v1"].text == '{"n": 2}'


class TestStructuredOutput:
    class Finding(BaseModel):
        topic: str
        confidence: str

    def _response(self, text: str) -> ModelResponse:
        return ModelResponse(
            text=text,
            provider="cached-demo",
            model="recorded-replay",
            prompt_version="v1",
            skill="contradictions",
            latency_ms=5,
            is_cached=True,
        )

    def test_valid_output_is_parsed_into_a_typed_model(self) -> None:
        parsed = parse_structured(
            self._response('{"topic": "address errors", "confidence": "moderate"}'), self.Finding
        )
        assert parsed.topic == "address errors"

    def test_non_json_output_raises_a_clear_error(self) -> None:
        # Asserts the exact message rather than an alternation. A loose regex here
        # previously matched the wrong branch and hid unreachable code.
        with pytest.raises(ModelOutputError, match="does not match Finding"):
            parse_structured(self._response("I think the answer is..."), self.Finding)

    def test_wrong_shape_raises_rather_than_half_populating(self) -> None:
        # A skill that silently accepted this would put unverified content in a brief.
        with pytest.raises(ModelOutputError, match="does not match"):
            parse_structured(self._response('{"topic": "x"}'), self.Finding)

    def test_the_error_names_the_provider_and_skill(self) -> None:
        with pytest.raises(ModelOutputError) as exc:
            parse_structured(self._response("{}"), self.Finding)
        assert "cached-demo" in str(exc.value)
        assert "contradictions" in str(exc.value)


class TestNoNetwork:
    def test_a_cached_call_completes_with_sockets_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Enforced rather than asserted: if the provider ever gained a network
        # path, this test fails instead of quietly making calls.
        def blocked(*args: object, **kwargs: object) -> None:
            raise AssertionError("network access attempted")

        monkeypatch.setattr(socket, "socket", blocked)
        monkeypatch.setattr(socket, "create_connection", blocked)

        request = _request()
        response = _provider(_entry(request.cache_key)).complete(request)
        assert response.text

    def test_no_api_key_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        request = _request()
        assert _provider(_entry(request.cache_key)).complete(request).text


class TestUsageAccounting:
    def test_total_is_none_when_nothing_is_reported(self) -> None:
        assert ModelUsage().total_tokens is None

    def test_partial_usage_still_totals(self) -> None:
        assert ModelUsage(input_tokens=100).total_tokens == 100


class TestTimeoutEnforcement:
    """timeout_seconds must be behaviour, not a field nobody reads."""

    class Slow(BaseModelProvider):
        def __init__(self, seconds: float) -> None:
            self.seconds = seconds

        @property
        def provider_id(self) -> str:
            return "slow"

        @property
        def model_id(self) -> str:
            return "slow-1"

        def _complete(self, request: ModelRequest) -> tuple[str, ModelUsage, tuple[str, ...]]:
            time.sleep(self.seconds)
            return "{}", ModelUsage(), ()

    def test_overrunning_a_deadline_raises(self) -> None:
        with pytest.raises(ModelTimeout, match="exceeding its"):
            self.Slow(0.05).complete(_request(timeout_seconds=0.01))

    def test_the_overrunning_response_is_discarded_not_returned(self) -> None:
        # Detection is only useful if the late answer cannot be used anyway.
        with pytest.raises(ModelTimeout):
            self.Slow(0.05).complete(_request(timeout_seconds=0.01))

    def test_the_error_says_detection_is_not_cancellation(self) -> None:
        with pytest.raises(ModelTimeout) as exc:
            self.Slow(0.05).complete(_request(timeout_seconds=0.01))
        assert "not merely detected" in str(exc.value)

    def test_a_prompt_call_inside_its_deadline_succeeds(self) -> None:
        assert self.Slow(0.0).complete(_request(timeout_seconds=5.0)).text == "{}"


class TestErrorHierarchy:
    """The orchestrator handles partial failure with `except ModelError`.

    Every provider failure must therefore descend from it, or a dead provider
    aborts a run instead of degrading it.
    """

    @pytest.mark.parametrize(
        "error", [ModelTimeout, ModelUnavailable, ModelOutputError, CacheMissError]
    )
    def test_every_provider_error_is_a_model_error(self, error: type[ModelError]) -> None:
        assert issubclass(error, ModelError)
        with pytest.raises(ModelError):
            raise error("boom")

    def test_model_error_is_catchable_as_a_runtime_error(self) -> None:
        assert issubclass(ModelError, RuntimeError)

    def test_the_error_types_are_distinguishable(self) -> None:
        # A caller that wants to retry a timeout but not a malformed response
        # needs these to be separate types, not one error with a message.
        assert not issubclass(ModelTimeout, ModelOutputError)
        assert not issubclass(ModelOutputError, ModelTimeout)

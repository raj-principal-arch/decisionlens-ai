"""Capturing a live run for offline replay.

The property that matters: what gets recorded is exactly what a real run
produced, keyed so replaying it reproduces the same brief. Nothing here calls a
real model — the "live" provider is scripted, which is the only way to test a
recorder in CI.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from decision_lens.case import load_case
from decision_lens.llm import (
    CachedDemoProvider,
    DemoCache,
    ModelRequest,
    ModelResponse,
    ModelUnavailable,
    ModelUsage,
)
from decision_lens.models import EvidenceRecord, EvidenceRequest, UserContext
from decision_lens.orchestrator import DecisionLens
from decision_lens.recorder import (
    RecordingProvider,
    estimate_run,
    merge_into,
    record_case,
)
from decision_lens.report import to_markdown
from tests.scripted import CASE_ID, evidence_ids, write_case
from tests.scripted import _script as scripted_responses

CLOCK = datetime(2026, 8, 2, 9, 0, 0)


class FakeLive:
    """Stands in for a real provider. Answers per skill; may fail on demand."""

    provider_id = "anthropic"
    model_id = "claude-opus-5"

    def __init__(self, script: dict[str, object]) -> None:
        self.script = script
        self.calls: list[str] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request.skill)
        entry = self.script.get(request.skill)
        if isinstance(entry, Exception):
            raise entry
        if not isinstance(entry, str):
            raise ModelUnavailable(f"nothing scripted for {request.skill!r}")
        return ModelResponse(
            text=entry,
            provider=self.provider_id,
            model=self.model_id,
            prompt_version=request.prompt_version,
            skill=request.skill,
            latency_ms=11,
            usage=ModelUsage(input_tokens=1000, output_tokens=300),
            is_cached=False,
        )


@pytest.fixture
def case(tmp_path: Path) -> Path:
    return write_case(tmp_path)


def _script(case: Path, **overrides: object) -> dict[str, object]:
    script: dict[str, object] = dict(scripted_responses(evidence_ids(case)))
    # The baseline shares the DecisionLens output shape closely enough for a
    # recording test; what is under test is capture, not baseline quality.
    script["baseline"] = script["recommendation"]
    script.update(overrides)
    return script


# --------------------------------------------------------------------------- #
# Estimation
# --------------------------------------------------------------------------- #


def _records(case: Path) -> tuple[EvidenceRecord, ...]:
    return tuple(
        load_case(case).sources[0].retrieve(EvidenceRequest(requested_by=UserContext(user_id="pm")))
    )


def test_the_estimate_is_labelled_as_an_estimate() -> None:
    """A guess presented as a measurement is the habit this product argues against."""
    estimate = estimate_run((), calls=8)
    assert "estimate, not a measurement" in estimate.describe()
    assert estimate.calls == 8


def test_the_estimate_scales_with_the_evidence(case: Path) -> None:
    records = _records(case)
    small = estimate_run(records[:1], calls=8)
    large = estimate_run(records, calls=8)
    assert large.approx_input_tokens > small.approx_input_tokens
    assert large.evidence_records == len(records)


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #


def test_the_wrapper_captures_without_changing_the_response(case: Path) -> None:
    cache = DemoCache()
    inner = FakeLive(_script(case))
    recording = RecordingProvider(inner, cache, clock=CLOCK)

    request = ModelRequest(skill="relevance", prompt_version="v1", user="anything", case_id=CASE_ID)
    response = recording.complete(request)

    assert response.provider == "anthropic"
    assert recording.provider_id == "anthropic"
    assert recording.model_id == "claude-opus-5"
    assert cache.responses[f"{CASE_ID}::relevance::v1"].text == response.text
    assert cache.responses[f"{CASE_ID}::relevance::v1"].recorded_from_model == "claude-opus-5"


def test_recording_both_arms_captures_both(case: Path) -> None:
    """The demo is a comparison; a cache with one arm shows half the argument."""
    loaded = load_case(case)
    cache = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    assert summary.succeeded
    assert f"{CASE_ID}::baseline::v1" in summary.keys
    assert f"{CASE_ID}::recommendation::v1" in summary.keys
    assert len(summary.keys) == 8
    assert summary.input_tokens == 8000
    assert summary.output_tokens == 2400


def test_the_baseline_arm_can_be_skipped(case: Path) -> None:
    loaded = load_case(case)
    cache = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
        include_baseline=False,
    )
    assert not any(k.endswith("::baseline::v1") for k in summary.keys)
    assert len(summary.keys) == 7


def test_a_recorded_cache_reproduces_the_run_offline(case: Path, tmp_path: Path) -> None:
    """The whole point: record once, replay identically with no key."""
    loaded = load_case(case)
    cache = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    path = tmp_path / "recorded.json"
    cache.save(path)

    replayed = DecisionLens(
        CachedDemoProvider(path), loaded.sources, as_of=loaded.as_of, clock=CLOCK
    ).run(loaded.request)

    assert replayed.recommendation is not None
    assert not [i for i in replayed.validation_issues if i.blocks_presentation]
    assert "cached-demo" in to_markdown(replayed)


def test_a_failed_stage_is_reported_and_the_rest_is_still_kept(case: Path) -> None:
    """A partial cache with a named gap beats no cache."""
    loaded = load_case(case)
    cache = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case, contradictions=ModelUnavailable("overloaded"))),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    assert not summary.succeeded
    assert any("contradictions" in f for f in summary.failures)
    assert summary.keys, "the responses that did arrive were kept"
    assert "did not complete" in summary.describe()


def test_a_failed_baseline_is_reported_without_losing_the_other_arm(case: Path) -> None:
    loaded = load_case(case)
    cache = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case, baseline=ModelUnavailable("overloaded"))),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    assert any("baseline" in f for f in summary.failures)
    assert f"{CASE_ID}::recommendation::v1" in summary.keys


# --------------------------------------------------------------------------- #
# Writing to disk
# --------------------------------------------------------------------------- #


def test_merging_preserves_recordings_of_other_cases(tmp_path: Path) -> None:
    """Recording one case must not silently discard another."""
    from decision_lens.llm import CachedResponse

    path = tmp_path / "cache.json"
    existing = DemoCache()
    existing.add(
        CachedResponse(
            key="other_case::relevance::v1",
            text="{}",
            recorded_from_model="claude-opus-5",
            recorded_at=CLOCK,
        )
    )
    existing.save(path)

    fresh = DemoCache()
    fresh.add(
        CachedResponse(
            key="tiny_case::relevance::v1",
            text="{}",
            recorded_from_model="claude-opus-5",
            recorded_at=CLOCK,
        )
    )
    added, replaced, removed = merge_into(fresh, path)

    reloaded = DemoCache.load(path)
    assert (added, replaced) == (1, 0)
    assert set(reloaded.responses) == {"other_case::relevance::v1", "tiny_case::relevance::v1"}


def test_re_recording_replaces_rather_than_duplicates(tmp_path: Path) -> None:
    from decision_lens.llm import CachedResponse

    path = tmp_path / "cache.json"
    first = DemoCache()
    first.add(
        CachedResponse(
            key="tiny_case::relevance::v1",
            text='{"old": true}',
            recorded_from_model="claude-opus-5",
            recorded_at=CLOCK,
        )
    )
    first.save(path)

    second = DemoCache()
    second.add(
        CachedResponse(
            key="tiny_case::relevance::v1",
            text='{"new": true}',
            recorded_from_model="claude-opus-5",
            recorded_at=CLOCK,
        )
    )
    added, replaced, removed = merge_into(second, path)

    assert (added, replaced, removed) == (0, 1, 0)
    assert DemoCache.load(path).responses["tiny_case::relevance::v1"].text == '{"new": true}'


def test_merging_into_a_missing_file_creates_it(tmp_path: Path) -> None:
    from decision_lens.llm import CachedResponse

    path = tmp_path / "nested" / "cache.json"
    cache = DemoCache()
    cache.add(
        CachedResponse(
            key="k::relevance::v1",
            text="{}",
            recorded_from_model="claude-opus-5",
            recorded_at=CLOCK,
        )
    )
    added, replaced, removed = merge_into(cache, path)
    assert (added, replaced, removed) == (1, 0, 0)
    assert path.is_file()


def test_a_case_with_no_evidence_still_records_the_baseline_arm(tmp_path: Path) -> None:
    """Both arms must see the same evidence, even when that is none of it.

    The orchestrator returns early on an empty evidence set, so the baseline has
    to retrieve for itself rather than silently running against nothing while
    the other arm ran against something.
    """
    import json as _json

    directory = tmp_path / "empty_case"
    directory.mkdir()
    (directory / "case_manifest.json").write_text(
        _json.dumps(
            {
                "case_id": "empty_case",
                "question": "Should we defer this entirely?",
                "as_of": "2026-08-02",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_case(directory)
    cache = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(
            {"baseline": scripted_responses(evidence_ids(write_case(tmp_path)))["recommendation"]}
        ),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    assert "empty_case::baseline::v1" in summary.keys


# --------------------------------------------------------------------------- #
# A rejected response must never be cached
# --------------------------------------------------------------------------- #


def test_a_response_its_own_stage_rejected_is_not_cached(case: Path) -> None:
    """Found on the first real recording run, not by reading the code.

    A response can arrive intact over HTTP and still be refused by the skill that
    asked for it. Caching one would ship a known-bad answer labelled as a
    recorded result, and every later replay would fail the same check.
    """
    loaded = load_case(case)
    cache = DemoCache()
    # Valid JSON for the shape, but it answers none of the eight questions, so
    # the challenger's own requirements reject it.
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case, challenger='{"findings": []}')),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    key = f"{CASE_ID}::challenger::v1"
    assert key not in cache.responses, "the rejected response was discarded"
    assert key in summary.dropped
    assert key not in summary.keys
    assert any("challenger" in f for f in summary.failures)
    assert "discarded as unusable" in summary.describe()
    assert f"  - {key}" in summary.describe()


def test_a_rejected_baseline_is_not_cached_either(case: Path) -> None:
    loaded = load_case(case)
    cache = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case, baseline="not json at all")),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    assert not [k for k in cache.responses if "baseline" in k]
    assert any("baseline" in k for k in summary.dropped)


def test_re_recording_removes_a_previously_cached_bad_response(case: Path, tmp_path: Path) -> None:
    """The already-poisoned entry has to go, not merely be left in place."""
    from decision_lens.llm import CachedResponse

    path = tmp_path / "cache.json"
    poisoned = DemoCache()
    poisoned.add(
        CachedResponse(
            key=f"{CASE_ID}::challenger::v1",
            text='{"findings": []}',
            recorded_from_model="claude-opus-5",
            recorded_at=CLOCK,
        )
    )
    poisoned.save(path)

    loaded = load_case(case)
    cache = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case, challenger='{"findings": []}')),
        cache=cache,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    added, replaced, removed = merge_into(cache, path, drop=summary.dropped)

    assert removed == 1
    assert f"{CASE_ID}::challenger::v1" not in DemoCache.load(path).responses


def test_the_live_deadline_allows_the_output_ceiling_to_be_reached() -> None:
    """The two constants are coupled; a test so they cannot drift apart.

    A deadline shorter than the time it takes to emit `max_tokens` converts a
    response that was going to arrive into a timeout — swapping one failure for
    another. 40 tokens/second is a deliberately pessimistic floor.
    """
    from decision_lens.llm.anthropic_provider import DEFAULT_MAX_OUTPUT_TOKENS
    from decision_lens.recorder import LIVE_SKILL_TIMEOUT_SECONDS

    slowest_plausible_tokens_per_second = 40
    needed = DEFAULT_MAX_OUTPUT_TOKENS / slowest_plausible_tokens_per_second
    assert needed <= LIVE_SKILL_TIMEOUT_SECONDS, (
        f"{LIVE_SKILL_TIMEOUT_SECONDS}s cannot deliver {DEFAULT_MAX_OUTPUT_TOKENS} tokens; "
        f"about {needed:.0f}s is needed. Raise the deadline or lower the ceiling."
    )


# --------------------------------------------------------------------------- #
# Progress
# --------------------------------------------------------------------------- #


def test_each_stage_is_announced_before_and_after(case: Path) -> None:
    """A run writes nothing to disk until the end, so the only signal is this."""
    loaded = load_case(case)
    lines: list[str] = []
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        progress=lines.append,
    )

    assert any(line.endswith("relevance …") for line in lines), "announced before it runs"
    assert any("relevance —" in line and "in /" in line for line in lines), "and after"
    for stage in ("classification", "recommendation", "challenger", "baseline"):
        assert any(stage in line for line in lines), stage


def test_the_counter_shows_how_much_is_left(case: Path) -> None:
    loaded = load_case(case)
    lines: list[str] = []
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        progress=lines.append,
    )
    assert any("[1/8]" in line for line in lines)
    assert any("[8/8]" in line for line in lines)


def test_the_counter_knows_the_baseline_was_skipped(case: Path) -> None:
    loaded = load_case(case)
    lines: list[str] = []
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        include_baseline=False,
        progress=lines.append,
    )
    assert any("[7/7]" in line for line in lines)
    assert not any("[8/" in line for line in lines)


def test_a_failing_stage_says_so_immediately(case: Path) -> None:
    """Waiting twenty minutes to learn stage two died is not acceptable."""
    loaded = load_case(case)
    lines: list[str] = []
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case, contradictions=ModelUnavailable("overloaded"))),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        progress=lines.append,
    )
    assert any("contradictions — failed after" in line for line in lines)
    assert any("ModelUnavailable" in line for line in lines)


def test_progress_is_optional(case: Path) -> None:
    """Nothing may depend on someone listening."""
    loaded = load_case(case)
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    assert summary.succeeded


def test_the_summary_reports_wall_clock_time(case: Path) -> None:
    loaded = load_case(case)
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    assert summary.elapsed_seconds > 0
    assert "in 0m" in summary.describe()

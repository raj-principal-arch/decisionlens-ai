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
from decision_lens.prompts.baseline import BASELINE_V2
from decision_lens.recorder import (
    CHAINED_STAGES,
    EXPECTED_STAGES,
    RecordingProvider,
    current_stage_versions,
    estimate_run,
    merge_into,
    record_case,
    stages_worth_reusing,
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
    assert f"{CASE_ID}::baseline::{BASELINE_V2.version}" in summary.keys
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
    assert not any("::baseline::" in k for k in summary.keys)
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

    assert f"empty_case::baseline::{BASELINE_V2.version}" in summary.keys


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


# --------------------------------------------------------------------------- #
# Resume
# --------------------------------------------------------------------------- #


def test_resuming_reuses_what_was_already_recorded(case: Path) -> None:
    """A recording costs real money; re-buying stages that worked is waste."""
    loaded = load_case(case)
    first = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=first,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    live = FakeLive(_script(case))
    second = DemoCache()
    summary = record_case(
        loaded.request,
        loaded.sources,
        live,
        cache=second,
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=first,
    )

    assert live.calls == [], "nothing was called a second time"
    assert len(summary.reused) == 8
    assert len(summary.keys) == 8
    assert summary.succeeded


def test_resuming_still_calls_for_what_is_missing(case: Path) -> None:
    loaded = load_case(case)
    partial = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=partial,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    # Force two stages to be recorded again.
    for skill in ("alternatives", "recommendation"):
        del partial.responses[f"{CASE_ID}::{skill}::v1"]

    live = FakeLive(_script(case))
    summary = record_case(
        loaded.request,
        loaded.sources,
        live,
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=partial,
    )

    # `challenger` is re-recorded too: it reads the alternatives and the
    # recommendation, so a cached one would have been produced from state that
    # no longer exists.
    assert live.calls == ["alternatives", "recommendation", "challenger"]
    assert len(summary.reused) == 5
    assert len(summary.keys) == 8


def test_a_reused_stage_is_announced(case: Path) -> None:
    """Reuse is never silent — otherwise it is indistinguishable from stale."""
    loaded = load_case(case)
    first = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=first,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    lines: list[str] = []
    summary = record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=first,
        progress=lines.append,
    )
    assert any("reused an earlier recording" in line for line in lines)
    assert "were reused, not called" in summary.describe()
    assert summary.describe().count("  ~ ") == 8


def test_without_resume_everything_is_called_again(case: Path) -> None:
    loaded = load_case(case)
    first = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=first,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    live = FakeLive(_script(case))
    summary = record_case(
        loaded.request,
        loaded.sources,
        live,
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    assert len(live.calls) == 8
    assert summary.reused == []


# --------------------------------------------------------------------------- #
# Resume must not stitch together stages that never saw each other
# --------------------------------------------------------------------------- #


def test_stages_after_a_gap_are_not_reusable() -> None:
    from decision_lens.recorder import stages_worth_reusing

    cached = {"relevance", "classification", "contradictions", "recommendation", "baseline"}
    # missing_evidence is the gap; everything chained after it is stale.
    assert stages_worth_reusing(cached) == {
        "relevance",
        "classification",
        "contradictions",
        "baseline",
    }


def test_the_baseline_is_reusable_however_broken_the_chain_is() -> None:
    """It is one call over the same evidence and depends on none of the chain."""
    from decision_lens.recorder import stages_worth_reusing

    assert stages_worth_reusing({"baseline"}) == {"baseline"}


def test_a_complete_cache_is_entirely_reusable() -> None:
    from decision_lens.recorder import EXPECTED_STAGES, stages_worth_reusing

    assert stages_worth_reusing(set(EXPECTED_STAGES)) == set(EXPECTED_STAGES)


def test_re_recording_a_stage_forces_everything_downstream_to_re_record(case: Path) -> None:
    """The bug this prevents produced a recommendation selecting nothing.

    A live run re-recorded `alternatives` and reused the `recommendation` and
    `challenger` from a run where alternatives had failed. The cache then held
    eleven options beside a recommendation that selected none of them.
    """
    loaded = load_case(case)
    complete = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=complete,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    # Only `alternatives` is missing; the stages after it are present but stale.
    del complete.responses[f"{CASE_ID}::alternatives::v1"]

    live = FakeLive(_script(case))
    record_case(
        loaded.request,
        loaded.sources,
        live,
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=complete,
    )

    assert live.calls == ["alternatives", "recommendation", "challenger"], (
        "recommendation and challenger must be recorded again, not reused"
    )


def test_a_re_record_is_announced_as_such(case: Path) -> None:
    loaded = load_case(case)
    complete = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=complete,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    del complete.responses[f"{CASE_ID}::alternatives::v1"]

    lines: list[str] = []
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=complete,
        progress=lines.append,
    )
    assert any("an earlier stage it depends on was re-recorded" in line for line in lines)


def test_the_baseline_is_still_reused_when_the_chain_is_re_recorded(case: Path) -> None:
    loaded = load_case(case)
    complete = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=complete,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    del complete.responses[f"{CASE_ID}::relevance::v1"]

    live = FakeLive(_script(case))
    summary = record_case(
        loaded.request,
        loaded.sources,
        live,
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=complete,
    )
    assert "baseline" not in live.calls
    assert f"{CASE_ID}::baseline::{BASELINE_V2.version}" in summary.reused


# --------------------------------------------------------------------------- #
# What the cache that actually ships can replay
# --------------------------------------------------------------------------- #


def _shipped_keys() -> set[str]:
    import json

    from decision_lens.llm.cached_provider import DEFAULT_CACHE_PATH

    if not DEFAULT_CACHE_PATH.exists():
        pytest.skip("no cache has been recorded yet")
    payload = json.loads(DEFAULT_CACHE_PATH.read_text(encoding="utf-8"))
    keys = set(payload.get("responses", {}))
    if not keys:
        pytest.skip("the shipped cache is empty")
    return keys


def test_the_shipped_cache_replays_the_whole_decisionlens_chain() -> None:
    """The offline demo is the only thing most readers will run. It must be whole."""
    stages = {k.split("::")[1] for k in _shipped_keys()}
    assert set(CHAINED_STAGES) <= stages


def test_the_shipped_cache_has_no_key_stranded_by_a_version_bump() -> None:
    """A recording keyed to a superseded prompt can never be read again.

    It is not corrupt, but it must never be mistaken for coverage, and it is
    dead weight in a file that ships with the repository — dropping the one
    stranded `baseline::v1` entry took the cache from 326 KB to 228 KB.

    The accepted set is deliberately empty. A prompt version bump is allowed at
    any time; what is not allowed is leaving the cache behind, because the
    result is a demo that silently loses a stage or a resumed run that costs
    money nobody previewed. `make record-resume` re-records only what moved.
    """
    from decision_lens.prompts import REGISTRY

    accepted: set[str] = set()
    stranded = set()
    for key in _shipped_keys():
        _, stage, version = key.split("::")
        name = "baseline" if stage == "baseline" else stage
        try:
            current = REGISTRY.latest(name).version
        except KeyError:  # pragma: no cover - a stage with no registered prompt
            continue
        if version != current:
            stranded.add(stage)

    assert stranded == accepted


# --------------------------------------------------------------------------- #
# The version a resumed run will actually ask for
# --------------------------------------------------------------------------- #


def test_stage_versions_cover_every_stage_a_run_records() -> None:
    assert set(current_stage_versions()) == set(EXPECTED_STAGES)


def test_stage_versions_match_the_prompt_each_stage_really_uses() -> None:
    """`current_stage_versions` trusts the registry's `latest`. This is why.

    It is only correct while every stage runs its newest registered prompt. The
    moment a skill pins an older version while a newer one is also registered,
    `latest` starts answering a question nobody asked and the resume preview
    goes back to lying about cost. Restating the mapping independently here is
    the point: if the two disagree, the assumption has expired.
    """
    from decision_lens.prompts.baseline import BASELINE_V2
    from decision_lens.prompts.decisionlens import (
        ALTERNATIVES_V1,
        CHALLENGER_V1,
        CLASSIFICATION_V2,
        CONTRADICTIONS_V2,
        MISSING_EVIDENCE_V1,
        RECOMMENDATION_V1,
        RELEVANCE_V1,
    )

    assert current_stage_versions() == {
        "relevance": RELEVANCE_V1.version,
        "classification": CLASSIFICATION_V2.version,
        "contradictions": CONTRADICTIONS_V2.version,
        "missing_evidence": MISSING_EVIDENCE_V1.version,
        "alternatives": ALTERNATIVES_V1.version,
        "recommendation": RECOMMENDATION_V1.version,
        "challenger": CHALLENGER_V1.version,
        "baseline": BASELINE_V2.version,
    }


def test_a_stage_recorded_under_a_superseded_prompt_is_not_reusable() -> None:
    """The bug this guards printed "$0.00" and then billed a real call.

    Matching on the stage name alone treats any recording of `baseline` as
    coverage, whatever prompt produced it. Reuse has to be judged on the whole
    key, because that is what the recorder looks up.
    """
    versions = current_stage_versions()
    prefix = f"{CASE_ID}::"
    # Every stage recorded, but the baseline under the prompt it no longer uses.
    responses: dict[str, object] = {f"{prefix}{stage}::{v}": {} for stage, v in versions.items()}
    del responses[f"{prefix}baseline::{versions['baseline']}"]
    responses[f"{prefix}baseline::v0"] = {}

    cached = set()
    for entry in responses:
        stage, _, version = entry[len(prefix) :].partition("::")
        if versions.get(stage) == version:
            cached.add(stage)

    assert "baseline" not in cached
    assert "baseline" not in stages_worth_reusing(cached)
    assert set(CHAINED_STAGES) <= stages_worth_reusing(cached)


@pytest.mark.parametrize(
    ("calls", "expected"),
    [(1, "1 model call over"), (0, "0 model calls over"), (8, "8 model calls over")],
)
def test_the_estimate_counts_calls_in_readable_english(calls: int, expected: str) -> None:
    assert expected in estimate_run((), calls=calls).describe()


def _without_moments(value: object) -> object:
    """Replace every datetime with a sentinel, wherever it sits in the tree.

    Deliberately not a list of field names. Comparing two runs by hand-listing
    `retrieved_at, generated_at, ...` misses one the moment a model grows a
    field, and the comparison then reports a difference that is only a clock —
    which is exactly how a determinism check first came back False here.
    Matching on the type cannot go stale.
    """
    if isinstance(value, datetime):
        return "<moment>"
    if isinstance(value, dict):
        return {k: _without_moments(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_without_moments(v) for v in value]
    return value


def test_the_shipped_cache_replays_the_same_brief_every_time() -> None:
    """The demo is the artifact most readers will actually run.

    Two runs off the same recording must agree on every conclusion. Anything
    else means a reviewer and the author can look at the same command and see
    different recommendations, which would undo the point of recording at all.
    """
    from decision_lens.case import bundled_case_dir
    from decision_lens.llm.cached_provider import DEFAULT_CACHE_PATH

    _shipped_keys()  # skips when nothing has been recorded yet
    loaded = load_case(bundled_case_dir())

    def once() -> dict[str, object]:
        provider = CachedDemoProvider(DEFAULT_CACHE_PATH)
        brief = DecisionLens(provider, loaded.sources, as_of=loaded.as_of).run(loaded.request)
        stripped = _without_moments(brief.model_dump())
        assert isinstance(stripped, dict)
        return stripped

    first, second = once(), once()
    assert first == second
    # Two empty briefs are also equal. Pin that a real one was compared.
    assert first["recommendation"] is not None
    claims, options = first["claims"], first["alternatives"]
    assert isinstance(claims, list) and isinstance(options, list)
    assert len(claims) > 1 and len(options) > 1


def test_the_determinism_check_would_notice_a_real_difference() -> None:
    """Guards the guard: a comparison that strips too much always passes."""
    a = {"support": "low", "at": datetime(2026, 8, 2, 9, 0)}
    b = {"support": "strong", "at": datetime(2026, 8, 2, 10, 30)}
    assert _without_moments(a) != _without_moments(b)
    assert _without_moments(a) == _without_moments({**a, "at": datetime(2020, 1, 1)})


def test_every_shipped_recording_answers_the_prompt_that_is_still_asked() -> None:
    """Version matching is not enough. The fingerprint is the real check.

    A version is a human declaration and humans forget to bump it; the
    fingerprint is derived from the prompt text itself. If someone edits a
    prompt and leaves the version alone, the cache keeps serving an answer to
    the question that used to be asked and the demo quietly stops meaning what
    it says. This is the whole reason `Prompt.fingerprint` exists.
    """
    import json

    from decision_lens.llm.cached_provider import DEFAULT_CACHE_PATH
    from decision_lens.prompts import REGISTRY

    _shipped_keys()  # skips when nothing has been recorded yet
    payload = json.loads(DEFAULT_CACHE_PATH.read_text(encoding="utf-8"))

    # No exceptions. Both stale entries were re-recorded and the superseded v1
    # keys dropped, so every shipped recording answers a prompt that still
    # exists. Keeping an allowance here "just in case" would let the next drift
    # settle in quietly, which is exactly how the last one survived an evening.
    known_stale: set[str] = set()

    mismatched = set()
    for key, entry in payload["responses"].items():
        _, stage, version = key.split("::")
        recorded = entry.get("prompt_fingerprint")
        if not recorded:
            continue
        if recorded != REGISTRY.get(stage, version).fingerprint:
            mismatched.add(stage)

    unexpected = mismatched - known_stale
    assert not unexpected, (
        f"prompt text changed without a version bump for: {sorted(unexpected)}. "
        "Bump the version and re-record with `make record-resume`."
    )
    healed = known_stale - mismatched
    assert not healed, (
        f"{sorted(healed)} now matches its prompt — drop it from known_stale so the "
        "exception cannot outlive the problem."
    )


def test_a_resumed_run_refuses_an_entry_whose_prompt_text_changed(case: Path) -> None:
    """Version is a declaration; fingerprint is derived. Trust the derived one.

    Two prompts were edited after being recorded and left at v1, so every
    resumed run went on replaying answers to wording that no longer existed.
    Announcing the reuse did not help — the announcement looked the same either
    way. Matching on the fingerprint makes the mistake unrepeatable.
    """
    loaded = load_case(case)
    seed = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=seed,
        as_of=loaded.as_of,
        clock=CLOCK,
    )

    # Same key, same version — but recorded from different prompt text.
    versions = current_stage_versions()
    stale_key = f"{CASE_ID}::contradictions::{versions['contradictions']}"
    original = seed.responses[stale_key]
    seed.responses[stale_key] = original.model_copy(update={"prompt_fingerprint": "0" * 64})

    live = FakeLive(_script(case))
    summary = record_case(
        loaded.request,
        loaded.sources,
        live,
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=seed,
    )

    assert "contradictions" in live.calls, "the stale entry must not have been served"
    assert stale_key not in summary.reused
    # relevance and classification precede it and were untouched, so they stand.
    assert f"{CASE_ID}::relevance::{versions['relevance']}" in summary.reused
    assert f"{CASE_ID}::classification::{versions['classification']}" in summary.reused


def test_an_entry_recorded_before_fingerprints_were_stored_is_still_reusable(
    case: Path,
) -> None:
    """Absent is not mismatched. Refusing a blank would re-buy the whole cache."""
    loaded = load_case(case)
    seed = DemoCache()
    record_case(
        loaded.request,
        loaded.sources,
        FakeLive(_script(case)),
        cache=seed,
        as_of=loaded.as_of,
        clock=CLOCK,
    )
    key = f"{CASE_ID}::contradictions::{current_stage_versions()['contradictions']}"
    seed.responses[key] = seed.responses[key].model_copy(update={"prompt_fingerprint": None})

    live = FakeLive(_script(case))
    summary = record_case(
        loaded.request,
        loaded.sources,
        live,
        cache=DemoCache(),
        as_of=loaded.as_of,
        clock=CLOCK,
        resume_from=seed,
    )
    assert "contradictions" not in live.calls
    assert key in summary.reused

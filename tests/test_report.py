"""The reviewer-facing artifact.

What matters here is not prettiness but three properties a reader depends on:
both required notices are present verbatim, the checks appear before the answer,
and the PM decision section exists whether or not a decision was made.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from decision_lens import report
from decision_lens.case import load_case
from decision_lens.llm import CachedDemoProvider
from decision_lens.models import (
    DECISION_OWNER_NOTICE,
    SYNTHETIC_DATA_NOTICE,
    DecisionBrief,
    RunStage,
    RunTrace,
)
from decision_lens.orchestrator import DecisionLens, record_pm_decision
from tests.scripted import case_with_cache

CLOCK = datetime(2026, 8, 2, 9, 0, 0)


@pytest.fixture
def brief(tmp_path: Path) -> DecisionBrief:
    directory, cache = case_with_cache(tmp_path)
    loaded = load_case(directory)
    lens = DecisionLens(CachedDemoProvider(cache), loaded.sources, as_of=loaded.as_of, clock=CLOCK)
    return lens.run(loaded.request)


@pytest.fixture
def markdown(brief: DecisionBrief) -> str:
    return report.to_markdown(brief)


# --------------------------------------------------------------------------- #
# The required notices
# --------------------------------------------------------------------------- #


def test_both_required_notices_appear_verbatim(markdown: str) -> None:
    assert SYNTHETIC_DATA_NOTICE in markdown
    assert DECISION_OWNER_NOTICE in markdown


def test_the_notices_come_from_the_model_layer(brief: DecisionBrief) -> None:
    """Rendered from the constants, so wording cannot drift between the two."""
    payload = json.loads(report.to_json(brief))
    assert payload["notices"]["synthetic_data"] == SYNTHETIC_DATA_NOTICE
    assert payload["notices"]["decision_owner"] == DECISION_OWNER_NOTICE


# --------------------------------------------------------------------------- #
# Order and completeness
# --------------------------------------------------------------------------- #


def test_the_checks_are_read_before_the_recommendation(markdown: str) -> None:
    """An error means the answer should not be read as it stands.

    Putting that after the answer puts it where nobody looks.
    """
    assert markdown.index("## Checks") < markdown.index("## Recommendation")


def test_the_evidence_is_read_before_the_recommendation(markdown: str) -> None:
    assert markdown.index("## What the evidence says") < markdown.index("## Recommendation")
    assert markdown.index("## Contradictions") < markdown.index("## Recommendation")
    assert markdown.index("## Missing evidence") < markdown.index("## Recommendation")


@pytest.mark.parametrize(
    "heading",
    [
        "## The question",
        "## Checks",
        "## What the evidence says",
        "### Facts",
        "### Assumptions",
        "### Stakeholder opinions",
        "### Constraints",
        "## Contradictions",
        "## Missing evidence",
        "## Alternatives considered",
        "## Recommendation",
        "## Tradeoffs and risks",
        "## What to test before investing",
        "## The product manager's decision",
        "## Evidence",
        "## Run trace",
    ],
)
def test_every_required_section_is_rendered(markdown: str, heading: str) -> None:
    assert heading in markdown


def test_success_and_guardrail_metrics_are_separated(markdown: str) -> None:
    """Collapsing them would hide the metrics that exist to catch harm."""
    assert "**Success metrics**" in markdown
    assert "**Guardrail metrics**" in markdown
    assert "exception rate" in markdown
    assert "checkout completion" in markdown


# --------------------------------------------------------------------------- #
# Traceability
# --------------------------------------------------------------------------- #


def test_claims_carry_their_citations_inline(brief: DecisionBrief, markdown: str) -> None:
    for claim in brief.claims:
        for citation in claim.citations:
            assert f"[{citation.evidence_id}]" in markdown


def test_the_evidence_section_reproduces_the_text_a_reader_must_check(
    brief: DecisionBrief, markdown: str
) -> None:
    for record in brief.evidence:
        assert record.content.strip() in markdown


def test_evidence_nobody_cited_is_marked_as_such(tmp_path: Path) -> None:
    """Retrieved but unused evidence is where a missed contradiction hides."""
    directory, cache = case_with_cache(tmp_path)
    # Added after the cache was built, so no scripted response cites it.
    (directory / "unused.md").write_text(
        "# Warehouse\n\nPallet labelling was standardised in March.\n", encoding="utf-8"
    )

    loaded = load_case(directory)
    lens = DecisionLens(CachedDemoProvider(cache), loaded.sources, as_of=loaded.as_of, clock=CLOCK)
    rendered = report.to_markdown(lens.run(loaded.request))
    assert "never cited" in rendered


def test_the_run_trace_pins_provider_and_model(markdown: str) -> None:
    assert "cached-demo" in markdown
    assert "recorded-replay" in markdown


def test_support_is_labelled_as_a_judgment_not_a_probability(markdown: str) -> None:
    assert "a qualitative judgment, not a probability" in markdown


# --------------------------------------------------------------------------- #
# The PM's decision
# --------------------------------------------------------------------------- #


def test_the_decision_section_exists_even_when_none_was_made(markdown: str) -> None:
    """The space for it is in every brief, so the boundary is visible."""
    assert "## The product manager's decision" in markdown
    assert "Not yet recorded" in markdown


def test_a_recorded_decision_is_rendered(brief: DecisionBrief) -> None:
    decision = record_pm_decision(
        brief,
        decided_by="pm-001",
        decision="Run the address-validation pilot.",
        rationale="Cheaper and testable sooner.",
        agreed_with_recommendation=True,
        decided_at=CLOCK,
    )
    rendered = report.to_markdown(brief, decision=decision)
    assert "Run the address-validation pilot." in rendered
    assert "agreed with the recommendation" in rendered


def test_a_disagreement_is_rendered_prominently(brief: DecisionBrief) -> None:
    decision = record_pm_decision(
        brief,
        decided_by="pm-001",
        decision="Build the assistant anyway.",
        agreed_with_recommendation=False,
        override_reason="A commitment was already made.",
        decided_at=CLOCK,
    )
    rendered = report.to_markdown(brief, decision=decision)
    assert "**disagreed with the recommendation**" in rendered
    assert "A commitment was already made." in rendered


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #


def test_the_json_export_is_the_whole_brief_not_a_summary(brief: DecisionBrief) -> None:
    """Phase 10 reads this back to score runs, so nothing may be dropped."""
    payload = json.loads(report.to_json(brief))
    assert payload["brief"] == json.loads(brief.model_dump_json())
    assert payload["pm_decision"] is None


def test_the_json_export_round_trips_into_the_model(brief: DecisionBrief) -> None:
    payload = json.loads(report.to_json(brief))
    assert DecisionBrief.model_validate(payload["brief"]).id == brief.id


def test_a_decision_is_carried_in_the_json_export(brief: DecisionBrief) -> None:
    decision = record_pm_decision(brief, decided_by="pm-001", decision="Defer.", decided_at=CLOCK)
    payload = json.loads(report.to_json(brief, decision=decision))
    assert payload["pm_decision"]["decision"] == "Defer."


# --------------------------------------------------------------------------- #
# Degraded briefs still render
# --------------------------------------------------------------------------- #


def test_a_brief_with_no_recommendation_still_renders(tmp_path: Path) -> None:
    """A run whose recommendation stage failed must still produce a readable page."""
    directory, _ = case_with_cache(tmp_path)
    empty = tmp_path / "empty.json"
    empty.write_text('{"responses":{}}', encoding="utf-8")
    loaded = load_case(directory)
    lens = DecisionLens(CachedDemoProvider(empty), loaded.sources, as_of=loaded.as_of, clock=CLOCK)
    rendered = report.to_markdown(lens.run(loaded.request))

    assert "_No recommendation was produced._" in rendered
    assert "should not be acted on as it stands" in rendered
    assert SYNTHETIC_DATA_NOTICE in rendered


def test_a_clean_brief_says_so_rather_than_showing_an_empty_section(
    request_: object, evidence: object
) -> None:
    """A brief with nothing wrong still needs the checks section to say that."""
    from decision_lens.models import DecisionRequest, EvidenceRecord

    assert isinstance(request_, DecisionRequest)
    assert isinstance(evidence, EvidenceRecord)
    spotless = DecisionBrief(
        id="DB-CLEAN",
        request=request_.model_copy(update={"time_period": "Q2 2026"}),
        generated_at=CLOCK,
        evidence=(evidence,),
        validation_issues=(),
        run_trace=None,
    )
    rendered = report.to_markdown(spotless)

    assert "Every deterministic check passed." in rendered
    assert "- Period: Q2 2026" in rendered
    assert "_No trace recorded._" in rendered


def test_a_claims_rationale_is_shown_next_to_it(markdown: str) -> None:
    """Why a claim was labelled an opinion is the part a PM argues with."""
    assert "Seniority does not convert it." in markdown


def test_issues_render_as_one_line_each(tmp_path: Path) -> None:
    """A provider error is usually multi-line; embedding one breaks the list."""
    directory, _ = case_with_cache(tmp_path)
    empty = tmp_path / "empty.json"
    empty.write_text('{"responses":{}}', encoding="utf-8")
    loaded = load_case(directory)
    lens = DecisionLens(CachedDemoProvider(empty), loaded.sources, as_of=loaded.as_of, clock=CLOCK)
    brief = lens.run(loaded.request)

    for issue in brief.validation_issues:
        assert "\n" not in issue.message


class TestProviderWarningsReachThePage:
    """A warning nobody prints is the same as no warning.

    The cached provider already said "the prompt has changed since this response
    was recorded" for two stages. `RunStage` had no field to hold it and the
    report had no line to print it, so the sentence was constructed and dropped
    on every run for an entire evening. These pin the whole path.
    """

    @staticmethod
    def _with(brief: DecisionBrief, warnings: tuple[str, ...]) -> DecisionBrief:
        stage = RunStage(name="classification", provider="cached-demo", warnings=warnings)
        trace = RunTrace(run_id="r1", request_id="q1", stages=(stage,))
        return brief.model_copy(update={"run_trace": trace})

    def test_a_stale_prompt_warning_is_printed(self, brief: DecisionBrief) -> None:
        note = "The prompt has changed since this was recorded."
        text = report.to_markdown(self._with(brief, (note,)))
        assert "Notes on how these answers were obtained" in text
        assert note in text
        assert "`classification`" in text

    def test_several_warnings_are_all_printed(self, brief: DecisionBrief) -> None:
        text = report.to_markdown(self._with(brief, ("first thing", "second thing")))
        assert "first thing" in text
        assert "second thing" in text

    def test_no_warnings_means_no_empty_heading(self, brief: DecisionBrief) -> None:
        text = report.to_markdown(self._with(brief, ()))
        assert "Notes on how these answers were obtained" not in text

    def test_the_warning_survives_the_json_artifact_too(self, brief: DecisionBrief) -> None:
        payload = json.loads(report.to_json(self._with(brief, ("prompt changed",))))
        assert payload["brief"]["run_trace"]["stages"][0]["warnings"] == ["prompt changed"]


class TestTheTraceRecordsWhichTextRan:
    """A version is a label a human attaches; a fingerprint is derived from the text.

    D14 established that the label cannot be trusted alone — two prompts were
    edited with their versions left unchanged and the cache went on replaying
    answers to wording that no longer existed. A trace carrying only the version
    reproduces that weakness: it says what the prompt was called, not what it
    said.
    """

    def test_the_fingerprint_reaches_the_run_trace(self, brief: DecisionBrief) -> None:
        trace = brief.run_trace
        assert trace is not None
        model_stages = [s for s in trace.stages if s.model]
        assert model_stages
        assert all(s.prompt_fingerprint for s in model_stages), (
            "every model stage must record the text that produced it"
        )

    def test_the_fingerprint_is_printed_in_the_brief(self, brief: DecisionBrief) -> None:
        trace = brief.run_trace
        assert trace is not None
        stage = next(s for s in trace.stages if s.prompt_fingerprint)
        assert stage.prompt_fingerprint[:12] in report.to_markdown(brief)

    def test_it_survives_the_json_artifact(self, brief: DecisionBrief) -> None:
        payload = json.loads(report.to_json(brief))
        stages = payload["brief"]["run_trace"]["stages"]
        assert any(s.get("prompt_fingerprint") for s in stages)

    def test_a_stage_that_never_called_a_model_has_none(self, brief: DecisionBrief) -> None:
        """Retrieval is a stage too, and it has no prompt."""
        trace = brief.run_trace
        assert trace is not None
        retrieval = [s for s in trace.stages if not s.model]
        assert retrieval, "the fixture should include a retrieval stage"
        assert all(not s.prompt_fingerprint for s in retrieval)


class TestLongListsAreCappedHonestly:
    """A recommendation section ran to 1,631 words on the bundled case, of which
    1,441 were four unbounded lists. The caps are here rather than in a validation
    rule because a display limit costs no retry, and they announce what they hide
    because a silently truncated list reads as a complete one."""

    def test_a_short_list_is_shown_whole(self) -> None:
        from decision_lens.report import TOP_N, _top_bullets

        items = tuple(f"item {n}" for n in range(TOP_N))
        rendered = _top_bullets(items)
        assert len(rendered) == TOP_N
        assert not any("more" in line for line in rendered)

    def test_a_long_list_is_capped_and_says_how_many_are_hidden(self) -> None:
        from decision_lens.report import TOP_N, _top_bullets

        items = tuple(f"item {n}" for n in range(TOP_N + 3))
        rendered = _top_bullets(items)
        assert len(rendered) == TOP_N + 1
        assert "and 3 more" in rendered[-1]
        assert "JSON artifact" in rendered[-1], "the reader is told where the rest lives"

    def test_an_empty_list_falls_back_to_its_message(self) -> None:
        from decision_lens.report import _top_bullets

        assert _top_bullets((), "_(nothing stated)_") == ["_(nothing stated)_"]

    def test_the_recommendation_section_stays_short(self, brief: DecisionBrief) -> None:
        """The whole point: a reader deciding, not studying."""
        text = report.to_markdown(brief)
        if "\n## Recommendation" not in text:
            pytest.skip("this brief produced no recommendation")
        section = text.split("\n## Recommendation")[1].split("\n## ")[0]
        assert len(section.split()) < 1_000, "the section this cap exists to bound"

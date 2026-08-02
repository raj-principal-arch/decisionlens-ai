"""The recommendation challenger.

Three invariants carry the weight here, and each is a check in code rather than a
sentence in a prompt: all eight questions get answered, the two arithmetic answers
are overridden by counting, and confidence can only go down.
"""

from __future__ import annotations

from typing import Any

import pytest

from decision_lens.llm import ModelRequest, ModelResponse, ModelUsage
from decision_lens.models import (
    Alternative,
    Citation,
    Claim,
    ClaimType,
    DecisionRequest,
    EvidenceRecord,
    EvidenceType,
    OptionKind,
    Recommendation,
    SourceSystem,
    SupportLevel,
    UserContext,
)
from decision_lens.skills import (
    ChallengeFinding,
    ChallengeOutput,
    ChallengeQuestion,
    ChallengerSkill,
    ChallengeVerdict,
    ClaimReclassification,
    SkillContext,
    SkillViolation,
)

QUOTE = "The VP believes notifications are the answer."


class FakeProvider:
    """Returns scripted JSON. Reaches nothing."""

    provider_id = "fake"
    model_id = "fake-1"

    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)

    def complete(self, request: ModelRequest) -> ModelResponse:
        text = self._texts.pop(0) if self._texts else "{}"
        return ModelResponse(
            text=text,
            provider=self.provider_id,
            model=self.model_id,
            prompt_version=request.prompt_version,
            skill=request.skill,
            latency_ms=5,
            usage=ModelUsage(input_tokens=10, output_tokens=5),
            is_cached=False,
        )


def _context() -> SkillContext:
    return SkillContext(
        request=DecisionRequest(
            id="DR-001",
            question="Which intervention should the team prioritize?",
            user=UserContext(user_id="pm-001"),
        ),
        evidence=(
            EvidenceRecord(
                id="EV-1",
                source_system=SourceSystem.LOCAL_FILE,
                source_id="stakeholder_notes.md",
                content=QUOTE,
                evidence_type=EvidenceType.STAKEHOLDER_INPUT,
            ),
        ),
    )


def _findings(**verdicts: ChallengeVerdict) -> tuple[ChallengeFinding, ...]:
    return tuple(
        ChallengeFinding(
            question=q,
            verdict=verdicts.get(q.value, ChallengeVerdict.PASSES),
            explanation=f"Reviewed {q.value}.",
        )
        for q in ChallengeQuestion
    )


def _output(**kwargs: Any) -> str:
    kwargs.setdefault("findings", _findings())
    return ChallengeOutput(**kwargs).model_dump_json()


def _alternatives(*kinds: OptionKind) -> tuple[Alternative, ...]:
    return tuple(
        Alternative(id=f"ALT-{i}", name=k.value, kind=k) for i, k in enumerate(kinds, start=1)
    )


def _recommendation(support: SupportLevel = SupportLevel.MODERATE) -> Recommendation:
    return Recommendation(
        statement="Improve notifications.",
        option_kind=OptionKind.PROCESS_CHANGE,
        support_level=support,
    )


def _skill(*texts: str, **kwargs: Any) -> ChallengerSkill:
    kwargs.setdefault("recommendation", _recommendation())
    kwargs.setdefault("alternatives", _alternatives(OptionKind.PROCESS_CHANGE, OptionKind.DEFER))
    return ChallengerSkill(FakeProvider(*texts), **kwargs)


# --------------------------------------------------------------------------- #
# All eight, every time
# --------------------------------------------------------------------------- #


def test_a_complete_review_passes() -> None:
    run = _skill(_output()).run(_context())
    assert len(run.output.findings) == len(ChallengeQuestion)
    assert run.output.failing == ()


def test_skipping_a_question_is_rejected() -> None:
    """Silence on the awkward question reads as approval of something unexamined."""
    partial = tuple(f for f in _findings() if f.question is not ChallengeQuestion.OVERCONFIDENT)
    text = ChallengeOutput(findings=partial).model_dump_json()
    with pytest.raises(SkillViolation, match="overconfident"):
        _skill(text, allow_retry=False).run(_context())


def test_answering_a_question_twice_is_rejected() -> None:
    doubled = _findings() + (
        ChallengeFinding(
            question=ChallengeQuestion.OVERCONFIDENT,
            verdict=ChallengeVerdict.FAILS,
            explanation="Changed my mind.",
        ),
    )
    text = ChallengeOutput(findings=doubled, what_would_change_it=("More data.",)).model_dump_json()
    with pytest.raises(SkillViolation, match="more than once"):
        _skill(text, allow_retry=False).run(_context())


def test_the_retry_names_the_question_that_was_skipped() -> None:
    partial = tuple(f for f in _findings() if f.question is not ChallengeQuestion.WHAT_TO_TEST)
    bad = ChallengeOutput(findings=partial).model_dump_json()
    skill = _skill(bad, _output())
    run = skill.run(_context())
    assert run.retried
    assert len(run.output.findings) == len(ChallengeQuestion)


# --------------------------------------------------------------------------- #
# Grounding
# --------------------------------------------------------------------------- #


def test_a_finding_citing_absent_text_is_rejected() -> None:
    findings = tuple(
        f.model_copy(update={"citations": (Citation(evidence_id="EV-1", quote="never written"),)})
        if f.question is ChallengeQuestion.CLAIMS_SUPPORTED
        else f
        for f in _findings()
    )
    text = ChallengeOutput(findings=findings).model_dump_json()
    with pytest.raises(SkillViolation, match="not in the evidence"):
        _skill(text, allow_retry=False).run(_context())


def test_a_finding_may_cite_real_text() -> None:
    findings = tuple(
        f.model_copy(update={"citations": (Citation(evidence_id="EV-1", quote=QUOTE),)})
        if f.question is ChallengeQuestion.PREFERENCE_AS_EVIDENCE
        else f
        for f in _findings()
    )
    text = ChallengeOutput(findings=findings).model_dump_json()
    assert _skill(text).run(_context()).output.findings


def test_reclassifying_an_unknown_claim_is_rejected() -> None:
    text = _output(
        reclassify=(
            ClaimReclassification(
                claim_id="CL-GHOST", new_type=ClaimType.STAKEHOLDER_OPINION, reason="It is one."
            ),
        )
    )
    with pytest.raises(SkillViolation, match="CL-GHOST"):
        _skill(text, allow_retry=False, claims=()).run(_context())


def test_reclassifying_a_known_claim_is_the_point() -> None:
    """An executive preference carried as a fact is what this catches."""
    claim = Claim(
        id="CL-1",
        statement="Notifications are the answer.",
        claim_type=ClaimType.FACT,
        citations=(Citation(evidence_id="EV-1", quote=QUOTE),),
    )
    text = _output(
        reclassify=(
            ClaimReclassification(
                claim_id="CL-1",
                new_type=ClaimType.STAKEHOLDER_OPINION,
                reason="This is the VP's preference, not a measurement.",
            ),
        )
    )
    run = _skill(text, claims=(claim,)).run(_context())
    assert run.output.reclassify[0].new_type is ClaimType.STAKEHOLDER_OPINION


def test_failing_without_saying_what_would_fix_it_is_rejected() -> None:
    text = ChallengeOutput(
        findings=_findings(overconfident=ChallengeVerdict.FAILS)
    ).model_dump_json()
    with pytest.raises(SkillViolation, match="what_would_change_it"):
        _skill(text, allow_retry=False).run(_context())


def test_failing_with_a_remedy_is_accepted() -> None:
    text = ChallengeOutput(
        findings=_findings(overconfident=ChallengeVerdict.FAILS),
        what_would_change_it=("A measured baseline for the affected segment.",),
    ).model_dump_json()
    run = _skill(text).run(_context())
    assert len(run.output.failing) == 1


# --------------------------------------------------------------------------- #
# The two answers that are arithmetic
# --------------------------------------------------------------------------- #


def test_a_missing_non_ai_option_forces_a_failure_whatever_the_model_said() -> None:
    # Every kind here is an AI kind. Note that deferring counts as a non-AI
    # option, so an option set containing `defer` would not trip this.
    text = ChallengeOutput(
        findings=_findings(non_ai_considered=ChallengeVerdict.PASSES),
        what_would_change_it=("Generate a non-AI option.",),
    ).model_dump_json()
    run = _skill(
        text, alternatives=_alternatives(OptionKind.AI_ASSISTED, OptionKind.AI_AUTOMATED)
    ).run(_context())

    assert run.output.verdict_for(ChallengeQuestion.NON_AI_CONSIDERED) is ChallengeVerdict.FAILS
    assert any("overridden to fails" in w for w in run.warnings)


def test_deferring_counts_as_a_non_ai_option() -> None:
    """Doing nothing does not involve AI, so it satisfies the non-AI requirement."""
    text = ChallengeOutput(
        findings=_findings(no_build_considered=ChallengeVerdict.PASSES),
        what_would_change_it=("n/a",),
    ).model_dump_json()
    run = _skill(text, alternatives=_alternatives(OptionKind.AI_ASSISTED, OptionKind.DEFER)).run(
        _context()
    )

    assert run.output.verdict_for(ChallengeQuestion.NON_AI_CONSIDERED) is ChallengeVerdict.PASSES
    assert run.output.verdict_for(ChallengeQuestion.NO_BUILD_CONSIDERED) is ChallengeVerdict.PASSES


def test_a_missing_no_build_option_forces_a_failure() -> None:
    text = ChallengeOutput(
        findings=_findings(no_build_considered=ChallengeVerdict.PASSES),
        what_would_change_it=("Generate a defer option.",),
    ).model_dump_json()
    run = _skill(
        text, alternatives=_alternatives(OptionKind.AI_ASSISTED, OptionKind.PROCESS_CHANGE)
    ).run(_context())

    assert run.output.verdict_for(ChallengeQuestion.NO_BUILD_CONSIDERED) is ChallengeVerdict.FAILS


def test_the_override_keeps_what_the_reviewer_actually_wrote() -> None:
    text = ChallengeOutput(
        findings=_findings(non_ai_considered=ChallengeVerdict.PASSES),
        what_would_change_it=("Generate one.",),
    ).model_dump_json()
    run = _skill(text, alternatives=_alternatives(OptionKind.AI_AUTOMATED)).run(_context())

    finding = run.output.by_question()[ChallengeQuestion.NON_AI_CONSIDERED]
    assert "Counted from the alternatives, not judged" in finding.explanation
    assert "The reviewer wrote:" in finding.explanation


def test_no_override_when_the_option_actually_exists() -> None:
    run = _skill(_output()).run(_context())
    assert run.output.verdict_for(ChallengeQuestion.NON_AI_CONSIDERED) is ChallengeVerdict.PASSES
    assert run.warnings == ()


def test_an_already_failing_verdict_is_not_re_warned() -> None:
    # An all-AI option set fails both existence checks at once: every no-build
    # kind is also a non-AI kind, so the two can never be overridden separately
    # in this direction.
    text = ChallengeOutput(
        findings=_findings(
            non_ai_considered=ChallengeVerdict.FAILS,
            no_build_considered=ChallengeVerdict.FAILS,
        ),
        what_would_change_it=("Generate one.",),
    ).model_dump_json()
    run = _skill(text, alternatives=_alternatives(OptionKind.AI_ASSISTED)).run(_context())
    assert not any("overridden" in w for w in run.warnings)


# --------------------------------------------------------------------------- #
# Confidence only goes down
# --------------------------------------------------------------------------- #


def test_the_challenger_may_lower_support() -> None:
    text = _output(recommended_support=SupportLevel.LOW)
    run = _skill(text, recommendation=_recommendation(SupportLevel.STRONG)).run(_context())
    assert run.output.recommended_support is SupportLevel.LOW


def test_the_challenger_may_not_raise_support() -> None:
    """A reviewer that can argue itself into more certainty has stopped reviewing."""
    text = _output(recommended_support=SupportLevel.STRONG)
    run = _skill(text, recommendation=_recommendation(SupportLevel.LOW)).run(_context())

    assert run.output.recommended_support is None
    assert any("never raise it" in w for w in run.warnings)


def test_restating_the_current_level_is_harmless() -> None:
    text = _output(recommended_support=SupportLevel.MODERATE)
    run = _skill(text, recommendation=_recommendation(SupportLevel.MODERATE)).run(_context())
    assert run.output.recommended_support is SupportLevel.MODERATE
    assert run.warnings == ()


def test_support_advice_is_kept_when_there_is_no_draft_to_compare_against() -> None:
    """A recommendation stage that failed still gets challenged on everything else."""
    text = _output(recommended_support=SupportLevel.LOW)
    run = _skill(text, recommendation=None).run(_context())
    assert run.output.recommended_support is SupportLevel.LOW


# --------------------------------------------------------------------------- #
# Reading the result
# --------------------------------------------------------------------------- #


def test_findings_are_addressable_by_question() -> None:
    text = ChallengeOutput(
        findings=_findings(
            overconfident=ChallengeVerdict.CONCERN,
            claims_supported=ChallengeVerdict.FAILS,
        ),
        what_would_change_it=("Measure it.",),
    ).model_dump_json()
    output = _skill(text).run(_context()).output

    assert [f.question for f in output.failing] == [ChallengeQuestion.CLAIMS_SUPPORTED]
    assert [f.question for f in output.concerns] == [ChallengeQuestion.OVERCONFIDENT]
    assert output.verdict_for(ChallengeQuestion.WHAT_TO_TEST) is ChallengeVerdict.PASSES


def test_an_unanswered_question_reads_as_none() -> None:
    assert ChallengeOutput().verdict_for(ChallengeQuestion.OVERCONFIDENT) is None


def test_refine_tolerates_a_question_that_is_absent() -> None:
    """`refine` is public and overridable, so it cannot assume `violations` ran first."""
    skill = _skill(alternatives=_alternatives(OptionKind.AI_ASSISTED))
    partial = ChallengeOutput(
        findings=tuple(
            f for f in _findings() if f.question is not ChallengeQuestion.NON_AI_CONSIDERED
        )
    )
    refined, warnings = skill.refine(partial, _context())

    assert refined.verdict_for(ChallengeQuestion.NON_AI_CONSIDERED) is None
    assert not any("non_ai_considered" in w for w in warnings)


# --------------------------------------------------------------------------- #
# What the challenger is shown
# --------------------------------------------------------------------------- #


def test_the_draft_is_rendered_with_the_parts_worth_attacking() -> None:
    """Support level and what it rests on, because those are what it argues with."""
    recommendation = Recommendation(
        statement="Improve notifications.",
        option_kind=OptionKind.PROCESS_CHANGE,
        selected_alternative_id="ALT-1",
        support_level=SupportLevel.MODERATE,
        support_basis="One operational record.",
        conditions=("Only for apartment deliveries.",),
        what_would_change_it=("A measured baseline.",),
    )
    rendered = _skill(recommendation=recommendation).render_values(_context())["recommendation"]

    assert "Support level: moderate" in rendered
    assert "Support rests on: One operational record." in rendered
    assert "Conditions: Only for apartment deliveries." in rendered
    assert "What would change it: A measured baseline." in rendered


def test_a_missing_draft_is_rendered_plainly_rather_than_blank() -> None:
    rendered = _skill(recommendation=None).render_values(_context())["recommendation"]
    assert rendered == "(no recommendation was produced)"

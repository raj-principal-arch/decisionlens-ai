"""The controlled workflow, end to end.

Covers the thirteen scenarios the build specification names, plus the wiring that
holds them together. The model is scripted throughout: what is under test is the
orchestration and the deterministic checks, not whether a model happens to answer
well on a given day.

The scenario tests are written to fail loudly if a guarantee is quietly removed.
A brief that silently drops a failed stage, resolves a contradiction, or keeps a
strong support level over a broken citation should break several of these at once.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from decision_lens.connectors.base import EvidenceSourceError
from decision_lens.llm import (
    CachedDemoProvider,
    CachedResponse,
    DemoCache,
    ModelRequest,
    ModelResponse,
    ModelTimeout,
    ModelUnavailable,
    ModelUsage,
)
from decision_lens.models import (
    Alternative,
    AssessmentState,
    Citation,
    Claim,
    ClaimType,
    Contradiction,
    ContradictionKind,
    DecisionRequest,
    Dimension,
    DimensionAssessment,
    EvidenceRecord,
    EvidenceRequest,
    EvidenceType,
    ExperimentPlan,
    GapImpact,
    Metric,
    MetricRole,
    MissingEvidence,
    OptionKind,
    Recommendation,
    SourceSystem,
    SupportLevel,
    UserContext,
)
from decision_lens.orchestrator import DecisionLens, DecisionLensError, record_pm_decision
from decision_lens.skills import (
    AlternativesOutput,
    ChallengeFinding,
    ChallengeOutput,
    ChallengeQuestion,
    ChallengeVerdict,
    ClaimReclassification,
    ClassificationOutput,
    ContradictionsOutput,
    MissingEvidenceOutput,
    RecommendationOutput,
    RelevanceOutput,
)
from decision_lens.validation import ValidationCode

CLOCK = datetime(2026, 8, 2, 9, 0, 0)
AS_OF = date(2026, 8, 2)

FACT = "Address errors account for 40% of delivery exceptions."
EXEC = "The VP wants an AI assistant for drivers."
GOV = "Delivery photos must not be retained beyond 30 days."


# --------------------------------------------------------------------------- #
# Doubles
# --------------------------------------------------------------------------- #


class FakeSource:
    """An evidence source that returns what it was handed."""

    def __init__(self, *records: EvidenceRecord, error: Exception | None = None) -> None:
        self._records = records
        self._error = error

    @property
    def source_system(self) -> SourceSystem:
        return SourceSystem.LOCAL_FILE

    def retrieve(self, request: EvidenceRequest) -> tuple[EvidenceRecord, ...]:
        if self._error is not None:
            raise self._error
        return self._records


class ScriptedProvider:
    """Answers per skill name. Reaches nothing.

    A script entry may be an exception, which is how the partial-failure and
    timeout scenarios are driven without any real provider.
    """

    provider_id = "scripted"
    model_id = "scripted-1"

    def __init__(self, script: dict[str, Any]) -> None:
        self.script = script
        self.seen: list[str] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.seen.append(request.skill)
        entry = self.script.get(request.skill)
        if isinstance(entry, Exception):
            raise entry
        if entry is None:
            raise ModelUnavailable(f"nothing scripted for {request.skill!r}")
        return ModelResponse(
            text=entry,
            provider=self.provider_id,
            model=self.model_id,
            prompt_version=request.prompt_version,
            skill=request.skill,
            latency_ms=7,
            usage=ModelUsage(input_tokens=100, output_tokens=40),
            is_cached=False,
        )


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _record(record_id: str, content: str, evidence_type: EvidenceType) -> EvidenceRecord:
    return EvidenceRecord(
        id=record_id,
        source_system=SourceSystem.LOCAL_FILE,
        source_id=f"{record_id}.md",
        source_reference=f"data/{record_id}.md",
        content=content,
        evidence_type=evidence_type,
        updated_at=date(2026, 6, 1),
    )


def _evidence() -> tuple[EvidenceRecord, ...]:
    return (
        _record("EV-1", FACT, EvidenceType.OPERATIONAL_RECORD),
        _record("EV-2", EXEC, EvidenceType.STAKEHOLDER_INPUT),
        _record("EV-3", GOV, EvidenceType.GOVERNANCE_POLICY),
    )


def _request() -> DecisionRequest:
    return DecisionRequest(
        id="DR-001",
        question="Which intervention should the team prioritize to reduce delivery exceptions?",
        desired_outcome="Improve first-attempt delivery success.",
        user=UserContext(user_id="pm-001", product_area="delivery"),
    )


def _cite(record_id: str = "EV-1", quote: str = FACT) -> Citation:
    return Citation(evidence_id=record_id, quote=quote)


def _claims() -> tuple[Claim, ...]:
    return (
        Claim(
            id="CL-1",
            statement="Address quality is the largest driver of delivery exceptions.",
            claim_type=ClaimType.FACT,
            citations=(_cite(),),
        ),
        Claim(
            id="CL-2",
            statement="An AI driver assistant is the right intervention.",
            claim_type=ClaimType.FACT,
            citations=(_cite("EV-2", EXEC),),
        ),
        Claim(
            id="CL-3",
            statement="Delivery photos cannot be retained beyond 30 days.",
            claim_type=ClaimType.GOVERNANCE_CONSTRAINT,
            citations=(_cite("EV-3", GOV),),
        ),
    )


def _alternatives(*kinds: OptionKind) -> tuple[Alternative, ...]:
    chosen = kinds or (OptionKind.DATA_QUALITY, OptionKind.AI_ASSISTED, OptionKind.DEFER)
    return tuple(
        Alternative(
            id=f"ALT-{i}",
            name=f"Option {i}",
            kind=kind,
            supporting=(_cite(),),
            assessments=(
                DimensionAssessment(
                    dimension=Dimension.RISK,
                    state=AssessmentState.ASSESSED,
                    summary="Bounded.",
                    citations=(_cite(),),
                ),
            ),
        )
        for i, kind in enumerate(chosen, start=1)
    )


def _recommendation(**kwargs: Any) -> Recommendation:
    base: dict[str, Any] = {
        "statement": "Validate addresses before considering an AI assistant.",
        "option_kind": OptionKind.DATA_QUALITY,
        "selected_alternative_id": "ALT-1",
        "claims": (_claims()[0],),
        "support_level": SupportLevel.MODERATE,
        "support_basis": "One operational record.",
        "what_would_change_it": ("A measured baseline by segment.",),
        "experiment": ExperimentPlan(
            id="EX-1",
            hypothesis="Address validation reduces exceptions.",
            metrics=(Metric(name="exception rate", role=MetricRole.SUCCESS),),
        ),
    }
    return Recommendation(**{**base, **kwargs})


def _findings(**verdicts: ChallengeVerdict) -> tuple[ChallengeFinding, ...]:
    return tuple(
        ChallengeFinding(
            question=q,
            verdict=verdicts.get(q.value, ChallengeVerdict.PASSES),
            explanation=f"Reviewed {q.value}.",
        )
        for q in ChallengeQuestion
    )


def _script(**overrides: Any) -> dict[str, Any]:
    """A coherent run. Any stage can be swapped or replaced with an exception."""
    base: dict[str, Any] = {
        "relevance": RelevanceOutput(relevant_ids=("EV-1", "EV-2", "EV-3")).model_dump_json(),
        "classification": ClassificationOutput(claims=_claims()).model_dump_json(),
        "contradictions": ContradictionsOutput(
            contradictions=(
                Contradiction(
                    id="CN-1",
                    topic="the leading cause of exceptions",
                    kind=ContradictionKind.CLAIM_CONFLICT,
                    side_a=_cite(),
                    side_b=_cite("EV-2", EXEC),
                    summary="The record and the VP disagree.",
                    how_to_resolve="Recount exceptions by cause for the last quarter.",
                ),
            )
        ).model_dump_json(),
        "missing_evidence": MissingEvidenceOutput(
            gaps=(
                MissingEvidence(
                    id="MG-1",
                    question="What does address validation cost to run?",
                    impact=GapImpact.WOULD_CHANGE_SUPPORT_LEVEL,
                    why_it_matters="The business case depends on it.",
                ),
            )
        ).model_dump_json(),
        "alternatives": AlternativesOutput(alternatives=_alternatives()).model_dump_json(),
        "recommendation": RecommendationOutput(recommendation=_recommendation()).model_dump_json(),
        "challenger": ChallengeOutput(findings=_findings()).model_dump_json(),
    }
    return {**base, **overrides}


def _lens(script: dict[str, Any] | None = None, *sources: Any, **kwargs: Any) -> DecisionLens:
    return DecisionLens(
        ScriptedProvider(script if script is not None else _script()),
        sources or (FakeSource(*_evidence()),),
        as_of=AS_OF,
        clock=CLOCK,
        **kwargs,
    )


def _run(script: dict[str, Any] | None = None, *sources: Any, **kwargs: Any) -> Any:
    return _lens(script, *sources, **kwargs).run(_request())


def _codes(brief: Any) -> set[str]:
    return {i.code for i in brief.validation_issues}


def _errors(brief: Any) -> set[str]:
    return {i.code for i in brief.validation_issues if i.blocks_presentation}


# --------------------------------------------------------------------------- #
# The happy path, and the sequence itself
# --------------------------------------------------------------------------- #


def test_a_complete_run_produces_a_clean_brief() -> None:
    brief = _run()

    assert brief.id == "DL-DR-001"
    assert brief.recommendation is not None
    assert len(brief.claims) == 3
    assert len(brief.alternatives) == 3
    assert brief.contradictions
    assert brief.missing_evidence
    assert _errors(brief) == set()


def test_the_stages_run_in_the_specified_order() -> None:
    """A fixed sequence, not a planner choosing its next move."""
    lens = _lens()
    lens.run(_request())
    provider = lens.provider
    assert isinstance(provider, ScriptedProvider)
    assert provider.seen == [
        "relevance",
        "classification",
        "contradictions",
        "missing_evidence",
        "alternatives",
        "recommendation",
        "challenger",
    ]


def test_the_run_trace_pins_provider_model_and_prompt_version() -> None:
    trace = _run().run_trace
    assert trace is not None
    assert trace.run_id == "decisionlens-DR-001"
    assert trace.started_at == CLOCK
    model_stages = [s for s in trace.stages if s.model]
    assert {s.provider for s in model_stages} == {"scripted"}
    assert all(s.prompt_version == "v1" for s in model_stages)
    assert trace.total_latency_ms > 0


def test_retrieval_is_recorded_as_its_own_stage() -> None:
    trace = _run().run_trace
    assert trace is not None
    assert any(s.name == "retrieve:local_file" for s in trace.stages)


def test_a_run_with_no_source_configured_refuses_to_answer() -> None:
    """DecisionLens does not answer from the model's own knowledge."""
    lens = DecisionLens(ScriptedProvider(_script()), (), clock=CLOCK)
    with pytest.raises(DecisionLensError, match="No evidence source"):
        lens.run(_request())


# --------------------------------------------------------------------------- #
# 1. Insufficient evidence
# --------------------------------------------------------------------------- #


def test_no_evidence_produces_a_brief_that_says_so_rather_than_an_answer() -> None:
    lens = _lens(_script(), FakeSource())
    brief = lens.run(_request())

    assert brief.evidence == ()
    assert brief.recommendation is None
    assert ValidationCode.SECTION_MISSING in _errors(brief)
    provider = lens.provider
    assert isinstance(provider, ScriptedProvider)
    assert provider.seen == [], "no skill should run against an empty evidence set"


def test_the_empty_run_explains_why_nothing_was_attempted() -> None:
    brief = _run(_script(), FakeSource())
    notes = [i.message for i in brief.validation_issues if i.code == ValidationCode.ANALYSIS_NOTE]
    assert any("No evidence was retrieved" in n for n in notes)


# --------------------------------------------------------------------------- #
# 2. Conflicting evidence
# --------------------------------------------------------------------------- #


def test_a_contradiction_reaches_the_brief_unresolved() -> None:
    """Both sides, with citations, and what would settle it. No winner picked."""
    brief = _run()
    (found,) = brief.contradictions

    assert found.side_a != found.side_b
    assert found.how_to_resolve
    assert {found.side_a.evidence_id, found.side_b.evidence_id} == {"EV-1", "EV-2"}


def test_a_recommendation_that_picks_a_side_says_that_it_did() -> None:
    """The default run genuinely rests on contested evidence, and now shows it.

    Its recommendation cites EV-1, which is one side of the address-errors versus
    executive-preference conflict. Every citation resolves and the contradiction
    is reported — two sections away from the answer, which is precisely why the
    connection has to be drawn for the reader rather than left to be noticed.
    """
    brief = _run()
    (issue,) = [i for i in brief.validation_issues if i.code == ValidationCode.CONTESTED_SUPPORT]

    assert "EV-1" in issue.message
    assert "CN-1" in issue.message
    assert not issue.blocks_presentation, "picking a side is allowed; doing it silently is not"


# --------------------------------------------------------------------------- #
# 3. Executive pressure
# --------------------------------------------------------------------------- #


def test_the_challenger_relabels_an_executive_preference_carried_as_fact() -> None:
    """The single most useful correction this stage makes."""
    challenge = ChallengeOutput(
        findings=_findings(preference_as_evidence=ChallengeVerdict.CONCERN),
        reclassify=(
            ClaimReclassification(
                claim_id="CL-2",
                new_type=ClaimType.STAKEHOLDER_OPINION,
                reason="This is the VP's preference, not a measurement.",
            ),
        ),
    ).model_dump_json()
    brief = _run(_script(challenger=challenge))

    relabelled = next(c for c in brief.claims if c.id == "CL-2")
    assert relabelled.claim_type is ClaimType.STAKEHOLDER_OPINION
    assert "VP's preference" in relabelled.rationale
    assert ValidationCode.CHALLENGE_CONCERN in _codes(brief)


def test_reclassification_happens_before_validation_runs() -> None:
    """Otherwise the brief reports a defect the challenger already fixed."""
    claims = (Claim(id="CL-9", statement="Leadership is confident.", claim_type=ClaimType.FACT),)
    challenge = ChallengeOutput(
        findings=_findings(),
        reclassify=(
            ClaimReclassification(
                claim_id="CL-9",
                new_type=ClaimType.STAKEHOLDER_OPINION,
                reason="Confidence is not a measurement.",
            ),
        ),
    ).model_dump_json()
    brief = _run(
        _script(
            classification=ClassificationOutput(claims=claims).model_dump_json(),
            challenger=challenge,
        )
    )
    assert ValidationCode.UNGROUNDED_FACT not in _codes(brief)


# --------------------------------------------------------------------------- #
# 4 & 5. The two options nobody asks for
# --------------------------------------------------------------------------- #


def test_an_all_ai_option_set_never_reaches_a_brief() -> None:
    """Two lines of defence, and this asserts both fired.

    The alternatives skill refuses the set outright, so the stage fails rather
    than returning something unusable. Validation then reports the resulting
    absence. Asserting only the second half would pass even if the first were
    removed, which is how a guard quietly stops guarding.
    """
    script = _script(
        alternatives=AlternativesOutput(
            alternatives=_alternatives(OptionKind.AI_ASSISTED, OptionKind.AI_AUTOMATED)
        ).model_dump_json()
    )
    brief = _run(script)

    assert brief.alternatives == (), "the skill refused the set"
    assert ValidationCode.STAGE_FAILED in _codes(brief)
    assert ValidationCode.NON_AI_ALTERNATIVE_MISSING in _errors(brief)
    assert ValidationCode.NO_BUILD_ALTERNATIVE_MISSING in _errors(brief)


def test_an_option_set_with_no_no_build_choice_never_reaches_a_brief() -> None:
    script = _script(
        alternatives=AlternativesOutput(
            alternatives=_alternatives(OptionKind.DATA_QUALITY, OptionKind.AI_ASSISTED)
        ).model_dump_json()
    )
    brief = _run(script)

    assert brief.alternatives == ()
    assert ValidationCode.STAGE_FAILED in _codes(brief)
    assert ValidationCode.NO_BUILD_ALTERNATIVE_MISSING in _errors(brief)


def test_a_complete_option_set_passes_both() -> None:
    brief = _run()
    assert brief.has_non_ai_alternative
    assert brief.has_no_build_alternative
    assert ValidationCode.NON_AI_ALTERNATIVE_MISSING not in _codes(brief)
    assert ValidationCode.NO_BUILD_ALTERNATIVE_MISSING not in _codes(brief)


# --------------------------------------------------------------------------- #
# 6 & 7. Unsupported citation, missing source span
# --------------------------------------------------------------------------- #


def test_a_recommendation_claim_citing_nothing_is_reported() -> None:
    bare = Claim(id="CL-X", statement="It will work.", claim_type=ClaimType.FACT)
    script = _script(
        recommendation=RecommendationOutput(
            recommendation=_recommendation(claims=(bare,))
        ).model_dump_json()
    )
    brief = _run(script)
    assert ValidationCode.UNGROUNDED_CLAIM in _errors(brief)


def test_a_fabricated_quote_is_refused_by_the_stage_that_produced_it() -> None:
    """The strongest guarantee the workflow makes.

    A quote that is not in the record never reaches a brief at all: the skill
    that produced it re-prompts once and then fails, so the section is absent and
    labelled failed rather than present and wrong. Validation is the second line
    of defence for the same fault, exercised directly in `test_validation.py` —
    that is what protects the unvalidated baseline arm in Phase 10.
    """
    invented = Claim(
        id="CL-X",
        statement="Exceptions fell by half.",
        claim_type=ClaimType.FACT,
        citations=(_cite("EV-1", "Exceptions fell by half last quarter."),),
    )
    script = _script(
        recommendation=RecommendationOutput(
            recommendation=_recommendation(claims=(invented,))
        ).model_dump_json()
    )
    brief = _run(script)

    assert brief.recommendation is None
    assert ValidationCode.STAGE_FAILED in _errors(brief)
    assert ValidationCode.CITATION_SPAN_MISSING not in _codes(brief), "nothing got through"


def test_a_fabricated_evidence_id_is_refused_by_the_stage_that_produced_it() -> None:
    ghost = Claim(
        id="CL-X",
        statement="A pilot succeeded.",
        claim_type=ClaimType.FACT,
        citations=(Citation(evidence_id="EV-999", quote="A pilot succeeded."),),
    )
    brief = _run(_script(classification=ClassificationOutput(claims=(ghost,)).model_dump_json()))

    assert brief.claims == ()
    assert ValidationCode.STAGE_FAILED in _codes(brief)
    assert ValidationCode.SECTION_MISSING in _errors(brief)
    assert ValidationCode.SOURCE_MISSING not in _codes(brief)


def test_the_failed_stage_is_named_so_the_gap_is_attributable() -> None:
    invented = Claim(
        id="CL-X",
        statement="Exceptions fell by half.",
        claim_type=ClaimType.FACT,
        citations=(_cite("EV-1", "not in the record"),),
    )
    script = _script(
        recommendation=RecommendationOutput(
            recommendation=_recommendation(claims=(invented,))
        ).model_dump_json()
    )
    brief = _run(script)

    (issue,) = [i for i in brief.validation_issues if i.code == ValidationCode.STAGE_FAILED]
    assert "The recommendation stage" in issue.message


# --------------------------------------------------------------------------- #
# 8. Excessive confidence
# --------------------------------------------------------------------------- #


def _incomplete_options_script(**overrides: Any) -> dict[str, Any]:
    """A run whose option set is missing a mandatory choice.

    The route by which a brief can legitimately hold strong support that the
    evidence does not carry: the alternatives stage fails, so the requirement is
    unmet, but the recommendation stage still succeeds on its own terms.
    """
    return _script(
        alternatives=ModelUnavailable("option generation is down"),
        recommendation=RecommendationOutput(
            recommendation=_recommendation(
                support_level=SupportLevel.STRONG,
                what_would_change_it=("A verified baseline.",),
            )
        ).model_dump_json(),
        **overrides,
    )


def test_strong_support_is_reduced_when_a_mandatory_option_is_missing() -> None:
    brief = _run(_incomplete_options_script())

    assert brief.recommendation is not None
    assert brief.recommendation.support_level is SupportLevel.MODERATE
    assert "Support reduced from strong to moderate" in brief.recommendation.support_basis
    assert "no non-AI alternative" in brief.recommendation.support_basis
    assert ValidationCode.SUPPORT_REDUCED in _codes(brief)


def test_an_ungrounded_supporting_claim_drives_support_to_low() -> None:
    """The recommendation skill caps it once; the brief-level check caps it again."""
    bare = Claim(id="CL-X", statement="It will work.", claim_type=ClaimType.FACT)
    script = _script(
        recommendation=RecommendationOutput(
            recommendation=_recommendation(
                claims=(bare,),
                support_level=SupportLevel.STRONG,
                what_would_change_it=("Anything verifiable.",),
            )
        ).model_dump_json()
    )
    brief = _run(script)

    assert brief.recommendation is not None
    assert brief.recommendation.support_level is SupportLevel.LOW
    assert ValidationCode.UNGROUNDED_CLAIM in _errors(brief)


def test_the_challenger_can_lower_confidence_on_its_own() -> None:
    challenge = ChallengeOutput(
        findings=_findings(overconfident=ChallengeVerdict.FAILS),
        what_would_change_it=("A randomised trial.",),
        recommended_support=SupportLevel.LOW,
    ).model_dump_json()
    brief = _run(_script(challenger=challenge))

    assert brief.recommendation is not None
    assert brief.recommendation.support_level is SupportLevel.LOW
    assert "challenger judged the draft overconfident" in brief.recommendation.support_basis
    assert ValidationCode.CHALLENGE_FAILED in _errors(brief)


def test_two_ceilings_produce_one_reduction_with_one_explanation() -> None:
    """The evidence says at most moderate; the challenger says low. One act, not two."""
    challenge = ChallengeOutput(
        findings=_findings(overconfident=ChallengeVerdict.CONCERN),
        recommended_support=SupportLevel.LOW,
    ).model_dump_json()
    brief = _run(_incomplete_options_script(challenger=challenge))

    assert brief.recommendation is not None
    assert brief.recommendation.support_level is SupportLevel.LOW
    reductions = [i for i in brief.validation_issues if i.code == ValidationCode.SUPPORT_REDUCED]
    assert len(reductions) == 1
    assert brief.recommendation.support_basis.count("Support reduced") == 1


# --------------------------------------------------------------------------- #
# 9. Governance
# --------------------------------------------------------------------------- #


def test_a_governance_constraint_survives_into_the_brief() -> None:
    brief = _run()
    governance = [c for c in brief.constraints if c.claim_type is ClaimType.GOVERNANCE_CONSTRAINT]
    assert [c.id for c in governance] == ["CL-3"]


def test_the_governance_constraint_is_rendered_into_the_alternatives_prompt() -> None:
    """An option set produced in ignorance of a governance limit is not credible."""
    seen: list[ModelRequest] = []

    class Recording(ScriptedProvider):
        def complete(self, request: ModelRequest) -> ModelResponse:
            seen.append(request)
            return super().complete(request)

    lens = DecisionLens(Recording(_script()), (FakeSource(*_evidence()),), as_of=AS_OF, clock=CLOCK)
    lens.run(_request())

    alternatives_prompt = next(r for r in seen if r.skill == "alternatives").user
    assert "Delivery photos cannot be retained beyond 30 days." in alternatives_prompt


# --------------------------------------------------------------------------- #
# 10 & 11. Partial provider failure and timeout
# --------------------------------------------------------------------------- #


def test_one_failed_stage_degrades_the_brief_rather_than_aborting_it() -> None:
    brief = _run(_script(contradictions=ModelUnavailable("provider is down")))

    assert brief.recommendation is not None, "the run continued past the failure"
    assert brief.contradictions == ()
    assert ValidationCode.STAGE_FAILED in _errors(brief)


def test_a_failed_stage_is_distinguishable_from_a_stage_that_found_nothing() -> None:
    """The distinction the whole partial-failure design exists to preserve."""
    brief = _run(_script(contradictions=ModelUnavailable("provider is down")))
    (issue,) = [i for i in brief.validation_issues if i.code == ValidationCode.STAGE_FAILED]
    assert "absent because it failed" in issue.message
    assert "not because there was nothing to report" in issue.message
    assert "\n" not in issue.message, "issues render as one line each; a dump breaks the layout"


def test_a_timeout_on_the_recommendation_leaves_a_brief_without_one() -> None:
    brief = _run(_script(recommendation=ModelTimeout("took too long")))

    assert brief.recommendation is None
    assert brief.claims, "earlier stages survived"
    assert brief.alternatives
    assert ValidationCode.SECTION_MISSING in _errors(brief)
    assert ValidationCode.STAGE_FAILED in _errors(brief)


def test_the_challenger_still_runs_when_the_recommendation_failed() -> None:
    """There is still an option set and a claim list worth attacking."""
    lens = _lens(_script(recommendation=ModelTimeout("took too long")))
    lens.run(_request())
    provider = lens.provider
    assert isinstance(provider, ScriptedProvider)
    assert "challenger" in provider.seen


def test_a_dead_evidence_source_degrades_the_run() -> None:
    brief = _run(
        _script(),
        FakeSource(error=EvidenceSourceError("directory is unreadable")),
        FakeSource(*_evidence()),
    )
    notes = [i.message for i in brief.validation_issues if i.code == ValidationCode.ANALYSIS_NOTE]
    assert any("contributed no evidence" in n for n in notes)
    assert brief.evidence, "the healthy source still contributed"


def test_every_source_failing_is_the_no_evidence_case() -> None:
    brief = _run(_script(), FakeSource(error=EvidenceSourceError("gone")))
    assert brief.evidence == ()
    assert ValidationCode.SECTION_MISSING in _errors(brief)


# --------------------------------------------------------------------------- #
# 12. The cached demo
# --------------------------------------------------------------------------- #


def _cache_file(tmp_path: Path) -> Path:
    cache = DemoCache()
    for skill, text in _script().items():
        cache.add(
            CachedResponse(
                key=f"DR-001::{skill}::v1",
                text=text,
                recorded_from_model="claude-opus-5",
                recorded_at=datetime(2026, 8, 1, 12, 0, 0),
                input_tokens=900,
                output_tokens=250,
            )
        )
    path = tmp_path / "demo_cache.json"
    cache.save(path)
    return path


def test_the_whole_workflow_runs_offline_from_recorded_output(tmp_path: Path) -> None:
    """No credential, no network, same answer every time."""
    lens = DecisionLens(
        CachedDemoProvider(_cache_file(tmp_path)),
        (FakeSource(*_evidence()),),
        as_of=AS_OF,
        clock=CLOCK,
    )
    brief = lens.run(_request())

    assert brief.recommendation is not None
    assert _errors(brief) == set()


def test_a_cached_run_is_reproducible(tmp_path: Path) -> None:
    path = _cache_file(tmp_path)

    def once() -> str:
        lens = DecisionLens(
            CachedDemoProvider(path), (FakeSource(*_evidence()),), as_of=AS_OF, clock=CLOCK
        )
        return lens.run(_request()).model_dump_json()

    assert once() == once()


def test_a_cached_run_never_claims_to_be_live(tmp_path: Path) -> None:
    lens = DecisionLens(
        CachedDemoProvider(_cache_file(tmp_path)),
        (FakeSource(*_evidence()),),
        as_of=AS_OF,
        clock=CLOCK,
    )
    trace = lens.run(_request()).run_trace
    assert trace is not None
    model_stages = [s for s in trace.stages if s.provider]
    assert {s.provider for s in model_stages} == {"cached-demo"}
    assert {s.model for s in model_stages} == {"recorded-replay"}


# --------------------------------------------------------------------------- #
# 13. The PM's decision stays separate
# --------------------------------------------------------------------------- #


def test_running_the_workflow_does_not_record_a_decision() -> None:
    """DecisionLens recommends. A person decides. The two never merge."""
    brief = _run()
    assert brief.recommendation is not None
    assert not hasattr(brief, "pm_decision")
    assert brief.decision_owner_notice
    assert "product manager remains accountable" in brief.decision_owner_notice


def test_a_pm_decision_is_recorded_by_a_separate_call() -> None:
    brief = _run()
    decision = record_pm_decision(
        brief,
        decided_by="pm-001",
        decision="Run the address-validation pilot for one quarter.",
        rationale="The cheaper option is testable sooner.",
        agreed_with_recommendation=True,
        decided_at=CLOCK,
    )
    assert decision.brief_id == brief.id
    assert decision.decided_at == CLOCK


def test_disagreeing_with_the_recommendation_requires_a_reason() -> None:
    """The disagreement is the signal worth capturing."""
    brief = _run()
    with pytest.raises(ValueError, match="override_reason"):
        record_pm_decision(
            brief,
            decided_by="pm-001",
            decision="Build the AI assistant anyway.",
            agreed_with_recommendation=False,
        )


def test_a_recorded_disagreement_keeps_its_reason() -> None:
    brief = _run()
    decision = record_pm_decision(
        brief,
        decided_by="pm-001",
        decision="Build the AI assistant anyway.",
        agreed_with_recommendation=False,
        override_reason="A commitment was already made to the customer.",
        decided_at=CLOCK,
    )
    assert decision.agreed_with_recommendation is False
    assert decision.override_reason


def test_a_decision_defaults_its_timestamp() -> None:
    decision = record_pm_decision(_run(), decided_by="pm-001", decision="Defer.")
    assert decision.decided_at is not None


# --------------------------------------------------------------------------- #
# Normalization and relevance
# --------------------------------------------------------------------------- #


def test_a_repeated_evidence_id_is_dropped() -> None:
    duplicate = _record("EV-1", "Different text entirely.", EvidenceType.OPERATIONAL_RECORD)
    brief = _run(_script(), FakeSource(*_evidence()), FakeSource(duplicate))

    assert [e.id for e in brief.evidence].count("EV-1") == 1
    notes = [i.message for i in brief.validation_issues if i.code == ValidationCode.ANALYSIS_NOTE]
    assert any("repeated an evidence id" in n for n in notes)


def test_the_same_passage_from_two_sources_is_counted_once() -> None:
    """Counting one passage twice would turn a single opinion into a consensus."""
    same = _record("EV-9", FACT, EvidenceType.OPERATIONAL_RECORD).model_copy(
        update={"source_reference": "data/EV-1.md"}
    )
    brief = _run(_script(), FakeSource(*_evidence()), FakeSource(same))

    assert "EV-9" not in {e.id for e in brief.evidence}
    notes = [i.message for i in brief.validation_issues if i.code == ValidationCode.ANALYSIS_NOTE]
    assert any("duplicated content" in n for n in notes)


def test_evidence_set_aside_by_relevance_is_named() -> None:
    script = _script(
        relevance=RelevanceOutput(
            relevant_ids=("EV-1", "EV-3"),
            excluded=({"evidence_id": "EV-2", "reason": "about a different product area"},),
        ).model_dump_json()
    )
    brief = _run(script)

    assert {e.id for e in brief.evidence} == {"EV-1", "EV-3"}
    notes = [i.message for i in brief.validation_issues if i.code == ValidationCode.ANALYSIS_NOTE]
    assert any("EV-2" in n and "set aside" in n for n in notes)


def test_relevance_selecting_nothing_leaves_the_evidence_alone() -> None:
    """A skill that excludes everything has malfunctioned; it does not get to empty the brief."""
    script = _script(relevance=RelevanceOutput(relevant_ids=()).model_dump_json())
    brief = _run(script)
    assert len(brief.evidence) == 3


def test_a_failed_relevance_stage_keeps_all_evidence() -> None:
    brief = _run(_script(relevance=ModelUnavailable("down")))
    assert len(brief.evidence) == 3
    assert brief.recommendation is not None


# --------------------------------------------------------------------------- #
# Challenger effects
# --------------------------------------------------------------------------- #


def test_what_would_change_it_is_merged_without_duplication() -> None:
    challenge = ChallengeOutput(
        findings=_findings(),
        what_would_change_it=(
            "A measured baseline by segment.",  # already on the draft
            "A cost estimate for validation tooling.",
        ),
    ).model_dump_json()
    brief = _run(_script(challenger=challenge))

    assert brief.recommendation is not None
    items = brief.recommendation.what_would_change_it
    assert items.count("A measured baseline by segment.") == 1
    assert "A cost estimate for validation tooling." in items


def test_what_to_test_becomes_a_condition_on_the_recommendation() -> None:
    challenge = ChallengeOutput(
        findings=_findings(),
        what_to_test=("Whether validation catches the addresses that actually fail.",),
    ).model_dump_json()
    brief = _run(_script(challenger=challenge))

    assert brief.recommendation is not None
    assert any("Test before investing" in c for c in brief.recommendation.conditions)


def test_a_failed_challenger_stage_is_an_error() -> None:
    """A recommendation nobody argued with has not been through this process."""
    brief = _run(_script(challenger=ModelUnavailable("down")))
    stage_issues = [i for i in brief.validation_issues if i.code == ValidationCode.STAGE_FAILED]
    assert any(i.severity.value == "error" for i in stage_issues)


def test_challenger_concerns_become_warnings_not_errors() -> None:
    challenge = ChallengeOutput(
        findings=_findings(what_to_test=ChallengeVerdict.CONCERN)
    ).model_dump_json()
    brief = _run(_script(challenger=challenge))

    assert ValidationCode.CHALLENGE_CONCERN in _codes(brief)
    assert ValidationCode.CHALLENGE_CONCERN not in _errors(brief)


def test_a_passing_challenge_adds_nothing() -> None:
    brief = _run()
    assert ValidationCode.CHALLENGE_CONCERN not in _codes(brief)
    assert ValidationCode.CHALLENGE_FAILED not in _codes(brief)

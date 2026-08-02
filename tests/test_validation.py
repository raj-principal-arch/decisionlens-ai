"""Deterministic checks, and the single place confidence is lowered.

Two properties are load-bearing and each has a test of its own: `validate` never
mutates, and `enforce_support_ceiling` is idempotent. Between them they are why a
support level in a finished brief can be trusted to mean what it says.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from decision_lens.models import (
    Alternative,
    Citation,
    Claim,
    ClaimType,
    Contradiction,
    ContradictionKind,
    DecisionBrief,
    DecisionCriteria,
    DecisionRequest,
    EvidenceRecord,
    EvidenceType,
    GapImpact,
    MissingEvidence,
    OptionKind,
    Recommendation,
    RunStage,
    RunTrace,
    SourceSystem,
    SupportLevel,
    UserContext,
    ValidationIssue,
    ValidationSeverity,
)
from decision_lens.provenance import check_provenance
from decision_lens.validation import (
    ValidationCode,
    enforce_support_ceiling,
    support_ceiling,
    validate,
    weaker_of,
)

GENERATED_AT = datetime(2026, 8, 2, 9, 0, 0)
QUOTE = "Address errors account for 40% of delivery exceptions."


def _record(record_id: str = "EV-1", content: str = QUOTE) -> EvidenceRecord:
    return EvidenceRecord(
        id=record_id,
        source_system=SourceSystem.LOCAL_FILE,
        source_id=f"{record_id}.md",
        content=content,
        evidence_type=EvidenceType.OPERATIONAL_RECORD,
    )


def _cite(record_id: str = "EV-1", quote: str = QUOTE) -> Citation:
    return Citation(evidence_id=record_id, quote=quote)


def _claim(
    claim_id: str = "CL-1", *citations: Citation, claim_type: ClaimType = ClaimType.FACT
) -> Claim:
    return Claim(
        id=claim_id,
        statement="Address quality drives exceptions.",
        claim_type=claim_type,
        citations=citations,
    )


def _request(**criteria: bool) -> DecisionRequest:
    return DecisionRequest(
        id="DR-001",
        question="Which intervention should the team prioritize?",
        user=UserContext(user_id="pm-001"),
        criteria=DecisionCriteria(**criteria),
    )


def _alternatives() -> tuple[Alternative, ...]:
    return (
        Alternative(id="ALT-1", name="Validate addresses", kind=OptionKind.DATA_QUALITY),
        Alternative(id="ALT-2", name="Do nothing", kind=OptionKind.NO_CHANGE),
    )


def _recommendation(**kwargs: object) -> Recommendation:
    base: dict[str, object] = {
        "statement": "Validate addresses first.",
        "option_kind": OptionKind.DATA_QUALITY,
        "selected_alternative_id": "ALT-1",
        "claims": (_claim("CL-R", _cite()),),
        "support_level": SupportLevel.MODERATE,
    }
    return Recommendation(**{**base, **kwargs})


def _brief(**kwargs: object) -> DecisionBrief:
    base: dict[str, object] = {
        "id": "DB-001",
        "request": _request(),
        "generated_at": GENERATED_AT,
        "evidence": (_record(),),
        "claims": (_claim("CL-1", _cite()),),
        "missing_evidence": (
            MissingEvidence(
                id="MG-1",
                question="What does address validation cost?",
                impact=GapImpact.WOULD_CHANGE_SUPPORT_LEVEL,
                why_it_matters="The business case depends on it.",
            ),
        ),
        "alternatives": _alternatives(),
        "recommendation": _recommendation(),
    }
    return DecisionBrief(**{**base, **kwargs})


def _codes(brief: DecisionBrief, **kwargs: Any) -> set[str]:
    return {i.code for i in validate(brief, **kwargs)}


# --------------------------------------------------------------------------- #
# Ordering
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (SupportLevel.LOW, SupportLevel.STRONG, SupportLevel.LOW),
        (SupportLevel.STRONG, SupportLevel.LOW, SupportLevel.LOW),
        (SupportLevel.MODERATE, SupportLevel.MODERATE, SupportLevel.MODERATE),
        (SupportLevel.STRONG, SupportLevel.MODERATE, SupportLevel.MODERATE),
    ],
)
def test_weaker_of_picks_the_more_cautious(
    a: SupportLevel, b: SupportLevel, expected: SupportLevel
) -> None:
    assert weaker_of(a, b) is expected


# --------------------------------------------------------------------------- #
# The checks
# --------------------------------------------------------------------------- #


def test_a_sound_brief_produces_no_errors() -> None:
    issues = validate(_brief())
    assert [i for i in issues if i.blocks_presentation] == []


def test_a_missing_source_and_a_missing_span_are_separate_errors() -> None:
    brief = _brief(
        claims=(_claim("CL-1", _cite("EV-GONE")), _claim("CL-2", _cite("EV-1", "not present")))
    )
    codes = _codes(brief)
    assert ValidationCode.SOURCE_MISSING in codes
    assert ValidationCode.CITATION_SPAN_MISSING in codes


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence", ()),
        ("claims", ()),
        ("alternatives", ()),
        ("recommendation", None),
    ],
)
def test_each_required_section_is_checked(field: str, value: object) -> None:
    issues = validate(_brief(**{field: value}))
    missing = [i for i in issues if i.code == ValidationCode.SECTION_MISSING]
    assert [i.location for i in missing] == [field]
    assert all(i.severity is ValidationSeverity.ERROR for i in missing)


def test_an_unsupported_fact_is_an_assumption_wearing_a_label() -> None:
    """The checkable form of 'separate assumptions from facts'."""
    brief = _brief(claims=(_claim("CL-1", claim_type=ClaimType.FACT),))
    issues = [i for i in validate(brief) if i.code == ValidationCode.UNGROUNDED_FACT]
    assert len(issues) == 1
    assert "label it as one" in issues[0].message


def test_an_uncited_assumption_is_fine() -> None:
    """Only a *fact* claim needs backing. An assumption is allowed to be one."""
    brief = _brief(claims=(_claim("CL-1", claim_type=ClaimType.ASSUMPTION),))
    assert ValidationCode.UNGROUNDED_FACT not in _codes(brief)


def test_a_recommendation_resting_on_nothing_is_an_error() -> None:
    brief = _brief(recommendation=_recommendation(claims=(_claim("CL-R"),)))
    assert ValidationCode.UNGROUNDED_CLAIM in _codes(brief)


def _contradiction(side_a: str = "EV-1", side_b: str = "EV-2") -> Contradiction:
    return Contradiction(
        id="CN-1",
        topic="the leading cause of exceptions",
        kind=ContradictionKind.CLAIM_CONFLICT,
        side_a=_cite(side_a),
        side_b=_cite(side_b, "A different account entirely."),
        how_to_resolve="Recount by cause.",
    )


def test_a_recommendation_built_on_one_side_of_a_conflict_says_so() -> None:
    """Every claim cited, every citation resolving, and the conflict two sections away.

    The shape a reader is least likely to catch, which is why it is checked.
    """
    brief = _brief(
        evidence=(_record("EV-1"), _record("EV-2", "A different account entirely.")),
        contradictions=(_contradiction(),),
        recommendation=_recommendation(claims=(_claim("CL-R", _cite("EV-1")),)),
    )
    (issue,) = [i for i in validate(brief) if i.code == ValidationCode.CONTESTED_SUPPORT]

    assert issue.severity is ValidationSeverity.WARNING
    assert "EV-1" in issue.message
    assert "CN-1" in issue.message


def test_a_recommendation_on_uncontested_evidence_is_not_flagged() -> None:
    brief = _brief(
        evidence=(
            _record("EV-1"),
            _record("EV-2", "A different account entirely."),
            _record("EV-3", "Something nobody disputes."),
        ),
        contradictions=(_contradiction(),),
        recommendation=_recommendation(
            claims=(_claim("CL-R", _cite("EV-3", "Something nobody disputes.")),)
        ),
    )
    assert ValidationCode.CONTESTED_SUPPORT not in _codes(brief)


def test_choosing_a_side_is_allowed_it_just_cannot_be_silent() -> None:
    """A warning, never an error. Picking a side of a live disagreement is legitimate."""
    brief = _brief(
        evidence=(_record("EV-1"), _record("EV-2", "A different account entirely.")),
        contradictions=(_contradiction(),),
        recommendation=_recommendation(claims=(_claim("CL-R", _cite("EV-1")),)),
    )
    assert ValidationCode.CONTESTED_SUPPORT not in {
        i.code for i in validate(brief) if i.blocks_presentation
    }


def test_no_contradictions_means_nothing_to_flag() -> None:
    assert ValidationCode.CONTESTED_SUPPORT not in _codes(_brief())


def test_no_recommendation_means_nothing_to_flag() -> None:
    brief = _brief(
        evidence=(_record("EV-1"), _record("EV-2", "A different account entirely.")),
        contradictions=(_contradiction(),),
        recommendation=None,
    )
    assert ValidationCode.CONTESTED_SUPPORT not in _codes(brief)


def test_a_failed_critical_stage_is_an_error() -> None:
    """A brief whose contradiction check crashed looks identical to one with no
    conflicts, unless it is said out loud."""
    brief = _brief(
        run_trace=RunTrace(
            run_id="r",
            request_id="DR-001",
            stages=(RunStage(name="contradictions", error="provider timed out"),),
        )
    )
    (issue,) = [i for i in validate(brief) if i.code == ValidationCode.STAGE_FAILED]
    assert issue.severity is ValidationSeverity.ERROR
    assert "because it failed" in issue.message


def test_a_failed_non_critical_stage_is_a_warning() -> None:
    brief = _brief(
        run_trace=RunTrace(
            run_id="r",
            request_id="DR-001",
            stages=(RunStage(name="relevance", error="nope"),),
        )
    )
    (issue,) = [i for i in validate(brief) if i.code == ValidationCode.STAGE_FAILED]
    assert issue.severity is ValidationSeverity.WARNING


def test_a_retry_stage_is_attributed_to_its_skill() -> None:
    brief = _brief(
        run_trace=RunTrace(
            run_id="r",
            request_id="DR-001",
            stages=(RunStage(name="recommendation-retry", error="still broken"),),
        )
    )
    (issue,) = [i for i in validate(brief) if i.code == ValidationCode.STAGE_FAILED]
    assert issue.severity is ValidationSeverity.ERROR
    assert "The recommendation stage" in issue.message


def test_a_run_with_no_trace_reports_no_stage_failures() -> None:
    assert ValidationCode.STAGE_FAILED not in _codes(_brief(run_trace=None))


def test_finding_no_gaps_at_all_is_suspicious() -> None:
    issues = [
        i
        for i in validate(_brief(missing_evidence=()))
        if i.code == ValidationCode.NO_MISSING_EVIDENCE
    ]
    assert len(issues) == 1
    assert issues[0].severity is ValidationSeverity.WARNING


def test_an_all_ai_option_set_has_assumed_its_answer() -> None:
    brief = _brief(
        alternatives=(Alternative(id="ALT-1", name="Build AI", kind=OptionKind.AI_ASSISTED),)
    )
    assert ValidationCode.NON_AI_ALTERNATIVE_MISSING in _codes(brief)


def test_a_missing_no_build_option_is_an_error() -> None:
    brief = _brief(
        alternatives=(Alternative(id="ALT-1", name="Validate", kind=OptionKind.DATA_QUALITY),)
    )
    assert ValidationCode.NO_BUILD_ALTERNATIVE_MISSING in _codes(brief)


def test_the_alternative_requirements_can_be_waived_by_the_request() -> None:
    """A PM may turn them off. The check honours the criteria rather than the opinion."""
    brief = _brief(
        request=_request(require_non_ai_alternative=False, require_no_build_alternative=False),
        alternatives=(Alternative(id="ALT-1", name="Build AI", kind=OptionKind.AI_ASSISTED),),
    )
    codes = _codes(brief)
    assert ValidationCode.NON_AI_ALTERNATIVE_MISSING not in codes
    assert ValidationCode.NO_BUILD_ALTERNATIVE_MISSING not in codes


def test_evidence_nobody_cited_is_a_warning_not_an_error() -> None:
    brief = _brief(evidence=(_record("EV-1"), _record("EV-2", "Unrelated text.")))
    (issue,) = [i for i in validate(brief) if i.code == ValidationCode.UNCITED_EVIDENCE]
    assert issue.severity is ValidationSeverity.WARNING
    assert "EV-2" in issue.message


def test_extra_issues_are_folded_into_one_list() -> None:
    extra = ValidationIssue(
        code="challenge_concern", severity=ValidationSeverity.WARNING, message="from elsewhere"
    )
    assert extra in validate(_brief(), extra=(extra,))


def test_validate_never_mutates_the_brief() -> None:
    brief = _brief(recommendation=_recommendation(support_level=SupportLevel.STRONG))
    before = brief.model_dump_json()
    validate(brief)
    validate(brief)
    assert brief.model_dump_json() == before


# --------------------------------------------------------------------------- #
# The support ceiling
# --------------------------------------------------------------------------- #


def test_a_sound_brief_has_no_ceiling() -> None:
    brief = _brief()
    assert support_ceiling(brief, check_provenance(brief)) is None


def test_a_broken_citation_inside_the_recommendation_caps_at_low() -> None:
    """Support is resting directly on something that could not be verified."""
    brief = _brief(recommendation=_recommendation(claims=(_claim("CL-R", _cite("EV-1", "nope")),)))
    assert support_ceiling(brief, check_provenance(brief)) is SupportLevel.LOW


def test_a_broken_citation_elsewhere_caps_at_moderate() -> None:
    brief = _brief(claims=(_claim("CL-1", _cite("EV-1", "nope")),))
    assert support_ceiling(brief, check_provenance(brief)) is SupportLevel.MODERATE


def test_a_missing_mandatory_alternative_caps_at_moderate() -> None:
    brief = _brief(
        alternatives=(Alternative(id="ALT-1", name="Build AI", kind=OptionKind.AI_ASSISTED),)
    )
    assert support_ceiling(brief, check_provenance(brief)) is SupportLevel.MODERATE


def test_the_weakest_ceiling_wins() -> None:
    brief = _brief(
        claims=(_claim("CL-1", _cite("EV-1", "nope")),),
        recommendation=_recommendation(claims=(_claim("CL-R"),)),
    )
    assert support_ceiling(brief, check_provenance(brief)) is SupportLevel.LOW


def test_stating_more_support_than_the_evidence_carries_is_an_error() -> None:
    brief = _brief(
        alternatives=(Alternative(id="ALT-1", name="Build AI", kind=OptionKind.AI_ASSISTED),),
        recommendation=_recommendation(support_level=SupportLevel.STRONG),
    )
    (issue,) = [i for i in validate(brief) if i.code == ValidationCode.SUPPORT_TOO_HIGH]
    assert issue.severity is ValidationSeverity.ERROR
    assert "at most moderate" in issue.message


# --------------------------------------------------------------------------- #
# Enforcement
# --------------------------------------------------------------------------- #


def test_enforcement_lowers_support_and_writes_the_reason_into_the_brief() -> None:
    brief = _brief(
        alternatives=(Alternative(id="ALT-1", name="Build AI", kind=OptionKind.AI_ASSISTED),),
        recommendation=_recommendation(support_level=SupportLevel.STRONG),
    )
    capped, issues = enforce_support_ceiling(brief)

    assert capped.recommendation is not None
    assert capped.recommendation.support_level is SupportLevel.MODERATE
    assert "Support reduced from strong to moderate" in capped.recommendation.support_basis
    assert "no non-AI alternative" in capped.recommendation.support_basis
    assert [i.code for i in issues] == [ValidationCode.SUPPORT_REDUCED]


def test_enforcement_is_idempotent() -> None:
    """Running it twice must not compound the annotation or lower support again."""
    brief = _brief(
        alternatives=(Alternative(id="ALT-1", name="Build AI", kind=OptionKind.AI_ASSISTED),),
        recommendation=_recommendation(support_level=SupportLevel.STRONG),
    )
    once, _ = enforce_support_ceiling(brief)
    twice, issues = enforce_support_ceiling(once)
    assert twice.model_dump_json() == once.model_dump_json()
    assert issues == ()


def test_enforcement_leaves_a_sound_brief_alone() -> None:
    brief = _brief()
    capped, issues = enforce_support_ceiling(brief)
    assert capped is brief
    assert issues == ()


def test_enforcement_does_nothing_without_a_recommendation() -> None:
    brief = _brief(recommendation=None)
    capped, issues = enforce_support_ceiling(brief)
    assert capped is brief
    assert issues == ()


def test_the_challenger_can_lower_support_on_its_own() -> None:
    brief = _brief(recommendation=_recommendation(support_level=SupportLevel.STRONG))
    capped, issues = enforce_support_ceiling(brief, challenger_ceiling=SupportLevel.LOW)

    assert capped.recommendation is not None
    assert capped.recommendation.support_level is SupportLevel.LOW
    assert "challenger judged the draft overconfident" in issues[0].message


def test_evidence_and_challenger_ceilings_combine_to_the_weakest() -> None:
    brief = _brief(
        claims=(_claim("CL-1", _cite("EV-1", "nope")),),
        recommendation=_recommendation(support_level=SupportLevel.STRONG),
    )
    capped, _ = enforce_support_ceiling(brief, challenger_ceiling=SupportLevel.LOW)
    assert capped.recommendation is not None
    assert capped.recommendation.support_level is SupportLevel.LOW


def test_a_challenger_ceiling_above_the_current_level_changes_nothing() -> None:
    brief = _brief(recommendation=_recommendation(support_level=SupportLevel.LOW))
    capped, issues = enforce_support_ceiling(brief, challenger_ceiling=SupportLevel.STRONG)
    assert capped is brief
    assert issues == ()


def test_the_reduction_names_unresolved_citations() -> None:
    brief = _brief(
        claims=(_claim("CL-1", _cite("EV-1", "nope")),),
        recommendation=_recommendation(support_level=SupportLevel.STRONG),
    )
    _, (issue,) = enforce_support_ceiling(brief)
    assert "1 citation(s) do not resolve" in issue.message


def test_the_reduction_names_ungrounded_supporting_claims() -> None:
    brief = _brief(
        recommendation=_recommendation(claims=(_claim("CL-R"),), support_level=SupportLevel.STRONG)
    )
    _, (issue,) = enforce_support_ceiling(brief)
    assert "cite nothing" in issue.message


def test_the_reduction_names_a_missing_no_build_option() -> None:
    brief = _brief(
        alternatives=(Alternative(id="ALT-1", name="Validate", kind=OptionKind.DATA_QUALITY),),
        recommendation=_recommendation(support_level=SupportLevel.STRONG),
    )
    _, (issue,) = enforce_support_ceiling(brief)
    assert "no no-build alternative" in issue.message

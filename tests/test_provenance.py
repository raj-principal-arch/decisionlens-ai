"""Citation resolution.

The tests that matter most here are the drift guard — that the citation walk
covers exactly what `DecisionBrief.all_citations` covers, so it cannot quietly
start checking a subset — and the separation of a missing source from a missing
quote, which have different causes and different fixes.
"""

from __future__ import annotations

from datetime import datetime

from decision_lens.models import (
    Alternative,
    AssessmentState,
    Citation,
    Claim,
    ClaimType,
    Contradiction,
    ContradictionKind,
    DecisionBrief,
    DecisionRequest,
    Dimension,
    DimensionAssessment,
    EvidenceRecord,
    EvidenceType,
    OptionKind,
    PriorityException,
    PriorityExceptionKind,
    Recommendation,
    SourceSystem,
)
from decision_lens.provenance import (
    BriefSection,
    ResolutionFailure,
    check_provenance,
    iter_citations,
)

GENERATED_AT = datetime(2026, 8, 2, 9, 0, 0)
QUOTE = "Address errors account for 40% of delivery exceptions."
OTHER = "Apartment deliveries fail more often than houses."


def _record(record_id: str, *quotes: str) -> EvidenceRecord:
    return EvidenceRecord(
        id=record_id,
        source_system=SourceSystem.LOCAL_FILE,
        source_id=f"{record_id}.md",
        source_reference=f"data/{record_id}.md",
        content="\n".join(quotes),
        evidence_type=EvidenceType.OPERATIONAL_RECORD,
    )


def _cite(record_id: str = "EV-1", quote: str = QUOTE) -> Citation:
    return Citation(evidence_id=record_id, quote=quote)


def _claim(claim_id: str = "CL-1", *citations: Citation, **kwargs: object) -> Claim:
    return Claim(
        id=claim_id,
        statement="Address quality drives exceptions.",
        claim_type=kwargs.pop("claim_type", ClaimType.FACT),
        citations=citations,
        **kwargs,
    )


def _brief(request_: DecisionRequest, **kwargs: object) -> DecisionBrief:
    base: dict[str, object] = {
        "id": "DB-001",
        "request": request_,
        "generated_at": GENERATED_AT,
        "evidence": (_record("EV-1", QUOTE, OTHER),),
    }
    return DecisionBrief(**{**base, **kwargs})


# --------------------------------------------------------------------------- #
# The walk
# --------------------------------------------------------------------------- #


def test_the_walk_covers_exactly_what_the_brief_reports(request_: DecisionRequest) -> None:
    """Drift guard.

    If these two ever disagree, one of them is checking part of the brief while
    appearing to check all of it — and the half that is silently skipped is where
    an unverifiable citation would live.
    """
    brief = _brief(
        request_,
        claims=(_claim("CL-1", _cite()),),
        contradictions=(
            Contradiction(
                id="CN-1",
                topic="cause",
                kind=ContradictionKind.CLAIM_CONFLICT,
                side_a=_cite(),
                side_b=_cite(quote=OTHER),
                how_to_resolve="Recount by segment.",
            ),
        ),
        priority_exceptions=(
            PriorityException(
                id="PX-1",
                kind=PriorityExceptionKind.COMPLIANCE,
                obligation="Retain delivery photos for 30 days.",
                citations=(_cite(),),
            ),
        ),
        alternatives=(
            Alternative(
                id="ALT-1",
                name="Validate addresses",
                kind=OptionKind.DATA_QUALITY,
                supporting=(_cite(),),
                opposing=(_cite(quote=OTHER),),
                assessments=(
                    DimensionAssessment(
                        dimension=Dimension.RISK,
                        state=AssessmentState.ASSESSED,
                        citations=(_cite(),),
                    ),
                ),
            ),
        ),
        recommendation=Recommendation(
            statement="Validate addresses first.",
            option_kind=OptionKind.DATA_QUALITY,
            claims=(_claim("CL-2", _cite()),),
        ),
    )

    walked = [ref.citation for ref in iter_citations(brief)]
    assert walked == list(brief.all_citations())


def test_every_citation_is_tagged_with_where_it_came_from(request_: DecisionRequest) -> None:
    brief = _brief(
        request_,
        claims=(_claim("CL-9", _cite()),),
        recommendation=Recommendation(
            statement="Do the thing.",
            option_kind=OptionKind.PROCESS_CHANGE,
            claims=(_claim("CL-R", _cite()),),
        ),
    )
    by_location = {ref.location: ref.section for ref in iter_citations(brief)}
    assert by_location["claim CL-9"] is BriefSection.CLAIMS
    assert by_location["recommendation claim CL-R"] is BriefSection.RECOMMENDATION


def test_opposing_citations_are_labelled_as_such(request_: DecisionRequest) -> None:
    """A broken quote on the opposing side is a different reading error."""
    brief = _brief(
        request_,
        claims=(_claim("CL-1", _cite(), opposing_citations=(_cite(quote=OTHER),)),),
    )
    locations = [ref.location for ref in iter_citations(brief)]
    assert locations == ["claim CL-1", "claim CL-1 (opposing)"]


def test_contradiction_sides_are_distinguishable(request_: DecisionRequest) -> None:
    brief = _brief(
        request_,
        contradictions=(
            Contradiction(
                id="CN-7",
                topic="cause",
                kind=ContradictionKind.SCOPE_CONFLICT,
                side_a=_cite(),
                side_b=_cite(quote=OTHER),
                how_to_resolve="Split by segment.",
            ),
        ),
    )
    assert [r.location for r in iter_citations(brief)] == [
        "contradiction CN-7 side_a",
        "contradiction CN-7 side_b",
    ]


def test_assessment_citations_name_the_dimension(request_: DecisionRequest) -> None:
    brief = _brief(
        request_,
        alternatives=(
            Alternative(
                id="ALT-2",
                name="Do nothing",
                kind=OptionKind.NO_CHANGE,
                assessments=(
                    DimensionAssessment(
                        dimension=Dimension.DELIVERY_EFFORT,
                        state=AssessmentState.ASSESSED,
                        citations=(_cite(),),
                    ),
                ),
            ),
        ),
    )
    (ref,) = iter_citations(brief)
    assert ref.location == "alternative ALT-2 / delivery_effort"
    assert ref.section is BriefSection.ASSESSMENTS


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def test_a_clean_brief_resolves_completely(request_: DecisionRequest) -> None:
    brief = _brief(request_, claims=(_claim("CL-1", _cite()),))
    report = check_provenance(brief)
    assert report.is_clean
    assert report.validity == 1.0
    assert report.resolved == report.total == 1


def test_an_unknown_evidence_id_is_not_the_same_as_a_bad_quote(
    request_: DecisionRequest,
) -> None:
    """Different causes, different fixes, so never one code."""
    brief = _brief(
        request_,
        claims=(
            _claim("CL-1", _cite("EV-MISSING")),
            _claim("CL-2", _cite("EV-1", "text nobody wrote")),
        ),
    )
    report = check_provenance(brief)

    unknown = report.failures_of(ResolutionFailure.UNKNOWN_EVIDENCE)
    not_found = report.failures_of(ResolutionFailure.QUOTE_NOT_FOUND)
    assert [u.ref.location for u in unknown] == ["claim CL-1"]
    assert [u.ref.location for u in not_found] == ["claim CL-2"]


def test_a_missing_source_says_it_was_never_retrieved(request_: DecisionRequest) -> None:
    brief = _brief(request_, claims=(_claim("CL-1", _cite("EV-GHOST")),))
    (bad,) = check_provenance(brief).unresolved
    assert "not in the evidence retrieved" in bad.describe()


def test_a_missing_span_says_the_quote_must_be_verbatim(request_: DecisionRequest) -> None:
    brief = _brief(request_, claims=(_claim("CL-1", _cite("EV-1", "paraphrased text")),))
    (bad,) = check_provenance(brief).unresolved
    assert "does not appear in the record" in bad.describe()
    assert "verbatim" in bad.describe()


def test_a_long_quote_is_truncated_in_the_message(request_: DecisionRequest) -> None:
    brief = _brief(request_, claims=(_claim("CL-1", _cite("EV-1", "z" * 200)),))
    (bad,) = check_provenance(brief).unresolved
    assert "..." in bad.describe()
    assert len(bad.describe()) < 200


def test_validity_is_a_fraction_not_a_verdict(request_: DecisionRequest) -> None:
    brief = _brief(
        request_,
        claims=(_claim("CL-1", _cite()), _claim("CL-2", _cite("EV-1", "absent"))),
    )
    assert check_provenance(brief).validity == 0.5


def test_citing_nothing_is_not_perfect_validity(request_: DecisionRequest) -> None:
    """A brief that never cited anything did not earn a 1.0."""
    assert check_provenance(_brief(request_)).validity is None


# --------------------------------------------------------------------------- #
# Grounding, which is a separate question
# --------------------------------------------------------------------------- #


def test_a_claim_with_no_citations_is_ungrounded_not_unresolvable(
    request_: DecisionRequest,
) -> None:
    """It never tried to show its work; that is a different failure."""
    brief = _brief(request_, claims=(_claim("CL-1"),))
    report = check_provenance(brief)
    assert report.is_clean
    assert [c.id for c in report.ungrounded_claims] == ["CL-1"]


def test_ungrounded_recommendation_claims_are_collected_too(
    request_: DecisionRequest,
) -> None:
    brief = _brief(
        request_,
        recommendation=Recommendation(
            statement="Do it.",
            option_kind=OptionKind.AI_ASSISTED,
            claims=(_claim("CL-R"),),
        ),
    )
    assert [c.id for c in check_provenance(brief).ungrounded_claims] == ["CL-R"]


def test_evidence_nobody_cited_is_reported(request_: DecisionRequest) -> None:
    brief = _brief(
        request_,
        evidence=(_record("EV-1", QUOTE), _record("EV-2", OTHER)),
        claims=(_claim("CL-1", _cite()),),
    )
    assert check_provenance(brief).uncited_evidence_ids == ("EV-2",)

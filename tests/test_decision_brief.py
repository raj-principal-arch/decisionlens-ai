"""Deterministic completeness rules on DecisionBrief.

These are the checks Phase 8 validation turns into ValidationIssues. Each one is
computable without a model call, which is the point: the guarantees DecisionLens
makes about its own output are testable rather than promised.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
    OptionKind,
    PriorityException,
    PriorityExceptionKind,
    Recommendation,
    RunStage,
    RunTrace,
    SupportLevel,
    ValidationIssue,
    ValidationSeverity,
)

from .conftest import GENERATED_AT, QUOTE


def _brief(request_: DecisionRequest, **overrides: object) -> DecisionBrief:
    base: dict[str, object] = {
        "id": "DB-001",
        "request": request_,
        "generated_at": GENERATED_AT,
    }
    return DecisionBrief(**{**base, **overrides})


class TestMandatoryAlternatives:
    def test_ai_only_brief_fails_both_rules(self, request_: DecisionRequest) -> None:
        brief = _brief(
            request_,
            alternatives=(
                Alternative(id="A1", name="AI triage", kind=OptionKind.AI_ASSISTED),
                Alternative(id="A2", name="Full automation", kind=OptionKind.AI_AUTOMATED),
            ),
        )
        assert not brief.has_non_ai_alternative
        assert not brief.has_no_build_alternative

    def test_process_change_satisfies_the_non_ai_rule_only(self, request_: DecisionRequest) -> None:
        brief = _brief(
            request_,
            alternatives=(
                Alternative(id="A1", name="AI triage", kind=OptionKind.AI_ASSISTED),
                Alternative(id="A2", name="Simplify driver flow", kind=OptionKind.PROCESS_CHANGE),
            ),
        )
        assert brief.has_non_ai_alternative
        assert not brief.has_no_build_alternative

    def test_defer_satisfies_both(self, request_: DecisionRequest) -> None:
        brief = _brief(
            request_,
            alternatives=(
                Alternative(id="A1", name="AI triage", kind=OptionKind.AI_ASSISTED),
                Alternative(id="A2", name="Defer to next quarter", kind=OptionKind.DEFER),
            ),
        )
        assert brief.has_non_ai_alternative
        assert brief.has_no_build_alternative


class TestCitationResolution:
    def test_valid_citation_resolves(
        self, request_: DecisionRequest, evidence: EvidenceRecord, claim: Claim
    ) -> None:
        brief = _brief(request_, evidence=(evidence,), claims=(claim,))
        assert brief.unresolvable_citations == ()

    def test_citation_to_missing_evidence_is_caught(
        self, request_: DecisionRequest, evidence: EvidenceRecord
    ) -> None:
        ghost = Claim(
            id="CL-X",
            statement="Weather causes most exceptions.",
            claim_type=ClaimType.FACT,
            citations=(Citation(evidence_id="EV-9999", quote=QUOTE),),
        )
        brief = _brief(request_, evidence=(evidence,), claims=(ghost,))
        assert len(brief.unresolvable_citations) == 1

    def test_fabricated_quote_is_caught(
        self, request_: DecisionRequest, evidence: EvidenceRecord
    ) -> None:
        # The failure this product exists to prevent: a real evidence id carrying
        # a quote that does not appear in the source.
        fabricated = Claim(
            id="CL-Y",
            statement="Weather causes most exceptions.",
            claim_type=ClaimType.FACT,
            citations=(Citation(evidence_id="EV-0001", quote="Weather causes 80% of exceptions."),),
        )
        brief = _brief(request_, evidence=(evidence,), claims=(fabricated,))
        assert len(brief.unresolvable_citations) == 1

    def test_citations_are_collected_from_every_section(
        self, request_: DecisionRequest, evidence: EvidenceRecord, claim: Claim
    ) -> None:
        cite = claim.citations[0]
        other = Citation(evidence_id="EV-0001", quote="Remaining causes are varied.")
        brief = _brief(
            request_,
            evidence=(evidence,),
            claims=(claim,),
            contradictions=(
                Contradiction(
                    id="CT-1",
                    topic="exception drivers",
                    kind=ContradictionKind.CLAIM_CONFLICT,
                    side_a=cite,
                    side_b=other,
                ),
            ),
            priority_exceptions=(
                PriorityException(
                    id="PX-1",
                    kind=PriorityExceptionKind.COMPLIANCE,
                    obligation="Retain delivery photos for 90 days.",
                    citations=(cite,),
                ),
            ),
            alternatives=(
                Alternative(
                    id="A1",
                    name="Address validation",
                    kind=OptionKind.DATA_QUALITY,
                    supporting=(cite,),
                ),
            ),
            recommendation=Recommendation(
                statement="Validate addresses at order time.",
                option_kind=OptionKind.DATA_QUALITY,
                claims=(claim,),
            ),
        )
        # claim + 2 contradiction sides + exception + alternative + recommendation claim
        assert len(brief.all_citations()) == 6
        assert brief.cited_evidence_ids() == {"EV-0001"}
        assert brief.unresolvable_citations == ()

    def test_dimension_assessment_citations_are_checked(
        self, request_: DecisionRequest, evidence: EvidenceRecord
    ) -> None:
        # An assessment is where a per-dimension claim about an option lives, so
        # its citations must face the same check as any other. A fabricated quote
        # here would otherwise reach a reader inside a comparison table.
        good = DimensionAssessment(
            dimension=Dimension.CUSTOMER_REACH,
            state=AssessmentState.ASSESSED,
            summary="Affects the largest single exception category.",
            citations=(Citation(evidence_id="EV-0001", quote=QUOTE),),
        )
        bad = DimensionAssessment(
            dimension=Dimension.FINANCIAL_IMPACT,
            state=AssessmentState.ASSESSED,
            summary="Saves millions.",
            citations=(Citation(evidence_id="EV-0001", quote="Saves $4M annually."),),
        )
        brief = _brief(
            request_,
            evidence=(evidence,),
            alternatives=(
                Alternative(
                    id="A1",
                    name="Address validation",
                    kind=OptionKind.DATA_QUALITY,
                    assessments=(good, bad),
                ),
            ),
        )
        assert len(brief.all_citations()) == 2
        unresolvable = brief.unresolvable_citations
        assert len(unresolvable) == 1
        assert unresolvable[0].quote == "Saves $4M annually."


class TestCitationRendering:
    def test_citation_renders_as_a_bracketed_reference(self, claim: Claim) -> None:
        # The form a reader sees inline in a rendered brief.
        assert str(claim.citations[0]) == "[EV-0001]"


class TestEvidenceUsage:
    def test_unused_evidence_is_surfaced(
        self, request_: DecisionRequest, evidence: EvidenceRecord
    ) -> None:
        brief = _brief(request_, evidence=(evidence,))
        assert [e.id for e in brief.uncited_evidence()] == ["EV-0001"]

    def test_cited_evidence_is_not_reported_as_unused(
        self, request_: DecisionRequest, evidence: EvidenceRecord, claim: Claim
    ) -> None:
        brief = _brief(request_, evidence=(evidence,), claims=(claim,))
        assert brief.uncited_evidence() == ()


class TestClaimGrouping:
    def test_claims_are_filterable_by_type(self, request_: DecisionRequest, claim: Claim) -> None:
        opinion = Claim(
            id="CL-2",
            statement="The VP wants the AI assistant.",
            claim_type=ClaimType.STAKEHOLDER_OPINION,
        )
        constraint = Claim(
            id="CL-3",
            statement="The driver app cannot change before Q3.",
            claim_type=ClaimType.TECHNICAL_CONSTRAINT,
        )
        brief = _brief(request_, claims=(claim, opinion, constraint))
        assert brief.claims_of_type(ClaimType.FACT) == (claim,)
        assert brief.claims_of_type(ClaimType.STAKEHOLDER_OPINION) == (opinion,)
        assert brief.constraints == (constraint,)


class TestValidationAndTrace:
    def test_error_blocks_presentation_and_warning_does_not(
        self, request_: DecisionRequest
    ) -> None:
        warned = _brief(
            request_,
            validation_issues=(
                ValidationIssue(
                    code="STALE_SOURCE",
                    severity=ValidationSeverity.WARNING,
                    message="18 months old",
                ),
            ),
        )
        blocked = _brief(
            request_,
            validation_issues=(
                ValidationIssue(
                    code="UNRESOLVED_CITATION",
                    severity=ValidationSeverity.ERROR,
                    message="quote not found in source",
                ),
            ),
        )
        assert not warned.has_blocking_issues
        assert blocked.has_blocking_issues

    def test_trace_reports_failures_and_total_latency(self, request_: DecisionRequest) -> None:
        trace = RunTrace(
            run_id="RUN-1",
            request_id=request_.id,
            stages=(
                RunStage(name="retrieve", latency_ms=120),
                RunStage(name="classify", latency_ms=300),
                RunStage(name="contradictions", latency_ms=80, error="provider timeout"),
            ),
        )
        brief = _brief(request_, run_trace=trace)
        assert brief.run_trace is not None
        assert brief.run_trace.total_latency_ms == 500
        assert [s.name for s in brief.run_trace.failed_stages] == ["contradictions"]


class TestBriefInvariants:
    def test_owner_notice_is_present_by_default(self, brief: DecisionBrief) -> None:
        assert "product manager remains accountable" in brief.decision_owner_notice

    def test_recommendation_reports_its_ungrounded_claims(self) -> None:
        recommendation = Recommendation(
            statement="Prioritize address validation.",
            option_kind=OptionKind.DATA_QUALITY,
            claims=(Claim(id="CL-4", statement="It will work.", claim_type=ClaimType.ASSUMPTION),),
            support_level=SupportLevel.LOW,
        )
        assert len(recommendation.ungrounded_claims) == 1

    def test_contradiction_needs_two_distinct_sides(self, claim: Claim) -> None:
        with pytest.raises(ValidationError, match="two distinct sides"):
            Contradiction(
                id="CT-2",
                topic="same thing twice",
                kind=ContradictionKind.METRIC_CONFLICT,
                side_a=claim.citations[0],
                side_b=claim.citations[0],
            )

    def test_brief_round_trips_through_json(self, brief: DecisionBrief) -> None:
        restored = DecisionBrief.model_validate_json(brief.model_dump_json())
        assert restored == brief

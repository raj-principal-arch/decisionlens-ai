"""Model validation, invalid input, required metadata, and serialization."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from decision_lens.models import (
    AssessmentState,
    Citation,
    Claim,
    ClaimType,
    DecisionCriteria,
    DecisionRequest,
    Dimension,
    DimensionAssessment,
    DimensionCriterion,
    EvidenceRecord,
    EvidenceType,
    ExperimentPlan,
    Metric,
    MetricRole,
    OptionKind,
    PMDecision,
    SourceSystem,
    SupportLevel,
    UserContext,
)

from .conftest import CONTENT, QUOTE


class TestEvidenceRecord:
    def test_preserves_required_metadata(self, evidence: EvidenceRecord) -> None:
        assert evidence.source_system is SourceSystem.LOCAL_FILE
        assert evidence.source_id
        assert evidence.source_reference
        assert evidence.created_at and evidence.updated_at
        assert evidence.owner and evidence.retrieved_at and evidence.product_area

    def test_blank_content_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="nothing to cite"):
            EvidenceRecord(
                id="EV-1",
                source_system=SourceSystem.LOCAL_FILE,
                source_id="f.md",
                content="   ",
                evidence_type=EvidenceType.OPERATIONAL_RECORD,
            )

    def test_empty_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRecord(
                id="",
                source_system=SourceSystem.LOCAL_FILE,
                source_id="f.md",
                content="x",
                evidence_type=EvidenceType.OPERATIONAL_RECORD,
            )

    def test_unknown_field_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRecord(
                id="EV-1",
                source_system=SourceSystem.LOCAL_FILE,
                source_id="f.md",
                content="x",
                evidence_type=EvidenceType.OPERATIONAL_RECORD,
                confidence=0.9,  # type: ignore[call-arg]
            )

    def test_contains_backs_citation_checking(self, evidence: EvidenceRecord) -> None:
        assert evidence.contains(QUOTE)
        assert not evidence.contains("Weather is the largest driver.")

    def test_age_uses_updated_date_when_present(self, evidence: EvidenceRecord) -> None:
        assert evidence.age_days(date(2026, 6, 11)) == 10

    def test_age_is_none_without_dates(self) -> None:
        record = EvidenceRecord(
            id="EV-2",
            source_system=SourceSystem.LOCAL_FILE,
            source_id="f.md",
            content="x",
            evidence_type=EvidenceType.OPERATIONAL_RECORD,
        )
        assert record.age_days(date(2026, 6, 11)) is None

    def test_is_immutable(self, evidence: EvidenceRecord) -> None:
        with pytest.raises(ValidationError):
            evidence.content = "rewritten"  # type: ignore[misc]

    def test_round_trips_through_json(self, evidence: EvidenceRecord) -> None:
        restored = EvidenceRecord.model_validate_json(evidence.model_dump_json())
        assert restored == evidence
        assert restored.content == CONTENT


class TestDecisionRequest:
    def test_solution_shaped_statement_is_rejected(self, user: UserContext) -> None:
        with pytest.raises(ValidationError, match="phrased as a question"):
            DecisionRequest(
                id="DR-2",
                question="Build an AI assistant for delivery exceptions.",
                user=user,
            )

    def test_criteria_default_to_all_nine_dimensions(self) -> None:
        criteria = DecisionCriteria()
        assert len(criteria.dimensions) == len(Dimension) == 9
        assert set(criteria.applicable) == set(Dimension)

    def test_inapplicable_dimensions_are_excluded(self) -> None:
        criteria = DecisionCriteria(
            dimensions=(
                DimensionCriterion(dimension=Dimension.RISK),
                DimensionCriterion(dimension=Dimension.SPEND, applies=False),
            )
        )
        assert criteria.applicable == (Dimension.RISK,)

    def test_mandatory_alternative_requirements_default_on(self) -> None:
        criteria = DecisionCriteria()
        assert criteria.require_non_ai_alternative
        assert criteria.require_no_build_alternative


class TestClaimTypes:
    def test_reclassifying_preserves_identity_and_citations(self, claim: Claim) -> None:
        # The behaviour that justified one Claim model over four classes: the
        # challenger relabels a claim without rebuilding it.
        relabelled = claim.reclassified(ClaimType.STAKEHOLDER_OPINION, "VP preference")
        assert relabelled.claim_type is ClaimType.STAKEHOLDER_OPINION
        assert relabelled.id == claim.id
        assert relabelled.citations == claim.citations
        assert claim.claim_type is ClaimType.FACT  # original untouched

    @pytest.mark.parametrize(
        ("claim_type", "expected"),
        [
            (ClaimType.TECHNICAL_CONSTRAINT, True),
            (ClaimType.BUSINESS_CONSTRAINT, True),
            (ClaimType.GOVERNANCE_CONSTRAINT, True),
            (ClaimType.FACT, False),
            (ClaimType.ASSUMPTION, False),
            (ClaimType.STAKEHOLDER_OPINION, False),
        ],
    )
    def test_constraint_grouping(self, claim_type: ClaimType, expected: bool) -> None:
        assert claim_type.is_constraint is expected

    def test_only_fact_counts_as_evidence(self) -> None:
        assert ClaimType.FACT.is_evidence
        assert not ClaimType.STAKEHOLDER_OPINION.is_evidence
        assert not ClaimType.ASSUMPTION.is_evidence

    def test_ungrounded_claim_is_representable_but_flagged(self) -> None:
        floating = Claim(id="CL-9", statement="PMs love AI.", claim_type=ClaimType.ASSUMPTION)
        assert not floating.is_grounded

    def test_contested_claim_is_detected(self, citation: Citation) -> None:
        contested = Claim(
            id="CL-3",
            statement="Notifications reduce exceptions.",
            claim_type=ClaimType.FACT,
            citations=(citation,),
            opposing_citations=(Citation(evidence_id="EV-0002", quote="No measurable effect."),),
        )
        assert contested.is_contested


class TestOptionKind:
    def test_ai_kinds(self) -> None:
        assert OptionKind.AI_ASSISTED.is_ai and OptionKind.AI_AUTOMATED.is_ai
        assert not OptionKind.PROCESS_CHANGE.is_ai
        assert not OptionKind.RULES_BASED_AUTOMATION.is_ai

    def test_no_build_kinds(self) -> None:
        assert OptionKind.NO_CHANGE.is_no_build
        assert OptionKind.DEFER.is_no_build
        assert OptionKind.FURTHER_RESEARCH.is_no_build
        assert not OptionKind.BUY.is_no_build


class TestDimensionAssessment:
    def test_assessed_without_citations_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cites nothing"):
            DimensionAssessment(
                dimension=Dimension.FINANCIAL_IMPACT,
                state=AssessmentState.ASSESSED,
                summary="Large upside.",
            )

    def test_cannot_assess_requires_saying_what_is_missing(self) -> None:
        with pytest.raises(ValidationError, match="what is missing"):
            DimensionAssessment(
                dimension=Dimension.RISK,
                state=AssessmentState.CANNOT_ASSESS,
            )

    def test_cannot_assess_is_valid_with_an_explanation(self) -> None:
        assessment = DimensionAssessment(
            dimension=Dimension.PRODUCT_USAGE,
            state=AssessmentState.CANNOT_ASSESS,
            summary="No usage data exists; the capability has not shipped.",
        )
        assert assessment.state is AssessmentState.CANNOT_ASSESS
        assert not assessment.citations


class TestMetricsAndExperiment:
    def test_roles_split_without_separate_types(self) -> None:
        plan = ExperimentPlan(
            id="EX-1",
            hypothesis="Pre-arrival notifications reduce failed first attempts.",
            metrics=(
                Metric(name="First-attempt success rate", role=MetricRole.SUCCESS),
                Metric(name="Support contact rate", role=MetricRole.GUARDRAIL),
                Metric(name="Driver time per stop", role=MetricRole.GUARDRAIL),
            ),
        )
        assert len(plan.success_metrics) == 1
        assert len(plan.guardrail_metrics) == 2


class TestPMDecision:
    def test_disagreement_requires_a_reason(self) -> None:
        with pytest.raises(ValidationError, match="override_reason"):
            PMDecision(
                brief_id="DB-001",
                decided_by="pm-001",
                decided_at=datetime(2026, 8, 2, 12, 0),
                decision="Prioritize address validation.",
                agreed_with_recommendation=False,
            )

    def test_disagreement_with_a_reason_is_accepted(self) -> None:
        decision = PMDecision(
            brief_id="DB-001",
            decided_by="pm-001",
            decided_at=datetime(2026, 8, 2, 12, 0),
            decision="Prioritize address validation.",
            agreed_with_recommendation=False,
            override_reason="Contractual deadline not reflected in the evidence.",
        )
        assert decision.override_reason

    def test_agreement_needs_no_reason(self) -> None:
        decision = PMDecision(
            brief_id="DB-001",
            decided_by="pm-001",
            decided_at=datetime(2026, 8, 2, 12, 0),
            decision="Adopt the recommendation.",
            agreed_with_recommendation=True,
        )
        assert decision.agreed_with_recommendation is True


class TestSupportLevel:
    def test_values_are_qualitative_not_numeric(self) -> None:
        # Guards the design intent: support is never a probability.
        assert [level.value for level in SupportLevel] == ["low", "moderate", "strong"]

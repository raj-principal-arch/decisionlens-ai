"""Analysis-layer models: gaps, classifications, excerpts, tradeoffs, horizons.

These types carry design intent that is easy to lose in a refactor, so the tests
assert the intent rather than the field list.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from decision_lens.models import (
    Alternative,
    AssessmentState,
    Citation,
    DecisionCriteria,
    Dimension,
    DimensionAssessment,
    DimensionCriterion,
    EvidenceClassification,
    EvidenceExcerpt,
    EvidenceRecord,
    EvidenceType,
    GapImpact,
    Horizon,
    MissingEvidence,
    OptionKind,
    SourceSystem,
    SupportLevel,
    Tradeoff,
)

from .conftest import QUOTE


class TestMissingEvidence:
    """Missing-evidence detection is one of the six mechanisms the hypothesis names."""

    def test_searched_and_never_covered_are_different_signals(self) -> None:
        # The distinction that makes a gap actionable: "we looked and found
        # nothing" is a finding; "no connector covers this" is a scope limit.
        searched = MissingEvidence(
            id="MG-1",
            question="Did the notification pilot change first-attempt success?",
            impact=GapImpact.WOULD_CHANGE_RECOMMENDATION,
            why_it_matters="The recommendation rests on an unmeasured effect.",
            was_searched=True,
        )
        uncovered = MissingEvidence(
            id="MG-2",
            question="What do drivers say about the exception workflow?",
            impact=GapImpact.WOULD_REFINE_SCOPE,
            why_it_matters="No driver feedback source is connected.",
            was_searched=False,
        )
        assert searched.was_searched
        assert not uncovered.was_searched

    def test_defaults_to_searched(self) -> None:
        gap = MissingEvidence(
            id="MG-3", question="Anything?", impact=GapImpact.WOULD_CHANGE_SUPPORT_LEVEL
        )
        assert gap.was_searched is True

    @pytest.mark.parametrize("impact", list(GapImpact))
    def test_every_impact_level_is_usable(self, impact: GapImpact) -> None:
        gap = MissingEvidence(id="MG-4", question="What is missing?", impact=impact)
        assert gap.impact is impact

    def test_impact_levels_are_decision_relative(self) -> None:
        # Named by what the gap costs the decision, not by an abstract severity.
        assert {i.value for i in GapImpact} == {
            "would_change_recommendation",
            "would_change_support_level",
            "would_refine_scope",
        }

    def test_a_gap_needs_a_question(self) -> None:
        with pytest.raises(ValidationError):
            MissingEvidence(id="MG-5", question="", impact=GapImpact.WOULD_REFINE_SCOPE)


class TestEvidenceClassification:
    """Judgment about a record, kept separate from the record itself."""

    def test_classification_references_a_record_rather_than_embedding_it(self) -> None:
        classification = EvidenceClassification(
            evidence_id="EV-0001",
            evidence_type=EvidenceType.OPERATIONAL_RECORD,
            support_level=SupportLevel.MODERATE,
            rationale="Single quarter of tickets; no comparison period.",
        )
        assert classification.evidence_id == "EV-0001"

    def test_a_record_carries_no_support_level(self, evidence: EvidenceRecord) -> None:
        # The separation that stops an interpretation passing as a fact of the
        # record. Retrieval says what a document is; only a skill says what it is
        # worth, and it must do so in a different object.
        assert not hasattr(evidence, "support_level")
        assert not hasattr(evidence, "rationale")
        with pytest.raises(ValidationError):
            EvidenceRecord(
                id="EV-9",
                source_system=SourceSystem.LOCAL_FILE,
                source_id="f.md",
                content="x",
                evidence_type=EvidenceType.OPERATIONAL_RECORD,
                support_level=SupportLevel.STRONG,  # type: ignore[call-arg]
            )

    def test_staleness_is_recorded_with_its_age(self) -> None:
        classification = EvidenceClassification(
            evidence_id="EV-0002",
            evidence_type=EvidenceType.QUALITATIVE_RESEARCH,
            support_level=SupportLevel.LOW,
            is_stale=True,
            age_days=548,
        )
        assert classification.is_stale and classification.age_days == 548

    def test_not_stale_by_default(self) -> None:
        classification = EvidenceClassification(
            evidence_id="EV-0003",
            evidence_type=EvidenceType.QUANTITATIVE_METRIC,
            support_level=SupportLevel.STRONG,
        )
        assert not classification.is_stale
        assert classification.age_days is None


class TestEvidenceExcerpt:
    def test_excerpt_carries_verbatim_text_and_a_locator(self) -> None:
        excerpt = EvidenceExcerpt(text=QUOTE, locator="L2")
        assert excerpt.text == QUOTE
        assert excerpt.locator == "L2"

    def test_empty_excerpt_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceExcerpt(text="", locator="L2")

    def test_excerpts_attach_to_a_record_and_resolve_against_it(self) -> None:
        record = EvidenceRecord(
            id="EV-0004",
            source_system=SourceSystem.LOCAL_FILE,
            source_id="notes.md",
            content=f"Header\n{QUOTE}\nFooter",
            evidence_type=EvidenceType.OPERATIONAL_RECORD,
            excerpts=(EvidenceExcerpt(text=QUOTE, locator="L2"),),
            created_at=date(2026, 5, 1),
        )
        assert len(record.excerpts) == 1
        assert record.contains(record.excerpts[0].text)


class TestTradeoff:
    def test_a_tradeoff_names_both_sides_and_links_to_options(self) -> None:
        tradeoff = Tradeoff(
            id="TO-1",
            description="Address validation delays checkout slightly.",
            gains=("Fewer failed first attempts", "Lower support contact rate"),
            gives_up=("A small increase in checkout friction",),
            alternative_ids=("A1", "A2"),
        )
        assert tradeoff.gains and tradeoff.gives_up
        assert tradeoff.alternative_ids == ("A1", "A2")

    def test_a_tradeoff_needs_a_description(self) -> None:
        with pytest.raises(ValidationError):
            Tradeoff(id="TO-2", description="")


class TestHorizon:
    def test_all_three_horizons_exist(self) -> None:
        assert {h.value for h in Horizon} == {"core", "adjacent", "innovation"}

    def test_alternatives_can_be_placed_on_a_horizon(self) -> None:
        core = Alternative(
            id="A1",
            name="Address validation at order time",
            kind=OptionKind.DATA_QUALITY,
            horizon=Horizon.CORE,
        )
        innovation = Alternative(
            id="A2",
            name="Autonomous delivery pilot",
            kind=OptionKind.AI_AUTOMATED,
            horizon=Horizon.INNOVATION,
        )
        assert core.horizon is Horizon.CORE
        assert innovation.horizon is Horizon.INNOVATION

    def test_horizon_is_optional(self) -> None:
        alt = Alternative(id="A3", name="Defer", kind=OptionKind.DEFER)
        assert alt.horizon is None

    def test_an_innovation_bet_may_be_largely_unassessable(self) -> None:
        # The argument in docs/01: an innovation option competes on dimensions
        # where the justifying evidence does not exist yet. That must be
        # representable and visible, not silently scored as low value.
        innovation = Alternative(
            id="A4",
            name="Autonomous delivery pilot",
            kind=OptionKind.AI_AUTOMATED,
            horizon=Horizon.INNOVATION,
            assessments=(
                DimensionAssessment(
                    dimension=Dimension.PRODUCT_USAGE,
                    state=AssessmentState.CANNOT_ASSESS,
                    summary="The capability has not shipped; no usage exists.",
                ),
                DimensionAssessment(
                    dimension=Dimension.FINANCIAL_IMPACT,
                    state=AssessmentState.CANNOT_ASSESS,
                    summary="No pilot has run; revenue effect is unmeasured.",
                ),
                DimensionAssessment(
                    dimension=Dimension.DELIVERY_EFFORT,
                    state=AssessmentState.ASSESSED,
                    summary="Two quarters of engineering, per the constraints note.",
                    citations=(Citation(evidence_id="EV-0001", quote=QUOTE),),
                ),
            ),
        )
        unassessed = innovation.unassessed_dimensions
        assert set(unassessed) == {Dimension.PRODUCT_USAGE, Dimension.FINANCIAL_IMPACT}
        assert len(unassessed) == 2  # surfaced, not silently treated as zero


class TestDecisionCriteriaDefaults:
    def test_omitting_dimensions_yields_all_nine(self) -> None:
        assert len(DecisionCriteria().dimensions) == 9

    def test_explicitly_empty_dimensions_are_rejected(self) -> None:
        # Silently substituting all nine would hide a caller mistake.
        with pytest.raises(ValidationError, match="at least one dimension"):
            DecisionCriteria(dimensions=())

    def test_defaults_are_not_shared_between_instances(self) -> None:
        a, b = DecisionCriteria(), DecisionCriteria()
        assert a.dimensions == b.dimensions
        assert a == b

    def test_criteria_remain_immutable(self) -> None:
        criteria = DecisionCriteria()
        with pytest.raises(ValidationError):
            criteria.notes = "changed"  # type: ignore[misc]

    def test_a_subset_is_preserved_exactly(self) -> None:
        criteria = DecisionCriteria(
            dimensions=(DimensionCriterion(dimension=Dimension.RISK, note="regulatory exposure"),)
        )
        assert len(criteria.dimensions) == 1
        assert criteria.dimensions[0].note == "regulatory exposure"

"""Scoring a brief against an answer key.

Every number the evaluation reports comes through here, so the tests are shaped
around the ways a scorer can be quietly wrong rather than loudly broken: a
recall figure whose denominator drifted, a false positive counted as an error
when the rules say it must be adjudicated, a restraint check that never fires.

The matching rules were fixed in each case's `scoring_rules` before results
existed. These tests hold the implementation to them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from decision_lens.evaluation.ground_truth import GroundTruth, SpanRef
from decision_lens.evaluation.metrics import RecordIndex, score_brief
from decision_lens.models import (
    Alternative,
    Citation,
    Claim,
    ClaimType,
    Contradiction,
    ContradictionKind,
    DecisionBrief,
    DecisionRequest,
    EvidenceRecord,
    EvidenceType,
    OptionKind,
    Recommendation,
    SourceSystem,
    SupportLevel,
    UserContext,
)

CLOCK = datetime(2026, 8, 3, tzinfo=UTC).replace(tzinfo=None)


def _record(rid: str, source: str, content: str) -> EvidenceRecord:
    return EvidenceRecord(
        id=rid,
        source_system=SourceSystem.LOCAL_FILE,
        source_id=source,
        source_reference=f"{source}#1",
        title=source,
        content=content,
        evidence_type=EvidenceType.QUANTITATIVE_METRIC,
        retrieved_at=CLOCK,
    )


RECORDS = (
    _record("EV-1", "metrics.csv", "first_attempt_success: 87.4 percent"),
    _record("EV-2", "objectives.md", "First-attempt success is currently 91%."),
    _record("EV-3", "notes.md", "An unrelated remark about staffing."),
)


def _truth(**overrides: object) -> GroundTruth:
    payload: dict[str, object] = {
        "case_id": "c",
        "version": "1.0",
        "synthetic": True,
        "notice": "synthetic and fictional",
        "authoring_limitation": "same author as the corpus",
        "question": "q",
        "desired_outcome": "o",
        "scoring_rules": {
            "recall_denominator": "must_detect only",
            "unplanted_findings": "adjudicated",
            "span_matching": "same record",
            "restraint_scoring": "overstating fails",
            "forbidden_claims": "checked independently",
        },
        "expected_contradictions": [
            {
                "id": "C1",
                "kind": "temporal_conflict",
                "topic": "success rate",
                "side_a": {"source": "metrics.csv", "span": "first_attempt_success: 87.4"},
                "side_b": {"source": "objectives.md", "span": "currently 91%"},
                "why_it_matters": "w",
                "how_to_resolve": "r",
            }
        ],
        "expected_alternative_categories": {},
        "recommendation_restraint": {
            "max_defensible_support_level": "moderate",
            "reason": "thin",
        },
    }
    payload.update(overrides)
    return GroundTruth.model_validate(payload)


def _brief(**overrides: object) -> DecisionBrief:
    payload: dict[str, object] = {
        "id": "DB-1",
        "request": DecisionRequest(
            id="DR-1",
            question="Which intervention should the team prioritise?",
            user=UserContext(user_id="pm"),
        ),
        "generated_at": CLOCK,
        "evidence": RECORDS,
    }
    payload.update(overrides)
    return DecisionBrief.model_validate(payload)


def _conflict(a: str, b: str) -> Contradiction:
    return Contradiction(
        id="X",
        topic="t",
        kind=ContradictionKind.TEMPORAL_CONFLICT,
        side_a=Citation(evidence_id=a, quote="q"),
        side_b=Citation(evidence_id=b, quote="q"),
        summary="s",
        how_to_resolve="r",
    )


class TestRecordIndex:
    def test_a_span_resolves_to_the_record_holding_it(self) -> None:
        index = RecordIndex(RECORDS)
        ref = SpanRef(source="metrics.csv", span="first_attempt_success: 87.4")
        assert index.resolve(ref) == "EV-1"

    def test_typography_does_not_prevent_resolution(self) -> None:
        index = RecordIndex(RECORDS)
        assert (
            index.resolve(SpanRef(source="objectives.md", span="First attempt success")) == "EV-2"
        )

    def test_a_span_from_an_unknown_file_resolves_to_nothing(self) -> None:
        index = RecordIndex(RECORDS)
        assert index.resolve(SpanRef(source="nope.md", span="anything")) is None

    def test_a_span_present_in_no_record_resolves_to_nothing(self) -> None:
        index = RecordIndex(RECORDS)
        assert index.resolve(SpanRef(source="metrics.csv", span="never written")) is None

    def test_an_ambiguous_span_resolves_to_nothing_rather_than_a_guess(self) -> None:
        """Two records, one file, same text. Choosing would decide recall on a coin toss."""
        twins = (
            _record("EV-A", "rows.csv", "status: open"),
            _record("EV-B", "rows.csv", "status: open"),
        )
        assert RecordIndex(twins).resolve(SpanRef(source="rows.csv", span="status: open")) is None


class TestContradictionRecall:
    def test_a_planted_conflict_counts_when_both_records_are_cited(self) -> None:
        score = score_brief(_brief(contradictions=(_conflict("EV-1", "EV-2"),)), _truth(), RECORDS)
        assert score.contradictions.found == ("C1",)
        assert score.contradictions.recall == 1.0

    def test_citing_only_one_side_does_not_count(self) -> None:
        score = score_brief(_brief(contradictions=(_conflict("EV-1", "EV-3"),)), _truth(), RECORDS)
        assert score.contradictions.missed == ("C1",)
        assert score.contradictions.recall == 0.0

    def test_the_order_of_the_two_sides_does_not_matter(self) -> None:
        score = score_brief(_brief(contradictions=(_conflict("EV-2", "EV-1"),)), _truth(), RECORDS)
        assert score.contradictions.found == ("C1",)

    def test_an_ungraded_entry_stays_out_of_the_denominator(self) -> None:
        truth = _truth(
            expected_contradictions=[
                {
                    "id": "C1",
                    "kind": "k",
                    "topic": "t",
                    "side_a": {"source": "metrics.csv", "span": "first_attempt_success: 87.4"},
                    "side_b": {"source": "objectives.md", "span": "currently 91%"},
                    "why_it_matters": "w",
                    "how_to_resolve": "r",
                    "must_detect": False,
                }
            ]
        )
        score = score_brief(_brief(), truth, RECORDS)
        assert score.contradictions.graded == 0
        assert score.contradictions.recall is None, "no data is not a zero"

    def test_an_unplanted_finding_is_held_for_adjudication_not_scored_wrong(self) -> None:
        """The rules forbid counting it as an error; the corpus may hold real
        conflicts its author never noticed."""
        brief = _brief(contradictions=(_conflict("EV-1", "EV-2"), _conflict("EV-1", "EV-3")))
        score = score_brief(brief, _truth(), RECORDS)
        assert score.contradictions.found == ("C1",)
        assert score.contradictions.unadjudicated == 1

    def test_a_key_entry_the_harness_cannot_locate_leaves_the_denominator(self) -> None:
        """A broken measurement is not a miss by the system under test."""
        truth = _truth(
            expected_contradictions=[
                {
                    "id": "C1",
                    "kind": "k",
                    "topic": "t",
                    "side_a": {"source": "metrics.csv", "span": "text that is not there"},
                    "side_b": {"source": "objectives.md", "span": "currently 91%"},
                    "why_it_matters": "w",
                    "how_to_resolve": "r",
                }
            ]
        )
        score = score_brief(_brief(), truth, RECORDS)
        assert score.contradictions.unresolvable == ("C1",)
        assert score.contradictions.graded == 0

    def test_one_reported_conflict_cannot_satisfy_two_planted_ones(self) -> None:
        truth = _truth(
            expected_contradictions=[
                {
                    "id": cid,
                    "kind": "k",
                    "topic": "t",
                    "side_a": {"source": "metrics.csv", "span": "first_attempt_success: 87.4"},
                    "side_b": {"source": "objectives.md", "span": "currently 91%"},
                    "why_it_matters": "w",
                    "how_to_resolve": "r",
                }
                for cid in ("C1", "C2")
            ]
        )
        score = score_brief(_brief(contradictions=(_conflict("EV-1", "EV-2"),)), truth, RECORDS)
        assert len(score.contradictions.found) == 1
        assert len(score.contradictions.missed) == 1


class TestCitations:
    def _claim(self, quote: str, evidence_id: str = "EV-1") -> Claim:
        return Claim(
            id="C-1",
            statement="s",
            claim_type=ClaimType.FACT,
            citations=(Citation(evidence_id=evidence_id, quote=quote),),
            support_level=SupportLevel.LOW,
        )

    def test_a_resolvable_citation_counts_as_valid(self) -> None:
        score = score_brief(_brief(claims=(self._claim("87.4 percent"),)), _truth(), RECORDS)
        assert score.citations_total == 1
        assert score.citation_validity == 1.0

    def test_a_quote_absent_from_its_record_is_invalid(self) -> None:
        score = score_brief(_brief(claims=(self._claim("never written"),)), _truth(), RECORDS)
        assert score.citation_validity == 0.0

    def test_a_citation_to_an_unknown_record_is_invalid(self) -> None:
        score = score_brief(
            _brief(claims=(self._claim("87.4 percent", "EV-999"),)), _truth(), RECORDS
        )
        assert score.citation_validity == 0.0

    def test_no_citations_reports_no_rate_rather_than_zero(self) -> None:
        assert score_brief(_brief(), _truth(), RECORDS).citation_validity is None

    def test_an_uncited_claim_is_counted(self) -> None:
        claim = Claim(
            id="C-1", statement="s", claim_type=ClaimType.ASSUMPTION, support_level=SupportLevel.LOW
        )
        score = score_brief(_brief(claims=(claim,)), _truth(), RECORDS)
        assert score.claims_total == 1
        assert score.claims_uncited == 1

    def test_alternative_citations_are_checked_too(self) -> None:
        option = Alternative(
            id="OPT-1",
            name="n",
            kind=OptionKind.PROCESS_CHANGE,
            description="d",
            supporting=(Citation(evidence_id="EV-1", quote="not in there"),),
        )
        score = score_brief(_brief(alternatives=(option,)), _truth(), RECORDS)
        assert score.citations_total == 1
        assert score.citation_validity == 0.0


class TestAlternativesAndRestraint:
    def _option(self, kind: OptionKind, oid: str = "OPT-1") -> Alternative:
        return Alternative(id=oid, name="n", kind=kind, description="d")

    def test_non_ai_and_no_build_come_from_the_brief_not_a_second_table(self) -> None:
        brief = _brief(
            alternatives=(
                self._option(OptionKind.PROCESS_CHANGE, "OPT-1"),
                self._option(OptionKind.DEFER, "OPT-2"),
            )
        )
        score = score_brief(brief, _truth(), RECORDS)
        assert score.alternatives == 2
        assert score.has_non_ai_option
        assert score.has_no_build_option

    def test_an_all_ai_option_set_is_reported_as_missing_both(self) -> None:
        brief = _brief(alternatives=(self._option(OptionKind.AI_ASSISTED),))
        score = score_brief(brief, _truth(), RECORDS)
        assert not score.has_non_ai_option
        assert not score.has_no_build_option

    def _recommend(self, level: SupportLevel, selected: str = "OPT-1") -> Recommendation:
        return Recommendation(
            statement="s",
            option_kind=OptionKind.PROCESS_CHANGE,
            selected_alternative_id=selected,
            support_level=level,
            support_basis="b",
            what_would_change_it=("c",),
        )

    def test_claiming_more_support_than_the_key_allows_is_a_restraint_failure(self) -> None:
        brief = _brief(
            alternatives=(self._option(OptionKind.PROCESS_CHANGE),),
            recommendation=self._recommend(SupportLevel.STRONG),
        )
        score = score_brief(brief, _truth(), RECORDS)
        assert score.support_ceiling == "moderate"
        assert score.overstates_support

    def test_claiming_the_ceiling_exactly_is_not_a_failure(self) -> None:
        brief = _brief(
            alternatives=(self._option(OptionKind.PROCESS_CHANGE),),
            recommendation=self._recommend(SupportLevel.MODERATE),
        )
        assert not score_brief(brief, _truth(), RECORDS).overstates_support

    def test_claiming_less_is_not_a_failure_here(self) -> None:
        """Under-claiming is a separate finding, not an overstatement."""
        brief = _brief(
            alternatives=(self._option(OptionKind.PROCESS_CHANGE),),
            recommendation=self._recommend(SupportLevel.LOW),
        )
        assert not score_brief(brief, _truth(), RECORDS).overstates_support

    def test_an_unknown_ceiling_never_invents_a_failure(self) -> None:
        truth = _truth(
            recommendation_restraint={"max_defensible_support_level": "unheard_of", "reason": "r"}
        )
        brief = _brief(
            alternatives=(self._option(OptionKind.PROCESS_CHANGE),),
            recommendation=self._recommend(SupportLevel.STRONG),
        )
        assert not score_brief(brief, truth, RECORDS).overstates_support

    def test_a_recommendation_selecting_an_absent_option_is_not_actionable(self) -> None:
        brief = _brief(
            alternatives=(self._option(OptionKind.PROCESS_CHANGE, "OPT-1"),),
            recommendation=self._recommend(SupportLevel.LOW, selected="OPT-99"),
        )
        score = score_brief(brief, _truth(), RECORDS)
        assert not score.recommended_option_exists
        assert not score.actionable
        assert any("OPT-99" in n for n in score.notes)

    def test_a_brief_with_no_recommendation_is_not_actionable_and_says_so(self) -> None:
        score = score_brief(_brief(), _truth(), RECORDS)
        assert not score.actionable
        assert any("no recommendation" in n for n in score.notes)


class TestValidationCounts:
    def test_blocking_errors_and_warnings_are_separated(self) -> None:
        from decision_lens.models import ValidationIssue, ValidationSeverity

        issues = (
            ValidationIssue(code="a", severity=ValidationSeverity.ERROR, message="m"),
            ValidationIssue(code="b", severity=ValidationSeverity.WARNING, message="m"),
            ValidationIssue(code="c", severity=ValidationSeverity.WARNING, message="m"),
        )
        score = score_brief(_brief(validation_issues=issues), _truth(), RECORDS)
        assert score.blocking_errors == 1
        assert score.warnings == 2

    def test_failed_stages_are_named(self) -> None:
        from decision_lens.models import RunStage, RunTrace

        trace = RunTrace(
            run_id="r",
            request_id="q",
            stages=(RunStage(name="alternatives", error="boom"), RunStage(name="relevance")),
        )
        score = score_brief(_brief(run_trace=trace), _truth(), RECORDS)
        assert score.failed_stages == ("alternatives",)

    def test_a_brief_without_a_trace_reports_no_failed_stages(self) -> None:
        assert score_brief(_brief(), _truth(), RECORDS).failed_stages == ()


@pytest.mark.parametrize(("found", "graded"), [(0, 0)])
def test_recall_of_nothing_is_none_not_zero(found: int, graded: int) -> None:
    """Reporting 0% when nothing was graded would invent a failing score."""
    from decision_lens.evaluation.metrics import RecallResult

    assert RecallResult(found=(), missed=()).recall is None

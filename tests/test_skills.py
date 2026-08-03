"""The six analysis skills.

Scenario tests run against the real synthetic corpus rather than convenient
fixtures. The executive preference, the misleading denominator and the stale
source are all planted in `data/sample_delivery_exceptions`, so a test that used
a hand-made stand-in would prove the skill works on the stand-in.

The model is always faked. What is under test is the deterministic half of each
skill — the checks that cannot be talked out of by fluent output.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from decision_lens.connectors import LocalFileEvidenceSource
from decision_lens.llm import ModelRequest, ModelResponse, ModelUnavailable, ModelUsage
from decision_lens.models import (
    Alternative,
    AssessmentState,
    Citation,
    ClaimType,
    Contradiction,
    ContradictionKind,
    DecisionRequest,
    Dimension,
    DimensionAssessment,
    EvidenceRecord,
    EvidenceRequest,
    EvidenceType,
    GapImpact,
    OptionKind,
    SourceSystem,
    SupportLevel,
    UserContext,
)
from decision_lens.skills import (
    AlternativesSkill,
    ClassificationSkill,
    ContradictionsSkill,
    MissingEvidenceSkill,
    RecommendationSkill,
    RelevanceSkill,
    SkillContext,
    SkillError,
    SkillViolation,
)

CASE_DIR = Path("data/sample_delivery_exceptions")
AS_OF = date(2026, 8, 2)


class FakeProvider:
    """Returns scripted JSON. Reaches nothing."""

    def __init__(self, *texts: str, fail_with: Exception | None = None) -> None:
        self._texts = list(texts)
        self._fail_with = fail_with
        self.requests: list[ModelRequest] = []

    provider_id = "fake"
    model_id = "fake-1"

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self._fail_with is not None:
            raise self._fail_with
        text = self._texts.pop(0) if self._texts else "{}"
        return ModelResponse(
            text=text,
            provider=self.provider_id,
            model=self.model_id,
            prompt_version=request.prompt_version,
            skill=request.skill,
            latency_ms=10,
            usage=ModelUsage(input_tokens=100, output_tokens=50),
            is_cached=False,
        )


def _record(rid: str, content: str, **kw: Any) -> EvidenceRecord:
    return EvidenceRecord(
        id=rid,
        source_system=SourceSystem.LOCAL_FILE,
        source_id=kw.pop("source_id", f"{rid}.md"),
        content=content,
        evidence_type=kw.pop("evidence_type", EvidenceType.OPERATIONAL_RECORD),
        **kw,
    )


def _context(*records: EvidenceRecord) -> SkillContext:
    return SkillContext(
        request=DecisionRequest(
            id="case-1",
            question="Which intervention should the team prioritize?",
            desired_outcome="Fewer failed deliveries.",
            user=UserContext(user_id="pm-1"),
        ),
        evidence=records,
    )


@pytest.fixture(scope="module")
def real_context() -> SkillContext:
    records = LocalFileEvidenceSource(CASE_DIR).retrieve(
        EvidenceRequest(query="", requested_by=UserContext(user_id="pm-1"), max_records=500)
    )
    return SkillContext(
        request=DecisionRequest(
            id="sample_delivery_exceptions",
            question=(
                "Which intervention should the team prioritize to reduce delivery exceptions?"
            ),
            desired_outcome="Improve first-attempt delivery success.",
            user=UserContext(user_id="pm-1", product_area="delivery"),
        ),
        evidence=tuple(records),
    )


def _find(context: SkillContext, needle: str) -> EvidenceRecord:
    return next(r for r in context.evidence if needle in r.content)


# --------------------------------------------------------------------------- #
# The shared contract
# --------------------------------------------------------------------------- #


class TestSkillContract:
    def test_a_skill_cannot_reach_evidence_it_was_not_given(self) -> None:
        # SkillContext has no provider and no fetch. Interpretation cannot quietly
        # become retrieval.
        context = _context(_record("EV-1", "content"))
        assert not hasattr(context, "retrieve")
        assert not hasattr(context, "source")

    def test_a_violation_triggers_exactly_one_retry(self) -> None:
        good = json.dumps(
            {
                "alternatives": [
                    {"id": "A1", "name": "Process", "kind": OptionKind.PROCESS_CHANGE.value},
                    {"id": "A2", "name": "Defer", "kind": OptionKind.DEFER.value},
                ]
            }
        )
        ai_only = json.dumps(
            {"alternatives": [{"id": "A1", "name": "AI", "kind": OptionKind.AI_ASSISTED.value}]}
        )
        provider = FakeProvider(ai_only, good)
        run = AlternativesSkill(provider).run(_context(_record("EV-1", "x")))
        assert len(provider.requests) == 2
        assert run.retried
        assert run.output.has_non_ai

    def test_the_retry_names_the_broken_rule(self) -> None:
        ai_only = json.dumps(
            {"alternatives": [{"id": "A1", "name": "AI", "kind": OptionKind.AI_ASSISTED.value}]}
        )
        good = json.dumps(
            {"alternatives": [{"id": "A1", "name": "Defer", "kind": OptionKind.DEFER.value}]}
        )
        provider = FakeProvider(ai_only, good)
        AlternativesSkill(provider).run(_context(_record("EV-1", "x")))
        assert "Every option involves AI" in provider.requests[1].user

    def test_a_second_violation_fails_rather_than_being_patched(self) -> None:
        # DecisionLens never inserts the missing option itself. Authoring an
        # alternative and presenting it as analysis is the fabrication this
        # product exists to prevent.
        ai_only = json.dumps(
            {"alternatives": [{"id": "A1", "name": "AI", "kind": OptionKind.AI_ASSISTED.value}]}
        )
        provider = FakeProvider(ai_only, ai_only)
        with pytest.raises(SkillViolation, match="Every option involves AI"):
            AlternativesSkill(provider).run(_context(_record("EV-1", "x")))
        assert len(provider.requests) == 2

    def test_retry_can_be_disabled(self) -> None:
        ai_only = json.dumps(
            {"alternatives": [{"id": "A1", "name": "AI", "kind": OptionKind.AI_ASSISTED.value}]}
        )
        provider = FakeProvider(ai_only, ai_only)
        with pytest.raises(SkillViolation):
            AlternativesSkill(provider, allow_retry=False).run(_context(_record("EV-1", "x")))
        assert len(provider.requests) == 1

    def test_malformed_output_is_a_skill_error_not_a_violation(self) -> None:
        provider = FakeProvider("not json", "still not json")
        with pytest.raises(SkillError) as exc:
            ContradictionsSkill(provider).run(_context(_record("EV-1", "x")))
        assert not isinstance(exc.value, SkillViolation)

    def test_a_provider_failure_is_reported_with_its_stages(self) -> None:
        provider = FakeProvider(fail_with=ModelUnavailable("down"))
        with pytest.raises(SkillError) as exc:
            ContradictionsSkill(provider).run(_context(_record("EV-1", "x")))
        assert exc.value.stages
        assert not exc.value.stages[0].succeeded

    def test_every_call_is_traceable_to_a_prompt_version(self) -> None:
        provider = FakeProvider(json.dumps({"contradictions": []}))
        skill = ContradictionsSkill(provider)
        skill.run(_context(_record("EV-1", "x")))
        sent = provider.requests[0]
        assert sent.skill == "contradictions"
        # Whatever the skill declares, not a pinned literal: the claim under test
        # is that the request carries the version, not which version it is today.
        assert sent.prompt_version == skill.prompt.version
        assert sent.prompt_fingerprint == skill.prompt.fingerprint


# --------------------------------------------------------------------------- #
# Relevance
# --------------------------------------------------------------------------- #


class TestRelevance:
    def test_invented_ids_are_rejected(self) -> None:
        bad = json.dumps({"relevant_ids": ["EV-1", "EV-NOPE"], "excluded": []})
        good = json.dumps({"relevant_ids": ["EV-1"], "excluded": []})
        provider = FakeProvider(bad, good)
        RelevanceSkill(provider).run(_context(_record("EV-1", "x")))
        assert "EV-NOPE" in provider.requests[1].user

    def test_unmentioned_records_are_kept_not_dropped(self) -> None:
        # Silence is not an exclusion decision. Defaulting the other way would let
        # an incomplete answer shrink the evidence base invisibly.
        payload = json.dumps({"relevant_ids": ["EV-1"], "excluded": []})
        context = _context(_record("EV-1", "a"), _record("EV-2", "b"))
        run = RelevanceSkill(FakeProvider(payload)).run(context)
        assert set(run.output.relevant_ids) == {"EV-1", "EV-2"}
        assert any("neither selected nor excluded" in w for w in run.warnings)

    def test_an_explicit_exclusion_is_honoured_with_its_reason(self) -> None:
        payload = json.dumps(
            {
                "relevant_ids": ["EV-1"],
                "excluded": [{"evidence_id": "EV-2", "reason": "about packaging, not delivery"}],
            }
        )
        context = _context(_record("EV-1", "a"), _record("EV-2", "b"))
        run = RelevanceSkill(FakeProvider(payload)).run(context)
        assert run.output.relevant_ids == ("EV-1",)
        assert run.output.excluded[0].reason


# --------------------------------------------------------------------------- #
# Classification: facts, assumptions, opinions, constraints
# --------------------------------------------------------------------------- #


def _claims_payload(*claims: dict[str, Any]) -> str:
    return json.dumps({"claims": list(claims)})


class TestClassification:
    def test_facts_assumptions_and_opinions_are_distinguished(self) -> None:
        content = "Success was 87.4%. Customers probably want SMS. The VP wants AI."
        context = _context(_record("EV-1", content))
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "Success was 87.4%.",
                "claim_type": ClaimType.FACT.value,
                "citations": [{"evidence_id": "EV-1", "quote": "Success was 87.4%."}],
            },
            {
                "id": "C2",
                "statement": "Customers want SMS.",
                "claim_type": ClaimType.ASSUMPTION.value,
                "citations": [{"evidence_id": "EV-1", "quote": "Customers probably want SMS."}],
            },
            {
                "id": "C3",
                "statement": "The VP wants AI.",
                "claim_type": ClaimType.STAKEHOLDER_OPINION.value,
                "citations": [{"evidence_id": "EV-1", "quote": "The VP wants AI."}],
            },
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(context)
        kinds = {c.claim_type for c in run.output.claims}
        assert kinds == {ClaimType.FACT, ClaimType.ASSUMPTION, ClaimType.STAKEHOLDER_OPINION}
        assert sum(1 for c in run.output.claims if c.claim_type.is_evidence) == 1

    def test_technical_and_governance_constraints_are_separated(self) -> None:
        content = "The driver app is locked until Q3. AI content requires human review."
        context = _context(_record("EV-1", content))
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "Driver app locked until Q3.",
                "claim_type": ClaimType.TECHNICAL_CONSTRAINT.value,
                "citations": [
                    {"evidence_id": "EV-1", "quote": "The driver app is locked until Q3."}
                ],
            },
            {
                "id": "C2",
                "statement": "AI content needs human review.",
                "claim_type": ClaimType.GOVERNANCE_CONSTRAINT.value,
                "citations": [
                    {"evidence_id": "EV-1", "quote": "AI content requires human review."}
                ],
            },
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(context)
        constraints = [c for c in run.output.claims if c.claim_type.is_constraint]
        assert len(constraints) == 2
        assert {c.claim_type for c in constraints} == {
            ClaimType.TECHNICAL_CONSTRAINT,
            ClaimType.GOVERNANCE_CONSTRAINT,
        }

    def test_a_fabricated_quote_is_rejected_and_named(self) -> None:
        context = _context(_record("EV-1", "Success was 87.4%."))
        bad = _claims_payload(
            {
                "id": "C1",
                "statement": "Weather causes most failures.",
                "claim_type": ClaimType.FACT.value,
                "citations": [{"evidence_id": "EV-1", "quote": "Weather causes 80%."}],
            }
        )
        good = _claims_payload(
            {
                "id": "C1",
                "statement": "Success was 87.4%.",
                "claim_type": ClaimType.FACT.value,
                "citations": [{"evidence_id": "EV-1", "quote": "Success was 87.4%."}],
            }
        )
        provider = FakeProvider(bad, good)
        ClassificationSkill(provider, as_of=AS_OF).run(context)
        assert "not in the evidence" in provider.requests[1].user

    def test_staleness_is_calculated_not_asked_for(self) -> None:
        fresh = _record("EV-1", "recent", updated_at=date(2026, 7, 1))
        old = _record("EV-2", "ancient", updated_at=date(2024, 11, 20))
        context = _context(fresh, old)
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "s",
                "claim_type": ClaimType.FACT.value,
                "citations": [{"evidence_id": "EV-1", "quote": "recent"}],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(context)
        by_id = {c.evidence_id: c for c in run.output.classifications}
        assert by_id["EV-2"].is_stale and by_id["EV-2"].age_days == 620
        assert not by_id["EV-1"].is_stale
        assert any("at least 365 days old" in w for w in run.warnings)

    def test_evidence_type_comes_from_the_record_not_the_model(self) -> None:
        context = _context(
            _record("EV-1", "policy text", evidence_type=EvidenceType.GOVERNANCE_POLICY)
        )
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "s",
                "claim_type": ClaimType.GOVERNANCE_CONSTRAINT.value,
                "citations": [{"evidence_id": "EV-1", "quote": "policy text"}],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(context)
        assert run.output.classifications[0].evidence_type is EvidenceType.GOVERNANCE_POLICY

    def test_extracting_nothing_is_a_violation(self) -> None:
        provider = FakeProvider(_claims_payload(), _claims_payload())
        with pytest.raises(SkillViolation, match="No claims were extracted"):
            ClassificationSkill(provider, as_of=AS_OF).run(_context(_record("EV-1", "x")))


# --------------------------------------------------------------------------- #
# Contradictions
# --------------------------------------------------------------------------- #


class TestContradictions:
    def _payload(self, **over: Any) -> str:
        base = {
            "id": "CT-1",
            "topic": "success rate",
            "kind": "temporal_conflict",
            "side_a": {"evidence_id": "EV-1", "quote": "currently 91%"},
            "side_b": {"evidence_id": "EV-2", "quote": "value: 87.4"},
            "summary": "figures disagree",
            "how_to_resolve": "The 91% matches an older period.",
        }
        base.update(over)
        return json.dumps({"contradictions": [base]})

    def test_a_contradiction_with_resolvable_sides_is_accepted(self) -> None:
        context = _context(_record("EV-1", "currently 91%"), _record("EV-2", "value: 87.4"))
        run = ContradictionsSkill(FakeProvider(self._payload())).run(context)
        assert len(run.output.contradictions) == 1

    def test_an_unresolvable_side_is_rejected(self) -> None:
        context = _context(_record("EV-1", "currently 91%"), _record("EV-2", "value: 87.4"))
        bad = self._payload(side_b={"evidence_id": "EV-2", "quote": "value: 99.9"})
        provider = FakeProvider(bad, self._payload())
        ContradictionsSkill(provider).run(context)
        assert "not in the evidence" in provider.requests[1].user

    def test_missing_resolution_guidance_is_rejected(self) -> None:
        # Reporting that two sources disagree is less useful than reporting that
        # one of them is quoting a stale figure.
        context = _context(_record("EV-1", "currently 91%"), _record("EV-2", "value: 87.4"))
        provider = FakeProvider(self._payload(how_to_resolve=""), self._payload())
        ContradictionsSkill(provider).run(context)
        assert "does not say how to resolve it" in provider.requests[1].user

    def test_both_sides_may_come_from_one_document(self) -> None:
        # A document contradicting itself is a real finding; a rule rejecting it
        # would discard valid contradictions.
        context = _context(_record("EV-1", "We will ship in Q1.\nWe will not ship this year."))
        payload = self._payload(
            side_a={"evidence_id": "EV-1", "quote": "We will ship in Q1."},
            side_b={"evidence_id": "EV-1", "quote": "We will not ship this year."},
        )
        run = ContradictionsSkill(FakeProvider(payload)).run(context)
        assert len(run.output.contradictions) == 1


# --------------------------------------------------------------------------- #
# Missing evidence
# --------------------------------------------------------------------------- #


class TestMissingEvidence:
    def _gap(self, **over: Any) -> dict[str, Any]:
        base = {
            "id": "MG-1",
            "question": "What do drivers say?",
            "impact": GapImpact.WOULD_CHANGE_RECOMMENDATION.value,
            "why_it_matters": "Two options are driver-facing and no driver evidence exists.",
            "was_searched": True,
        }
        base.update(over)
        return base

    def test_gaps_are_returned_with_their_impact(self) -> None:
        payload = json.dumps({"gaps": [self._gap()]})
        run = MissingEvidenceSkill(FakeProvider(payload)).run(_context(_record("EV-1", "x")))
        assert run.output.gaps[0].impact is GapImpact.WOULD_CHANGE_RECOMMENDATION

    def test_a_gap_without_a_reason_is_rejected(self) -> None:
        bad = json.dumps({"gaps": [self._gap(why_it_matters="  ")]})
        provider = FakeProvider(bad, json.dumps({"gaps": [self._gap()]}))
        MissingEvidenceSkill(provider).run(_context(_record("EV-1", "x")))
        assert "does not say why it matters" in provider.requests[1].user

    def test_finding_no_gaps_at_all_is_rejected(self) -> None:
        provider = FakeProvider(json.dumps({"gaps": []}), json.dumps({"gaps": []}))
        with pytest.raises(SkillViolation, match="No gaps were identified"):
            MissingEvidenceSkill(provider).run(_context(_record("EV-1", "x")))

    def test_an_unpopulated_metric_is_found_by_scanning(self) -> None:
        # Blank is not zero, and a scan finds this with certainty where a model
        # might not.
        empty_metric = _record(
            "EV-9",
            "period: 2026-Q2\nmetric: repeat_exception_customers\n"
            "unit: count\nnote: never populated",
        )
        payload = json.dumps({"gaps": [self._gap()]})
        run = MissingEvidenceSkill(FakeProvider(payload)).run(_context(empty_metric))
        questions = [g.question for g in run.output.gaps]
        assert any("repeat_exception_customers" in q for q in questions)
        assert any("unpopulated metric" in w for w in run.warnings)

    def test_a_populated_metric_is_not_reported_as_missing(self) -> None:
        full = _record("EV-9", "metric: first_attempt_success\nvalue: 87.4\nunit: percent")
        payload = json.dumps({"gaps": [self._gap()]})
        run = MissingEvidenceSkill(FakeProvider(payload)).run(_context(full))
        assert len(run.output.gaps) == 1


# --------------------------------------------------------------------------- #
# Alternatives: the two mandatory rules
# --------------------------------------------------------------------------- #


class TestAlternatives:
    def _alts(self, *kinds: OptionKind) -> str:
        return json.dumps(
            {
                "alternatives": [
                    {"id": f"A{i}", "name": f"Option {i}", "kind": k.value}
                    for i, k in enumerate(kinds, start=1)
                ]
            }
        )

    def test_ai_only_options_are_rejected(self) -> None:
        provider = FakeProvider(
            self._alts(OptionKind.AI_ASSISTED, OptionKind.AI_AUTOMATED),
            self._alts(OptionKind.PROCESS_CHANGE, OptionKind.DEFER),
        )
        run = AlternativesSkill(provider).run(_context(_record("EV-1", "x")))
        assert run.output.has_non_ai and run.output.has_no_build

    def test_a_missing_no_build_option_is_rejected(self) -> None:
        provider = FakeProvider(
            self._alts(OptionKind.PROCESS_CHANGE, OptionKind.AI_ASSISTED),
            self._alts(OptionKind.PROCESS_CHANGE, OptionKind.FURTHER_RESEARCH),
        )
        AlternativesSkill(provider).run(_context(_record("EV-1", "x")))
        assert "no no-change, defer, or further-research option" in provider.requests[1].user

    @pytest.mark.parametrize(
        "kind", [OptionKind.NO_CHANGE, OptionKind.DEFER, OptionKind.FURTHER_RESEARCH]
    )
    def test_each_no_build_kind_satisfies_the_rule(self, kind: OptionKind) -> None:
        run = AlternativesSkill(FakeProvider(self._alts(kind))).run(_context(_record("EV-1", "x")))
        assert run.output.has_no_build

    def test_the_no_build_rule_subsumes_the_non_ai_rule(self) -> None:
        # A structural property worth pinning. Every no-build kind is non-AI, so
        # any set satisfying the no-build rule satisfies the non-AI rule too, and
        # the non-AI check can never be the sole violation. Both rules are kept
        # because the specification requires both and the messages differ. If
        # OptionKind ever gained an AI-flavoured no-build kind, the non-AI rule
        # would become independently load-bearing and this test fails first.
        no_build = [k for k in OptionKind if k.is_no_build]
        assert no_build
        assert not any(k.is_ai for k in no_build)

    def test_ai_only_output_reports_both_broken_rules(self) -> None:
        provider = FakeProvider(
            self._alts(OptionKind.AI_ASSISTED, OptionKind.AI_AUTOMATED),
            self._alts(OptionKind.DEFER),
        )
        AlternativesSkill(provider).run(_context(_record("EV-1", "x")))
        retry = provider.requests[1].user
        assert "Every option involves AI" in retry
        assert "no no-change, defer, or further-research option" in retry

    def test_duplicate_ids_are_rejected(self) -> None:
        dupes = json.dumps(
            {
                "alternatives": [
                    {"id": "A1", "name": "One", "kind": OptionKind.DEFER.value},
                    {"id": "A1", "name": "Two", "kind": OptionKind.PROCESS_CHANGE.value},
                ]
            }
        )
        provider = FakeProvider(dupes, self._alts(OptionKind.DEFER))
        AlternativesSkill(provider).run(_context(_record("EV-1", "x")))
        assert "ids must be unique" in provider.requests[1].user

    def test_unassessable_dimensions_are_reported_not_scored_as_zero(self) -> None:
        # Treating absence of evidence as low value systematically defunds
        # anything new, because a bet has no track record by definition.
        payload = json.dumps(
            {
                "alternatives": [
                    {
                        "id": "A1",
                        "name": "Autonomous delivery",
                        "kind": OptionKind.AI_AUTOMATED.value,
                        "horizon": "innovation",
                        "assessments": [
                            {
                                "dimension": Dimension.PRODUCT_USAGE.value,
                                "state": AssessmentState.CANNOT_ASSESS.value,
                                "summary": "has not shipped",
                            },
                            {
                                "dimension": Dimension.RISK.value,
                                "state": AssessmentState.CANNOT_ASSESS.value,
                                "summary": "no pilot",
                            },
                        ],
                    },
                    {"id": "A2", "name": "Defer", "kind": OptionKind.DEFER.value},
                ]
            }
        )
        run = AlternativesSkill(FakeProvider(payload)).run(_context(_record("EV-1", "x")))
        assert len(run.output.alternatives[0].unassessed_dimensions) == 2
        assert any("could not be made" in w for w in run.warnings)

    def test_constraints_are_passed_to_the_model(self) -> None:
        from decision_lens.models import Claim

        constraint = Claim(
            id="C1",
            statement="Driver app locked until Q3.",
            claim_type=ClaimType.TECHNICAL_CONSTRAINT,
        )
        provider = FakeProvider(self._alts(OptionKind.DEFER))
        AlternativesSkill(provider, constraints=(constraint,)).run(_context(_record("EV-1", "x")))
        assert "Driver app locked until Q3." in provider.requests[0].user


# --------------------------------------------------------------------------- #
# Recommendation
# --------------------------------------------------------------------------- #


class TestRecommendation:
    def _rec(self, **over: Any) -> str:
        base: dict[str, Any] = {
            "statement": "Pilot address validation.",
            "option_kind": OptionKind.DATA_QUALITY.value,
            "support_level": SupportLevel.MODERATE.value,
        }
        base.update(over)
        return json.dumps({"recommendation": base})

    def test_a_recommendation_is_returned(self) -> None:
        run = RecommendationSkill(FakeProvider(self._rec())).run(_context(_record("EV-1", "x")))
        assert run.output.recommendation.support_level is SupportLevel.MODERATE

    def test_selecting_an_alternative_that_does_not_exist_is_rejected(self) -> None:
        from decision_lens.models import Alternative

        alts = (Alternative(id="A1", name="Real", kind=OptionKind.DEFER),)
        provider = FakeProvider(
            self._rec(selected_alternative_id="A99"), self._rec(selected_alternative_id="A1")
        )
        RecommendationSkill(provider, alternatives=alts).run(_context(_record("EV-1", "x")))
        assert "which is not one of the alternatives" in provider.requests[1].user

    def test_strong_support_must_say_what_would_change_it(self) -> None:
        provider = FakeProvider(
            self._rec(support_level=SupportLevel.STRONG.value),
            self._rec(
                support_level=SupportLevel.STRONG.value, what_would_change_it=["a randomised pilot"]
            ),
        )
        run = RecommendationSkill(provider).run(_context(_record("EV-1", "x")))
        assert "cannot act on is decoration" in provider.requests[1].user
        assert run.output.recommendation.what_would_change_it

    def test_strong_support_is_capped_when_claims_are_ungrounded(self) -> None:
        # Insufficient evidence: computed, not judged.
        payload = self._rec(
            support_level=SupportLevel.STRONG.value,
            what_would_change_it=["more data"],
            claims=[
                {"id": "C1", "statement": "It will work.", "claim_type": ClaimType.ASSUMPTION.value}
            ],
        )
        run = RecommendationSkill(FakeProvider(payload)).run(_context(_record("EV-1", "x")))
        assert run.output.recommendation.support_level is SupportLevel.MODERATE
        assert "Support reduced from strong" in run.output.recommendation.support_basis
        assert any("unverifiable" in w for w in run.warnings)

    def test_strong_support_survives_when_every_claim_resolves(self) -> None:
        context = _context(_record("EV-1", "Address errors dominate apartments."))
        payload = self._rec(
            support_level=SupportLevel.STRONG.value,
            what_would_change_it=["a contradicting measurement"],
            claims=[
                {
                    "id": "C1",
                    "statement": "Address errors dominate apartments.",
                    "claim_type": ClaimType.FACT.value,
                    "citations": [
                        {"evidence_id": "EV-1", "quote": "Address errors dominate apartments."}
                    ],
                }
            ],
        )
        run = RecommendationSkill(FakeProvider(payload)).run(context)
        assert run.output.recommendation.support_level is SupportLevel.STRONG

    def test_the_skill_records_no_decision(self) -> None:
        # It recommends. The PM decides, and PMDecision is recorded elsewhere.
        run = RecommendationSkill(FakeProvider(self._rec())).run(_context(_record("EV-1", "x")))
        assert not hasattr(run.output, "decision")
        assert not hasattr(run.output, "approved")


# --------------------------------------------------------------------------- #
# The named scenarios, against the real corpus
# --------------------------------------------------------------------------- #


class TestPlantedScenarios:
    def test_executive_pressure_is_classifiable_as_opinion(
        self, real_context: SkillContext
    ) -> None:
        record = _find(real_context, "I want the AI exception assistant shipped this quarter.")
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "The VP wants the AI assistant shipped this quarter.",
                "claim_type": ClaimType.STAKEHOLDER_OPINION.value,
                "citations": [
                    {
                        "evidence_id": record.id,
                        "quote": "I want the AI exception assistant shipped this quarter.",
                    }
                ],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(real_context)
        assert run.output.claims[0].claim_type is ClaimType.STAKEHOLDER_OPINION
        assert not run.output.claims[0].claim_type.is_evidence

    def test_labelling_executive_pressure_as_fact_still_resolves_but_is_not_evidence(
        self, real_context: SkillContext
    ) -> None:
        # The citation check cannot catch a wrong label - the quote is real. This
        # is why the challenger exists in Phase 8, and the gap is recorded here.
        record = _find(real_context, "I want the AI exception assistant shipped this quarter.")
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "AI is the right intervention.",
                "claim_type": ClaimType.FACT.value,
                "citations": [
                    {
                        "evidence_id": record.id,
                        "quote": "I want the AI exception assistant shipped this quarter.",
                    }
                ],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(real_context)
        assert run.output.claims[0].claim_type is ClaimType.FACT  # not caught here

    def test_the_misleading_denominator_is_present_and_quotable(
        self, real_context: SkillContext
    ) -> None:
        record = _find(real_context, "80% of surveyed customers")
        assert "The survey was sent to 15 customers" in record.content
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "A survey of 15 self-selected customers reported wanting SMS alerts.",
                "claim_type": ClaimType.STAKEHOLDER_OPINION.value,
                "citations": [
                    {"evidence_id": record.id, "quote": "The survey was sent to 15 customers"}
                ],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(real_context)
        assert run.output.claims[0].is_grounded

    def test_the_outdated_source_is_flagged_by_calculation(
        self, real_context: SkillContext
    ) -> None:
        record = _find(real_context, "Pre-arrival notification pilot")
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "A notification pilot ran in 2024.",
                "claim_type": ClaimType.FACT.value,
                "citations": [
                    {
                        "evidence_id": record.id,
                        "quote": "Pre-arrival SMS was enabled for a subset of deliveries",
                    }
                ],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(real_context)
        stale = {c.evidence_id for c in run.output.classifications if c.is_stale}
        assert record.id in stale

    def test_governance_constraints_are_present_in_the_corpus(
        self, real_context: SkillContext
    ) -> None:
        record = _find(real_context, "requires human review before dispatch")
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "AI-generated customer content needs human review.",
                "claim_type": ClaimType.GOVERNANCE_CONSTRAINT.value,
                "citations": [
                    {"evidence_id": record.id, "quote": "requires human review before dispatch"}
                ],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(real_context)
        assert run.output.claims[0].claim_type is ClaimType.GOVERNANCE_CONSTRAINT

    def test_technical_constraints_are_present_in_the_corpus(
        self, real_context: SkillContext
    ) -> None:
        record = _find(real_context, "release train is locked until Q3 2026")
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "The driver app cannot change before Q3 2026.",
                "claim_type": ClaimType.TECHNICAL_CONSTRAINT.value,
                "citations": [
                    {"evidence_id": record.id, "quote": "release train is locked until Q3 2026"}
                ],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(real_context)
        assert run.output.claims[0].claim_type.is_constraint

    def test_the_planted_scope_conflict_is_expressible(self, real_context: SkillContext) -> None:
        overall = _find(real_context, "ticket_count: 1842")
        apartment = _find(real_context, "ticket_count: 921")
        payload = json.dumps(
            {
                "contradictions": [
                    {
                        "id": "CT-1",
                        "topic": "largest exception driver",
                        "kind": "scope_conflict",
                        "side_a": {"evidence_id": overall.id, "quote": "ticket_count: 1842"},
                        "side_b": {"evidence_id": apartment.id, "quote": "ticket_count: 921"},
                        "summary": "access issues lead overall; address errors lead for apartments",
                        "how_to_resolve": (
                            "State the segment; both are true of different populations."
                        ),
                    }
                ]
            }
        )
        run = ContradictionsSkill(FakeProvider(payload)).run(real_context)
        assert run.output.contradictions[0].kind.value == "scope_conflict"

    def test_the_real_corpus_contains_an_unpopulated_metric(
        self, real_context: SkillContext
    ) -> None:
        payload = json.dumps(
            {
                "gaps": [
                    {
                        "id": "MG-1",
                        "question": "What do drivers say?",
                        "impact": GapImpact.WOULD_CHANGE_RECOMMENDATION.value,
                        "why_it_matters": "No driver evidence exists.",
                    }
                ]
            }
        )
        run = MissingEvidenceSkill(FakeProvider(payload)).run(real_context)
        assert any("repeat_exception_customers" in g.question for g in run.output.gaps)


# --------------------------------------------------------------------------- #
# Rendering: what each skill actually shows the model
# --------------------------------------------------------------------------- #


class TestRenderingReachesTheModel:
    """These renderers feed later skills. If one silently produced nothing, a
    stage would run with an empty section and the model would answer anyway."""

    def test_constraints_reach_the_alternatives_prompt(self) -> None:
        from decision_lens.models import Claim

        constraints = (
            Claim(id="C1", statement="Locked until Q3.", claim_type=ClaimType.TECHNICAL_CONSTRAINT),
            Claim(
                id="C2",
                statement="Human review required.",
                claim_type=ClaimType.GOVERNANCE_CONSTRAINT,
            ),
            Claim(id="C3", statement="Not a constraint.", claim_type=ClaimType.FACT),
        )
        provider = FakeProvider(
            json.dumps(
                {"alternatives": [{"id": "A1", "name": "Defer", "kind": OptionKind.DEFER.value}]}
            )
        )
        AlternativesSkill(provider, constraints=constraints).run(_context(_record("EV-1", "x")))
        sent = provider.requests[0].user
        assert "Locked until Q3." in sent
        assert "Human review required." in sent
        assert "Not a constraint." not in sent  # only constraint-typed claims

    def test_alternatives_contradictions_and_gaps_reach_the_recommendation_prompt(self) -> None:
        from decision_lens.models import (
            Alternative,
            Citation,
            Contradiction,
            ContradictionKind,
            DimensionAssessment,
            MissingEvidence,
        )

        alts = (
            Alternative(
                id="A1",
                name="Address validation",
                kind=OptionKind.DATA_QUALITY,
                description="Validate at order entry.",
                horizon=None,
                assessments=(
                    DimensionAssessment(
                        dimension=Dimension.RISK,
                        state=AssessmentState.CANNOT_ASSESS,
                        summary="no pilot has run",
                    ),
                ),
            ),
        )
        contradictions = (
            Contradiction(
                id="CT-1",
                topic="success rate",
                kind=ContradictionKind.TEMPORAL_CONFLICT,
                side_a=Citation(evidence_id="EV-1", quote="a"),
                side_b=Citation(evidence_id="EV-2", quote="b"),
                summary="figures disagree",
                how_to_resolve="check the period",
            ),
        )
        gaps = (
            MissingEvidence(
                id="MG-1",
                question="What do drivers say?",
                impact=GapImpact.WOULD_CHANGE_RECOMMENDATION,
            ),
        )
        provider = FakeProvider(
            json.dumps(
                {
                    "recommendation": {
                        "statement": "Pilot it.",
                        "option_kind": OptionKind.DATA_QUALITY.value,
                    }
                }
            )
        )
        RecommendationSkill(
            provider, alternatives=alts, contradictions=contradictions, gaps=gaps
        ).run(_context(_record("EV-1", "x")))
        sent = provider.requests[0].user
        assert "A1 Address validation" in sent
        assert "risk: cannot_assess" in sent  # the unassessable dimension is visible
        assert "temporal_conflict" in sent
        assert "What do drivers say?" in sent

    def test_empty_sections_say_so_rather_than_going_blank(self) -> None:
        provider = FakeProvider(
            json.dumps(
                {"recommendation": {"statement": "Defer.", "option_kind": OptionKind.DEFER.value}}
            )
        )
        RecommendationSkill(provider).run(_context(_record("EV-1", "x")))
        sent = provider.requests[0].user
        assert "(none generated)" in sent
        assert "(none identified)" in sent

    def test_claims_render_with_their_type_and_citations(self) -> None:
        from decision_lens.models import Citation, Claim
        from decision_lens.rendering import render_claims

        rendered = render_claims(
            (
                Claim(
                    id="C1",
                    statement="Grounded.",
                    claim_type=ClaimType.FACT,
                    citations=(Citation(evidence_id="EV-1", quote="q"),),
                ),
                Claim(id="C2", statement="Floating.", claim_type=ClaimType.ASSUMPTION),
            )
        )
        assert "[fact] Grounded. ([EV-1])" in rendered
        assert "uncited" in rendered
        assert render_claims(()) == "(none identified)"


# --------------------------------------------------------------------------- #
# Remaining deterministic checks
# --------------------------------------------------------------------------- #


class TestRemainingChecks:
    def test_generating_no_alternatives_at_all_is_rejected(self) -> None:
        empty = json.dumps({"alternatives": []})
        provider = FakeProvider(empty, empty)
        with pytest.raises(SkillViolation, match="No alternatives were generated"):
            AlternativesSkill(provider).run(_context(_record("EV-1", "x")))

    def test_an_alternative_citing_absent_text_is_rejected(self) -> None:
        bad = json.dumps(
            {
                "alternatives": [
                    {
                        "id": "A1",
                        "name": "Defer",
                        "kind": OptionKind.DEFER.value,
                        "supporting": [{"evidence_id": "EV-1", "quote": "never written"}],
                    }
                ]
            }
        )
        good = json.dumps(
            {"alternatives": [{"id": "A1", "name": "Defer", "kind": OptionKind.DEFER.value}]}
        )
        provider = FakeProvider(bad, good)
        AlternativesSkill(provider).run(_context(_record("EV-1", "real text")))
        assert "cites text not in the evidence" in provider.requests[1].user

    def test_a_dimension_assessment_citing_absent_text_is_rejected(self) -> None:
        bad = json.dumps(
            {
                "alternatives": [
                    {
                        "id": "A1",
                        "name": "Defer",
                        "kind": OptionKind.DEFER.value,
                        "assessments": [
                            {
                                "dimension": Dimension.RISK.value,
                                "state": AssessmentState.ASSESSED.value,
                                "summary": "low risk",
                                "citations": [{"evidence_id": "EV-1", "quote": "invented"}],
                            }
                        ],
                    }
                ]
            }
        )
        good = json.dumps(
            {"alternatives": [{"id": "A1", "name": "Defer", "kind": OptionKind.DEFER.value}]}
        )
        provider = FakeProvider(bad, good)
        AlternativesSkill(provider).run(_context(_record("EV-1", "real text")))
        assert "dimension risk cites" in provider.requests[1].user

    def test_a_recommendation_claim_citing_absent_text_is_rejected(self) -> None:
        bad = json.dumps(
            {
                "recommendation": {
                    "statement": "Do it.",
                    "option_kind": OptionKind.DATA_QUALITY.value,
                    "claims": [
                        {
                            "id": "C1",
                            "statement": "Proven.",
                            "claim_type": ClaimType.FACT.value,
                            "citations": [{"evidence_id": "EV-1", "quote": "not present"}],
                        }
                    ],
                }
            }
        )
        good = json.dumps(
            {
                "recommendation": {
                    "statement": "Do it.",
                    "option_kind": OptionKind.DATA_QUALITY.value,
                }
            }
        )
        provider = FakeProvider(bad, good)
        RecommendationSkill(provider).run(_context(_record("EV-1", "real text")))
        assert "cites text not in the evidence" in provider.requests[1].user

    def test_a_metric_the_model_already_named_is_not_added_twice(self) -> None:
        empty_metric = _record(
            "EV-9", "period: 2026-Q2\nmetric: repeat_exception_customers\nunit: count"
        )
        payload = json.dumps(
            {
                "gaps": [
                    {
                        "id": "MG-1",
                        "question": "How many repeat_exception_customers are there?",
                        "impact": GapImpact.WOULD_REFINE_SCOPE.value,
                        "why_it_matters": "The field was never populated.",
                    }
                ]
            }
        )
        run = MissingEvidenceSkill(FakeProvider(payload)).run(_context(empty_metric))
        assert len(run.output.gaps) == 1  # not duplicated by the scan

    def test_a_skill_declaring_no_hard_requirements_still_runs(self) -> None:
        # The base default. A future skill with nothing deterministic to check
        # must not be forced to invent one.
        from decision_lens.prompts import Prompt
        from decision_lens.skills.base import Skill

        class Trivial(Skill[Any]):
            name = "trivial"
            prompt = Prompt(name="trivial", version="v1", user_template="{x}")

            @property
            def output_model(self) -> type[Any]:
                from decision_lens.skills.relevance import RelevanceOutput

                return RelevanceOutput

            def render_values(self, context: SkillContext) -> dict[str, str]:
                return {"x": "hello"}

        run = Trivial(FakeProvider(json.dumps({"relevant_ids": []}))).run(
            _context(_record("EV-1", "x"))
        )
        assert run.stages


class TestSupportLevelIsDerivedHonestly:
    """support_level must come from the record, never from how the analysis used it."""

    def test_an_uncited_record_is_not_marked_weak(self) -> None:
        # "Unused" and "weak" are different things. Conflating them would
        # systematically mislabel evidence the analysis simply did not reach for.
        cited = _record("EV-1", "quoted text", updated_at=date(2026, 7, 1))
        untouched = _record("EV-2", "never referenced", updated_at=date(2026, 7, 1))
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "s",
                "claim_type": ClaimType.FACT.value,
                "citations": [{"evidence_id": "EV-1", "quote": "quoted text"}],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(
            _context(cited, untouched)
        )
        by_id = {c.evidence_id: c for c in run.output.classifications}
        assert by_id["EV-2"].support_level is SupportLevel.MODERATE
        assert by_id["EV-2"].support_level == by_id["EV-1"].support_level

    def test_stakeholder_input_is_weak_however_recent(self) -> None:
        opinion = _record(
            "EV-1",
            "The VP wants it.",
            evidence_type=EvidenceType.STAKEHOLDER_INPUT,
            updated_at=date(2026, 8, 1),
        )
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "s",
                "claim_type": ClaimType.STAKEHOLDER_OPINION.value,
                "citations": [{"evidence_id": "EV-1", "quote": "The VP wants it."}],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(_context(opinion))
        classification = run.output.classifications[0]
        assert classification.support_level is SupportLevel.LOW
        assert "report belief, not measurement" in classification.rationale

    def test_no_rule_ever_awards_strong_support(self) -> None:
        # Whether a passage strongly supports a claim is judgment about content.
        # A rule awarding it from metadata alone would be inventing confidence.
        from decision_lens.skills.classification import _support_from_record

        for evidence_type in EvidenceType:
            for stale in (True, False):
                assert _support_from_record(evidence_type, stale) is not SupportLevel.STRONG

    def test_a_stale_metric_is_weak_despite_its_type(self) -> None:
        old = _record(
            "EV-1",
            "value: 91.0",
            evidence_type=EvidenceType.QUANTITATIVE_METRIC,
            updated_at=date(2024, 11, 20),
        )
        payload = _claims_payload(
            {
                "id": "C1",
                "statement": "s",
                "claim_type": ClaimType.FACT.value,
                "citations": [{"evidence_id": "EV-1", "quote": "value: 91.0"}],
            }
        )
        run = ClassificationSkill(FakeProvider(payload), as_of=AS_OF).run(_context(old))
        assert run.output.classifications[0].support_level is SupportLevel.LOW


class TestRetrievalBoundaryIsStructural:
    def test_no_skill_module_imports_a_connector(self) -> None:
        # Skills interpret; they do not retrieve. Enforced by inspection rather
        # than by convention, because a convention is one careless import away
        # from being false.
        import decision_lens.skills as pkg

        skill_dir = Path(pkg.__file__).parent
        offenders = [
            path.name
            for path in skill_dir.glob("*.py")
            if "decision_lens.connectors" in path.read_text(encoding="utf-8")
        ]
        assert offenders == []

    def test_the_skill_context_exposes_no_way_to_fetch(self) -> None:
        context = _context(_record("EV-1", "x"))
        surface = {name for name in dir(context) if not name.startswith("_")}
        for forbidden in ("retrieve", "source", "connector", "fetch", "load"):
            assert forbidden not in surface

    def test_the_approved_skill_set_is_exactly_seven(self) -> None:
        """Tripwire against skill sprawl, updated per phase.

        Six analysis skills arrived in Phase 7; the challenger joined them in
        Phase 8. It is a skill rather than orchestrator code because it is one:
        a versioned prompt, a typed output, and deterministic requirements of
        its own. Nothing else is a skill.
        """
        from decision_lens.skills import SKILL_NAMES

        assert set(SKILL_NAMES) == {
            "relevance",
            "classification",
            "contradictions",
            "missing_evidence",
            "alternatives",
            "recommendation",
            "challenger",
        }
        assert len(SKILL_NAMES) == len(set(SKILL_NAMES))


class TestCitationRepair:
    """Re-labelling a citation that quotes real text against the wrong record.

    From a live run that failed twice on exactly this: the model quoted a
    delivery comment word for word and attributed it to a neighbouring record.
    The quote is verifiable, so the correct id is a fact rather than a guess —
    but only when one record contains it.
    """

    @staticmethod
    def _context() -> SkillContext:
        return _context(
            _record("EV-1", "Gate was locked and the driver did not have the code."),
            _record("EV-2", "Would be helpful to know the delivery window."),
            _record("EV-3", "Address errors account for 40% of exceptions."),
        )

    def test_a_quote_found_in_exactly_one_other_record_is_re_pointed(self) -> None:
        from decision_lens.skills.base import repair_citations

        context = self._context()
        # Correct quote, wrong id — the shape the live run produced.
        citation = Citation(
            evidence_id="EV-2", quote="Gate was locked and the driver did not have the code."
        )
        fixed: list[str] = []
        repaired = repair_citations(citation, context, fixed)

        assert isinstance(repaired, Citation)
        assert repaired.evidence_id == "EV-1"
        assert repaired.quote == citation.quote, (
            "an already-verbatim quote is never rewritten; only the label moved"
        )
        assert "was found in EV-1" in fixed[0]

    def test_a_correct_citation_is_untouched_and_unremarked(self) -> None:
        from decision_lens.skills.base import repair_citations

        context = self._context()
        citation = Citation(evidence_id="EV-3", quote="Address errors account for 40%")
        fixed: list[str] = []
        assert repair_citations(citation, context, fixed) is citation
        assert fixed == []

    def test_an_invented_quote_is_left_alone_to_be_rejected(self) -> None:
        """Repair is for mislabelling. A quote in no record stays broken."""
        from decision_lens.skills.base import repair_citations

        context = self._context()
        citation = Citation(evidence_id="EV-1", quote="Exceptions fell by half last quarter.")
        fixed: list[str] = []

        assert repair_citations(citation, context, fixed) is citation
        assert fixed == []
        assert context.unresolvable((citation,)) == (citation,)

    def test_a_quote_differing_only_in_typography_is_snapped_to_the_source(self) -> None:
        """One missing hyphen cost a 29-minute recording run. Not twice.

        The repair rewrites the quote to the source's own characters rather than
        loosening the check, so what lands in the brief is genuinely verbatim
        and a reader who searches the evidence for it will find it.
        """
        from decision_lens.skills.base import repair_citations

        context = _context(_record("EV-1", "First-attempt success was 88.1% in the pilot."))
        citation = Citation(evidence_id="EV-1", quote="first attempt success was 88.1%")
        fixed: list[str] = []
        repaired = repair_citations(citation, context, fixed)

        assert isinstance(repaired, Citation)
        assert repaired.quote == "First-attempt success was 88.1%"
        assert context.resolves(repaired), "the repaired citation must actually resolve"
        assert "typography" in fixed[0]

    def test_a_wrong_id_and_wrong_typography_are_both_repaired_and_both_reported(self) -> None:
        from decision_lens.skills.base import repair_citations

        context = _context(
            _record("EV-1", "Gate was locked and the driver did not have the code."),
            _record("EV-2", "Unrelated."),
        )
        citation = Citation(evidence_id="EV-2", quote="gate was locked and the driver")
        fixed: list[str] = []
        repaired = repair_citations(citation, context, fixed)

        assert isinstance(repaired, Citation)
        assert repaired.evidence_id == "EV-1"
        assert repaired.quote == "Gate was locked and the driver"
        assert context.resolves(repaired)
        assert len(fixed) == 2, "a reader is told about both corrections, not one"

    def test_a_changed_number_is_never_snapped(self) -> None:
        """The line the repair must not cross: this is a different claim."""
        from decision_lens.skills.base import repair_citations

        context = _context(_record("EV-1", "First-attempt success was 88.1% in the pilot."))
        citation = Citation(evidence_id="EV-1", quote="First-attempt success was 87.6%")
        fixed: list[str] = []

        assert repair_citations(citation, context, fixed) is citation
        assert fixed == []
        assert context.unresolvable((citation,)) == (citation,)

    def test_an_ambiguous_quote_is_left_alone(self) -> None:
        """Two records contain it, so which one was meant is not knowable."""
        from decision_lens.skills.base import repair_citations

        context = _context(
            _record("EV-1", "Delivery failed."),
            _record("EV-2", "Delivery failed."),
        )
        citation = Citation(evidence_id="EV-9", quote="Delivery failed.")
        fixed: list[str] = []

        assert repair_citations(citation, context, fixed) is citation
        assert fixed == []

    def test_repair_reaches_citations_nested_deep_in_an_output(self) -> None:
        """Alternatives carry citations three levels down, inside assessments."""
        from decision_lens.skills.alternatives import AlternativesOutput
        from decision_lens.skills.base import repair_citations

        context = self._context()
        misattributed = Citation(
            evidence_id="EV-3", quote="Gate was locked and the driver did not have the code."
        )
        output = AlternativesOutput(
            alternatives=(
                Alternative(
                    id="ALT-1",
                    name="Validate addresses",
                    kind=OptionKind.DATA_QUALITY,
                    supporting=(misattributed,),
                    assessments=(
                        DimensionAssessment(
                            dimension=Dimension.RISK,
                            state=AssessmentState.ASSESSED,
                            summary="Bounded.",
                            citations=(misattributed,),
                        ),
                    ),
                ),
            )
        )
        fixed: list[str] = []
        repaired = repair_citations(output, context, fixed)

        assert isinstance(repaired, AlternativesOutput)
        alt = repaired.alternatives[0]
        assert alt.supporting[0].evidence_id == "EV-1"
        assert alt.assessments[0].citations[0].evidence_id == "EV-1"
        assert len(fixed) == 2

    def test_a_stage_survives_a_mislabelled_citation_and_says_so(self) -> None:
        """End to end: the run succeeds, and the correction is reported."""
        from decision_lens.skills.contradictions import ContradictionsOutput

        context = self._context()
        good = Citation(evidence_id="EV-3", quote="Address errors account for 40% of exceptions.")
        wrong = Citation(
            evidence_id="EV-3", quote="Gate was locked and the driver did not have the code."
        )
        text = ContradictionsOutput(
            contradictions=(
                Contradiction(
                    id="CN-1",
                    topic="cause",
                    kind=ContradictionKind.CLAIM_CONFLICT,
                    side_a=good,
                    side_b=wrong,
                    how_to_resolve="Recount by cause.",
                ),
            )
        ).model_dump_json()

        run = ContradictionsSkill(FakeProvider(text)).run(context)

        assert run.output.contradictions[0].side_b.evidence_id == "EV-1"
        assert any("was found in EV-1" in w for w in run.warnings)
        assert not run.retried, "the stage was not thrown away over a label"

    def test_a_blank_quote_resolves_to_nothing(self) -> None:
        """Guard: an empty string is contained by every record."""
        assert self._context().locate("   ") is None

"""The strong single-call baseline.

Two properties matter more than the rest, because the whole evaluation rests on
them: the baseline must be given a genuinely fair shot, and it must not be
secretly helped. A strawman would let DecisionLens claim a win it had not earned;
a baseline quietly benefiting from DecisionLens's provenance check would erase
the difference being measured.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from decision_lens.baseline import BaselineError, BaselineOutput, StrongBaseline
from decision_lens.llm import (
    ModelRequest,
    ModelResponse,
    ModelTimeout,
    ModelUnavailable,
    ModelUsage,
)
from decision_lens.models import (
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
from decision_lens.prompts.baseline import BASELINE_REPAIR_V1, BASELINE_V1
from decision_lens.rendering import render_criteria, render_evidence

CLOCK = datetime(2026, 8, 2, 10, 0, 0)
QUOTE = "Address errors account for 40% of delivery exceptions."


@pytest.fixture
def evidence() -> tuple[EvidenceRecord, ...]:
    return (
        EvidenceRecord(
            id="EV-0001",
            source_system=SourceSystem.LOCAL_FILE,
            source_id="support_ticket_summaries.csv",
            title="Support tickets (synthetic)",
            content=f"Q2 review.\n{QUOTE}",
            evidence_type=EvidenceType.OPERATIONAL_RECORD,
            updated_at=date(2026, 6, 1),
            owner="support-ops",
        ),
        EvidenceRecord(
            id="EV-0002",
            source_system=SourceSystem.LOCAL_FILE,
            source_id="stakeholder_notes.md",
            title="Stakeholder notes (synthetic)",
            content="The VP wants the AI assistant shipped this quarter.",
            evidence_type=EvidenceType.STAKEHOLDER_INPUT,
        ),
    )


@pytest.fixture
def request_() -> DecisionRequest:
    return DecisionRequest(
        id="sample_delivery_exceptions",
        question="Which intervention should the team prioritize to reduce delivery exceptions?",
        desired_outcome="Improve first-attempt delivery success.",
        user=UserContext(user_id="pm-001", product_area="delivery"),
    )


def _valid_output(*, quote: str = QUOTE, evidence_id: str = "EV-0001") -> str:
    return json.dumps(
        {
            "claims": [
                {
                    "id": "CL-1",
                    "statement": "Address quality drives most exceptions.",
                    "claim_type": ClaimType.FACT.value,
                    "citations": [{"evidence_id": evidence_id, "quote": quote}],
                    "support_level": SupportLevel.MODERATE.value,
                }
            ],
            "alternatives": [
                {"id": "A1", "name": "Address validation", "kind": OptionKind.DATA_QUALITY.value},
                {"id": "A2", "name": "Defer", "kind": OptionKind.DEFER.value},
            ],
            "recommendation": {
                "statement": "Pilot address validation for apartment deliveries.",
                "option_kind": OptionKind.DATA_QUALITY.value,
                "support_level": SupportLevel.MODERATE.value,
            },
        }
    )


class FakeProvider:
    """Returns scripted responses. Reaches nothing."""

    def __init__(self, *texts: str, fail_with: Exception | None = None) -> None:
        self._texts = list(texts)
        self._fail_with = fail_with
        self.requests: list[ModelRequest] = []

    @property
    def provider_id(self) -> str:
        return "fake"

    @property
    def model_id(self) -> str:
        return "fake-1"

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
            latency_ms=42,
            usage=ModelUsage(input_tokens=5000, output_tokens=800),
            is_cached=False,
        )


class TestPromptStrength:
    """The baseline must not be weakened by omission."""

    @pytest.mark.parametrize(
        "instruction",
        [
            "GROUND EVERY CLAIM",
            "NEVER INVENT EVIDENCE",
            "CLASSIFY HONESTLY",
            "SURFACE CONTRADICTIONS",
            "NAME WHAT IS MISSING",
            "GIVE REAL ALTERNATIVES",
            "BE HONEST ABOUT SUPPORT",
            "WATCH FOR MISLEADING NUMBERS",
            "PROPOSE WHAT TO TEST",
            "SEPARATE MANDATORY WORK FROM DISCRETIONARY WORK",
            "THE READER DECIDES",
        ],
    )
    def test_the_prompt_asks_for_everything_decisionlens_does(self, instruction: str) -> None:
        assert instruction in BASELINE_V1.system

    def test_the_prompt_demands_a_non_ai_and_a_no_build_option(self) -> None:
        # Withholding these would hand DecisionLens an unearned win on the two
        # deterministic checks it is proudest of.
        system = BASELINE_V1.system.lower()
        assert "does not involve ai" in system
        assert "no-change, defer, or further-research" in system

    def test_every_output_field_is_something_the_prompt_asked_for(self) -> None:
        # Asking for a field the model was never told about would hand
        # DecisionLens that dimension by default. priority_exceptions was exactly
        # that until rule 10 was added.
        system = BASELINE_V1.system.lower()
        assert "priority exceptions" in system
        for obligation in ("security", "compliance", "contractual", "critical-reliability"):
            assert obligation in system

    def test_the_prompt_demands_verbatim_quotes(self) -> None:
        assert "VERBATIM" in BASELINE_V1.system
        assert "Never paraphrase inside a quote" in BASELINE_V1.system

    def test_both_prompts_are_registered_and_versioned(self) -> None:
        from decision_lens.prompts import REGISTRY

        assert REGISTRY.get("baseline", "v1") is BASELINE_V1
        assert REGISTRY.get("baseline-repair", "v1") is BASELINE_REPAIR_V1


class TestPromptAssembly:
    def test_evidence_is_rendered_verbatim_with_citable_ids(
        self, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        # Summarising here would make "quote verbatim" impossible to obey.
        rendered = render_evidence(evidence)
        assert "[EV-0001]" in rendered and "[EV-0002]" in rendered
        assert QUOTE in rendered

    def test_evidence_metadata_reaches_the_prompt(
        self, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        rendered = render_evidence(evidence)
        assert "operational_record" in rendered
        assert "updated: 2026-06-01" in rendered
        assert "owner: support-ops" in rendered

    def test_criteria_default_to_all_nine_dimensions(self, request_: DecisionRequest) -> None:
        assert len(render_criteria(request_).splitlines()) == 9

    def test_the_call_carries_the_question_evidence_and_schema(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        provider = FakeProvider(_valid_output())
        StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        sent = provider.requests[0]
        assert request_.question in sent.user
        assert QUOTE in sent.user
        assert '"claims"' in sent.user  # the schema
        assert sent.system == BASELINE_V1.system

    def test_the_call_is_traceable_to_a_prompt_version(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        provider = FakeProvider(_valid_output())
        StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        sent = provider.requests[0]
        assert sent.prompt_version == BASELINE_V1.version
        assert sent.prompt_fingerprint == BASELINE_V1.fingerprint


class TestSingleCall:
    def test_a_successful_run_makes_exactly_one_call(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        # One call without controlled stages is the definition of this arm.
        provider = FakeProvider(_valid_output())
        StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        assert len(provider.requests) == 1

    def test_the_brief_uses_the_same_schema_as_decisionlens(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        assert brief.id == "BASELINE-sample_delivery_exceptions"
        assert brief.request is request_
        assert brief.recommendation is not None
        assert brief.has_non_ai_alternative
        assert brief.has_no_build_alternative

    def test_the_generated_timestamp_is_deterministic(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        assert brief.generated_at == CLOCK


class TestEvidenceIntegrity:
    def test_the_brief_carries_the_real_records_not_model_output(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        # If the model could emit its own EvidenceRecords it could invent evidence
        # and then cite it, and citation checking would measure nothing.
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        assert brief.evidence == evidence

    def test_the_model_cannot_add_evidence_through_its_output(self) -> None:
        payload = json.loads(_valid_output())
        payload["evidence"] = [{"id": "EV-FAKE", "content": "invented"}]
        parsed = BaselineOutput.model_validate(payload)
        assert not hasattr(parsed, "evidence")

    def test_a_fabricated_citation_survives_into_the_brief(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        # The baseline is the unvalidated arm. Stripping bad citations here would
        # apply DecisionLens's provenance stage to it and erase the difference the
        # evaluation exists to measure.
        bad = _valid_output(quote="Weather causes 80% of exceptions.")
        brief = StrongBaseline(FakeProvider(bad), clock=CLOCK).run(request_, evidence)
        assert len(brief.unresolvable_citations) == 1
        assert brief.validation_issues == ()

    def test_a_citation_to_a_nonexistent_record_also_survives(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output(evidence_id="EV-9999")), clock=CLOCK).run(
            request_, evidence
        )
        assert len(brief.unresolvable_citations) == 1

    def test_a_correct_citation_resolves(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        assert brief.unresolvable_citations == ()


class TestRepairRetry:
    def test_malformed_output_triggers_exactly_one_repair(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        provider = FakeProvider("not json at all", _valid_output())
        brief = StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        assert len(provider.requests) == 2
        assert brief.recommendation is not None

    def test_the_repair_call_uses_its_own_versioned_prompt(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        provider = FakeProvider("not json", _valid_output())
        StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        repair = provider.requests[1]
        assert repair.skill == "baseline-repair"
        assert repair.prompt_version == BASELINE_REPAIR_V1.version

    def test_the_repair_prompt_includes_the_error_and_the_previous_answer(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        provider = FakeProvider("not json", _valid_output())
        StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        repair = provider.requests[1].user
        assert "not json" in repair
        assert "does not match" in repair

    def test_the_repair_resends_the_full_original_request(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        # If the first response was prose rather than a formatting slip, a repair
        # holding only the schema and the bad answer cannot rebuild the analysis:
        # it has no evidence. That would make "one repair" less generous than
        # intended, and the spec forbids weakening the baseline.
        provider = FakeProvider("I would rather discuss something else.", _valid_output())
        StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        repair = provider.requests[1].user
        assert request_.question in repair
        assert QUOTE in repair
        assert "[EV-0001]" in repair

    def test_the_repair_can_redo_the_task_from_scratch(self) -> None:
        assert "redo the task from the original request" in BASELINE_REPAIR_V1.system

    def test_a_second_failure_is_not_retried_again(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        provider = FakeProvider("bad", "still bad")
        with pytest.raises(BaselineError, match="no repair attempt remains"):
            StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        assert len(provider.requests) == 2

    def test_repair_can_be_disabled(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        provider = FakeProvider("bad", _valid_output())
        with pytest.raises(BaselineError):
            StrongBaseline(provider, allow_repair=False, clock=CLOCK).run(request_, evidence)
        assert len(provider.requests) == 1

    def test_the_repair_is_visible_in_the_trace(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        # The retry costs a call. Hiding it would flatter the baseline's cost and
        # latency numbers against DecisionLens.
        provider = FakeProvider("bad", _valid_output())
        brief = StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        assert brief.run_trace is not None
        names = [s.name for s in brief.run_trace.stages]
        assert names == ["baseline", "baseline-repair"]
        assert not brief.run_trace.stages[0].succeeded
        assert brief.run_trace.stages[1].succeeded


class TestRunTrace:
    def test_the_trace_pins_provider_model_and_prompt_version(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        assert brief.run_trace is not None
        stage = brief.run_trace.stages[0]
        assert stage.provider == "fake"
        assert stage.model == "fake-1"
        assert stage.prompt_version == "v1"

    def test_usage_and_latency_are_captured(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        assert brief.run_trace is not None
        stage = brief.run_trace.stages[0]
        assert stage.input_tokens == 5000
        assert stage.output_tokens == 800
        assert brief.run_trace.total_latency_ms == 42

    def test_the_trace_identifies_the_request(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        assert brief.run_trace is not None
        assert brief.run_trace.request_id == request_.id
        assert brief.run_trace.run_id == "baseline-sample_delivery_exceptions"


class TestProviderFailure:
    @pytest.mark.parametrize(
        "failure", [ModelTimeout("too slow"), ModelUnavailable("provider down")]
    )
    def test_a_provider_failure_raises_with_its_trace(
        self,
        request_: DecisionRequest,
        evidence: tuple[EvidenceRecord, ...],
        failure: Exception,
    ) -> None:
        # An evaluation that silently drops failed runs overstates the ones it keeps.
        with pytest.raises(BaselineError) as exc:
            StrongBaseline(FakeProvider(fail_with=failure), clock=CLOCK).run(request_, evidence)
        assert exc.value.trace.stages
        assert not exc.value.trace.stages[0].succeeded

    def test_the_failure_names_the_stage(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        with pytest.raises(BaselineError, match="stage 'baseline'"):
            StrongBaseline(FakeProvider(fail_with=ModelUnavailable("down")), clock=CLOCK).run(
                request_, evidence
            )


class TestOutputSchema:
    def test_extra_top_level_keys_do_not_fail_the_baseline(self) -> None:
        # Failing the baseline for adding a helpful field would handicap it.
        payload = json.loads(_valid_output())
        payload["notes"] = "some extra commentary"
        assert BaselineOutput.model_validate(payload).recommendation is not None

    def test_a_recommendation_is_required(self) -> None:
        payload = json.loads(_valid_output())
        del payload["recommendation"]
        with pytest.raises(ValueError, match="recommendation"):
            BaselineOutput.model_validate(payload)

    def test_the_analysis_sections_default_to_empty(self) -> None:
        parsed = BaselineOutput.model_validate(
            {"recommendation": {"statement": "Defer.", "option_kind": OptionKind.DEFER.value}}
        )
        assert parsed.claims == ()
        assert parsed.contradictions == ()
        assert parsed.missing_evidence == ()

    def test_the_schema_sent_to_the_model_is_valid_json(self) -> None:
        provider = FakeProvider(_valid_output())
        baseline = StrongBaseline(provider, clock=CLOCK)
        schema = json.loads(baseline._schema_text())
        assert "properties" in schema
        assert set(schema["properties"]) >= {"claims", "alternatives", "recommendation"}


class TestNoNetworkNoSecrets:
    def test_no_credentials_are_read(
        self,
        request_: DecisionRequest,
        evidence: tuple[EvidenceRecord, ...],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-never-be-read")
        provider = FakeProvider(_valid_output())
        brief = StrongBaseline(provider, clock=CLOCK).run(request_, evidence)
        serialised = brief.model_dump_json()
        assert "sk-should-never-be-read" not in serialised
        assert "sk-should-never-be-read" not in provider.requests[0].user

    def test_the_baseline_holds_no_live_provider_of_its_own(self) -> None:
        # It composes whatever provider it is handed. There is no hidden path to
        # a real API, which is what makes the offline demo trustworthy.
        import decision_lens.baseline as module

        source = module.__file__
        assert source is not None
        text = Path(source).read_text(encoding="utf-8")
        for forbidden in ("import anthropic", "import openai", "requests.post", "httpx"):
            assert forbidden not in text


class TestFairness:
    def test_baseline_and_decisionlens_share_the_analysis_model_types(self) -> None:
        # Literal schema parity, not merely conceptual: the same Claim,
        # Contradiction and Recommendation classes on both sides.
        annotations = BaselineOutput.model_fields
        assert annotations["claims"].annotation == tuple[Claim, ...]
        assert annotations["recommendation"].annotation is Recommendation

    def test_the_baseline_gets_a_generous_timeout(self) -> None:
        from decision_lens.baseline import BASELINE_TIMEOUT_SECONDS
        from decision_lens.llm import DEFAULT_TIMEOUT_SECONDS

        # It does in one call what DecisionLens spreads across many.
        assert BASELINE_TIMEOUT_SECONDS > DEFAULT_TIMEOUT_SECONDS

    def test_a_claim_carries_its_citation_into_the_brief(
        self, request_: DecisionRequest, evidence: tuple[EvidenceRecord, ...]
    ) -> None:
        brief = StrongBaseline(FakeProvider(_valid_output()), clock=CLOCK).run(request_, evidence)
        claim = brief.claims[0]
        assert claim.is_grounded
        assert claim.citations == (Citation(evidence_id="EV-0001", quote=QUOTE),)

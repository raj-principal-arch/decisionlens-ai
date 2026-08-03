"""The case checker, the judge, and the runner.

Three things stand between a corpus and a number, and each fails silently in its
own way. The checker can pass a case whose answer key no longer describes it. The
judge can report a clean sheet because it was never reached. The runner can drop
a case that failed and quietly improve whichever arm broke more often.

So the tests here care less about the happy path than about what each part does
when something is wrong.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from decision_lens.evaluation.casecheck import check_all_cases, check_case
from decision_lens.evaluation.ground_truth import GroundTruth
from decision_lens.evaluation.harness import BASELINE, DECISIONLENS, evaluate_case
from decision_lens.evaluation.judge import JUDGE_V1, judge_brief
from decision_lens.llm import ModelResponse, ModelUnavailable, ModelUsage

CLOCK = datetime(2026, 8, 3, 9, 0, 0)
DATA = Path("data")
TRUTH = Path("evals/ground_truth")


# --------------------------------------------------------------------------- #
# The case checker
# --------------------------------------------------------------------------- #


class TestCheckerOnRealCases:
    @pytest.mark.parametrize(
        "case", sorted(p.name for p in DATA.iterdir() if p.is_dir()), ids=lambda c: c
    )
    def test_every_shipped_case_checks_out(self, case: str) -> None:
        report = check_case(DATA / case, TRUTH / f"{case}.json")
        assert report.ok, report.describe()
        assert report.record_count > 0
        assert report.span_count > 0

    def test_check_all_cases_covers_the_whole_directory(self) -> None:
        reports = check_all_cases(DATA, TRUTH)
        assert len(reports) == len([p for p in DATA.iterdir() if p.is_dir()])
        assert all(r.ok for r in reports)


def _clone(tmp_path: Path, case: str = "sample_delivery_exceptions") -> tuple[Path, Path]:
    """A writable copy of a real case, so mutations can be tested destructively."""
    import shutil

    directory = tmp_path / case
    shutil.copytree(DATA / case, directory)
    truth = json.loads((TRUTH / f"{case}.json").read_text(encoding="utf-8"))
    path = tmp_path / f"{case}.json"
    path.write_text(json.dumps(truth), encoding="utf-8")
    return directory, path


class TestCheckerCatchesDrift:
    def test_a_clean_copy_passes(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        assert check_case(directory, truth).ok

    def test_evidence_edited_without_updating_the_key_is_caught(self, tmp_path: Path) -> None:
        """The failure that survives review because nothing looks wrong."""
        directory, truth = _clone(tmp_path)
        target = directory / "business_objectives.md"
        target.write_text(target.read_text().replace("91%", "99%"), encoding="utf-8")
        report = check_case(directory, truth)
        assert not report.ok
        assert any("not found" in p for p in report.problems)

    def test_a_key_quoting_a_file_that_does_not_exist_is_caught(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        payload = json.loads(truth.read_text())
        payload["known_facts"][0]["source"] = "invented.md"
        truth.write_text(json.dumps(payload))
        report = check_case(directory, truth)
        assert not report.ok
        assert any("no evidence records" in p for p in report.problems)

    def test_an_evidence_file_nothing_refers_to_is_surfaced(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        (directory / "stray.md").write_text("> Synthetic document.\nOrphan.\n", encoding="utf-8")
        report = check_case(directory, truth)
        assert not report.ok
        assert any("stray.md" in p for p in report.problems)

    def test_naming_the_real_company_outside_a_disclaimer_is_caught(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        target = directory / "prior_decisions.md"
        target.write_text(
            target.read_text() + "\nEscalated to the Walmart logistics team.\n", encoding="utf-8"
        )
        report = check_case(directory, truth)
        assert not report.ok
        assert any("Walmart" in p for p in report.problems)

    def test_a_disclaimer_line_naming_the_company_is_allowed(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        target = directory / "prior_decisions.md"
        target.write_text(
            target.read_text() + "\n> Synthetic note. No real Walmart data.\n", encoding="utf-8"
        )
        assert check_case(directory, truth).ok

    def test_an_unparseable_key_is_reported_rather_than_raised(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        truth.write_text("{not json", encoding="utf-8")
        report = check_case(directory, truth)
        assert not report.ok
        assert any("does not parse" in p for p in report.problems)

    def test_a_missing_case_directory_is_reported(self, tmp_path: Path) -> None:
        report = check_case(tmp_path / "absent", TRUTH / "sample_delivery_exceptions.json")
        assert not report.ok
        assert any("case directory missing" in p for p in report.problems)

    def test_a_missing_key_is_reported(self, tmp_path: Path) -> None:
        directory, _ = _clone(tmp_path)
        report = check_case(directory, tmp_path / "absent.json")
        assert not report.ok
        assert any("ground truth missing" in p for p in report.problems)

    def test_a_case_id_disagreeing_with_its_directory_is_caught(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        payload = json.loads(truth.read_text())
        payload["case_id"] = "some_other_case"
        truth.write_text(json.dumps(payload))
        report = check_case(directory, truth)
        assert not report.ok
        assert any("does not match directory" in p for p in report.problems)

    def test_a_notice_that_does_not_say_synthetic_is_caught(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        payload = json.loads(truth.read_text())
        payload["notice"] = "Ordinary evidence about an organisation."
        truth.write_text(json.dumps(payload))
        report = check_case(directory, truth)
        assert not report.ok
        assert any("synthetic" in p for p in report.problems)

    def test_the_report_describes_itself_both_ways(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        assert check_case(directory, truth).describe().lstrip().startswith("OK")
        (directory / "stray.md").write_text("> Synthetic.\nOrphan.\n", encoding="utf-8")
        assert "FAIL" in check_case(directory, truth).describe()


# --------------------------------------------------------------------------- #
# The judge
# --------------------------------------------------------------------------- #


class ScriptedJudge:
    """Answers with whatever it was handed, or raises."""

    provider_id = "scripted"
    model_id = "scripted-1"

    def __init__(self, text: str | Exception) -> None:
        self._text = text
        self.requests: list[object] = []

    def complete(self, request: object) -> ModelResponse:
        self.requests.append(request)
        if isinstance(self._text, Exception):
            raise self._text
        return ModelResponse(
            text=self._text,
            provider=self.provider_id,
            model=self.model_id,
            prompt_version="v1",
            skill="evaluation-judge",
            latency_ms=1,
            usage=ModelUsage(),
            is_cached=False,
        )


def _truth_for_judging() -> GroundTruth:
    return GroundTruth.model_validate_json(
        (TRUTH / "sample_delivery_exceptions.json").read_text(encoding="utf-8")
    )


class TestJudge:
    def test_a_violation_backed_by_a_quotation_is_reported(self) -> None:
        payload = json.dumps(
            {
                "forbidden_claims": [
                    {"id": "GT-U1", "made": True, "quote": "the brief said this", "reasoning": "r"}
                ],
                "gaps_found": [{"id": "GT-M1", "made": True, "quote": "q", "reasoning": "r"}],
            }
        )
        result = judge_brief(
            "brief text", _truth_for_judging(), ScriptedJudge(payload), case_id="c", arm="a"
        )
        assert result.usable
        assert result.violations == ("GT-U1",)
        assert result.gaps_found == ("GT-M1",)

    def test_an_accusation_with_no_quotation_is_discarded(self) -> None:
        """The burden of proof sits on the accusation, not the brief."""
        payload = json.dumps(
            {"forbidden_claims": [{"id": "GT-U1", "made": True, "quote": "  ", "reasoning": "r"}]}
        )
        result = judge_brief(
            "brief", _truth_for_judging(), ScriptedJudge(payload), case_id="c", arm="a"
        )
        assert result.violations == ()
        assert result.discarded_unevidenced == ("GT-U1",)

    def test_a_negative_verdict_is_not_a_violation(self) -> None:
        payload = json.dumps({"forbidden_claims": [{"id": "GT-U1", "made": False, "quote": ""}]})
        result = judge_brief(
            "brief", _truth_for_judging(), ScriptedJudge(payload), case_id="c", arm="a"
        )
        assert result.violations == ()
        assert result.usable

    def test_a_fenced_block_is_tolerated(self) -> None:
        payload = "```json\n" + json.dumps({"forbidden_claims": []}) + "\n```"
        assert judge_brief(
            "brief", _truth_for_judging(), ScriptedJudge(payload), case_id="c", arm="a"
        ).usable

    def test_output_that_does_not_parse_is_unusable_not_clean(self) -> None:
        """'We could not check' and 'we checked and found nothing' differ."""
        result = judge_brief(
            "brief", _truth_for_judging(), ScriptedJudge("not json"), case_id="c", arm="a"
        )
        assert not result.usable
        assert "did not parse" in result.error

    def test_a_provider_failure_is_unusable_not_clean(self) -> None:
        result = judge_brief(
            "brief",
            _truth_for_judging(),
            ScriptedJudge(ModelUnavailable("overloaded")),
            case_id="c",
            arm="a",
        )
        assert not result.usable
        assert "ModelUnavailable" in result.error

    def test_the_judge_is_not_told_which_arm_produced_the_brief(self) -> None:
        """A judge that can see the arm can prefer one, and the comparison dies."""
        provider = ScriptedJudge(json.dumps({"forbidden_claims": []}))
        judge_brief(
            "the brief", _truth_for_judging(), provider, case_id="mycase", arm="decisionlens"
        )
        sent = provider.requests[0]
        assert "decisionlens" not in sent.system  # type: ignore[attr-defined]
        assert "decisionlens" not in sent.user  # type: ignore[attr-defined]
        assert "decisionlens" in sent.case_id  # type: ignore[attr-defined]

    def test_a_key_with_nothing_to_judge_costs_no_call(self) -> None:
        truth = GroundTruth.model_validate(
            {
                "case_id": "c",
                "version": "1.0",
                "synthetic": True,
                "notice": "synthetic",
                "authoring_limitation": "same author",
                "question": "q?",
                "desired_outcome": "o",
                "scoring_rules": {
                    "recall_denominator": "a",
                    "unplanted_findings": "b",
                    "span_matching": "c",
                    "restraint_scoring": "d",
                    "forbidden_claims": "e",
                },
                "expected_alternative_categories": {},
                "recommendation_restraint": {"max_defensible_support_level": "low", "reason": "r"},
            }
        )
        provider = ScriptedJudge(ModelUnavailable("must not be called"))
        result = judge_brief("brief", truth, provider, case_id="c", arm="a")
        assert result.usable
        assert provider.requests == []

    def test_the_judge_prompt_is_not_in_the_product_registry(self) -> None:
        """Evaluation apparatus is not something the agent runs."""
        from decision_lens.prompts import REGISTRY

        assert "evaluation-judge" not in REGISTRY.names()
        assert JUDGE_V1.fingerprint


# --------------------------------------------------------------------------- #
# The runner
# --------------------------------------------------------------------------- #


class TestHarness:
    def test_an_unloadable_case_is_reported_rather_than_dropped(self, tmp_path: Path) -> None:
        """Dropping it would flatter whichever arm broke more often."""
        result = evaluate_case(
            tmp_path / "nope", TRUTH / "sample_delivery_exceptions.json", ScriptedJudge("{}")
        )
        assert result.error
        assert result.arms == {}

    def test_an_arm_whose_stages_all_fail_still_yields_a_scored_row(self, tmp_path: Path) -> None:
        """The orchestrator degrades rather than collapsing, and the harness
        keeps the result. A case that vanished when it went wrong would flatter
        whichever arm broke more often."""
        directory, truth = _clone(tmp_path)
        provider = ScriptedJudge(ModelUnavailable("down"))
        result = evaluate_case(directory, truth, provider, clock=CLOCK, arms=(DECISIONLENS,))
        arm = result.arm(DECISIONLENS)
        assert arm is not None
        assert arm.produced_a_brief, "a degraded brief is still a result"
        assert arm.score is not None
        assert arm.score.failed_stages, "and it names every stage that did not complete"
        assert not arm.score.actionable
        assert result.records > 0

    def test_the_baseline_arm_reports_its_error_when_the_call_fails(self, tmp_path: Path) -> None:
        """Unlike the staged arm, one call that fails produces nothing to score."""
        directory, truth = _clone(tmp_path)
        result = evaluate_case(
            directory, truth, ScriptedJudge(ModelUnavailable("down")), clock=CLOCK, arms=(BASELINE,)
        )
        arm = result.arm(BASELINE)
        assert arm is not None
        assert arm.error
        assert not arm.produced_a_brief

    def test_both_arms_are_attempted(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        provider = ScriptedJudge(ModelUnavailable("down"))
        result = evaluate_case(directory, truth, provider, clock=CLOCK)
        assert set(result.arms) == {DECISIONLENS, BASELINE}

    def test_scored_returns_only_arms_that_produced_something(self, tmp_path: Path) -> None:
        from decision_lens.evaluation.harness import EvaluationRun

        directory, truth = _clone(tmp_path)
        run = EvaluationRun()
        run.cases.append(
            evaluate_case(directory, truth, ScriptedJudge(ModelUnavailable("x")), clock=CLOCK)
        )
        # The staged arm degrades into a scoreable brief; the single-call arm does not.
        assert len(run.scored(DECISIONLENS)) == 1
        assert run.scored(BASELINE) == []


class TestEdgesThatOnlyShowUpWhenSomethingIsBroken:
    def test_a_corpus_that_will_not_load_is_reported(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        (directory / "case_manifest.json").write_text("{not json", encoding="utf-8")
        report = check_case(directory, truth)
        assert not report.ok
        assert any("does not load" in p for p in report.problems)

    def test_a_directory_holding_no_evidence_is_reported(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        for f in directory.iterdir():
            if f.name != "case_manifest.json":
                f.unlink()
        report = check_case(directory, truth)
        assert not report.ok

    def test_a_key_that_quotes_nothing_is_reported(self, tmp_path: Path) -> None:
        """An answer key anchored nowhere asserts things about a corpus it never read."""
        directory, truth = _clone(tmp_path)
        payload = json.loads(truth.read_text())
        for section in (
            "expected_contradictions",
            "known_facts",
            "known_opinions",
            "known_constraints",
            "governance_issues",
            "evidence_hazards",
            "irrelevant_evidence",
            "known_assumptions",
            "unsupported_claims_the_system_must_not_make",
            "expected_missing_evidence",
        ):
            payload[section] = []
        truth.write_text(json.dumps(payload))
        report = check_case(directory, truth)
        assert not report.ok
        assert any("quotes the corpus nowhere" in p for p in report.problems)

    def test_a_directory_entry_that_is_not_a_file_is_skipped(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        (directory / "a_subdirectory").mkdir()
        report = check_case(directory, truth)
        assert not any("a_subdirectory" in p for p in report.problems if "Walmart" in p)


class ExplodingProvider:
    """Fails in a way no arm anticipates, to prove one arm cannot end the run."""

    provider_id = "exploding"
    model_id = "exploding-1"

    def complete(self, request: object) -> ModelResponse:
        raise RuntimeError("something nobody planned for")


class TestRunnerResilience:
    def test_an_unexpected_exception_is_caught_and_named(self, tmp_path: Path) -> None:
        directory, truth = _clone(tmp_path)
        result = evaluate_case(directory, truth, ExplodingProvider(), clock=CLOCK, arms=(BASELINE,))
        arm = result.arm(BASELINE)
        assert arm is not None
        assert "unexpected RuntimeError" in arm.error

    def test_evaluate_all_walks_the_directory_and_reports_progress(self, tmp_path: Path) -> None:
        from decision_lens.evaluation.harness import evaluate_all

        directory, truth = _clone(tmp_path)
        truth_root = tmp_path / "truth"
        truth_root.mkdir()
        (truth_root / f"{directory.name}.json").write_text(truth.read_text(), encoding="utf-8")

        lines: list[str] = []
        run = evaluate_all(
            tmp_path,
            truth_root,
            ExplodingProvider(),
            clock=CLOCK,
            arms=(BASELINE,),
            progress=lines.append,
        )
        assert [c.case_id for c in run.cases] == [directory.name]
        assert run.provider_id == "exploding"
        assert any("failed" in line for line in lines)

    def test_only_restricts_which_cases_run(self, tmp_path: Path) -> None:
        from decision_lens.evaluation.harness import evaluate_all

        directory, truth = _clone(tmp_path)
        truth_root = tmp_path / "truth"
        truth_root.mkdir()
        (truth_root / f"{directory.name}.json").write_text(truth.read_text(), encoding="utf-8")
        run = evaluate_all(
            tmp_path, truth_root, ExplodingProvider(), arms=(BASELINE,), only=("nothing_matches",)
        )
        assert run.cases == []

    def test_a_case_directory_without_a_key_is_skipped(self, tmp_path: Path) -> None:
        from decision_lens.evaluation.harness import evaluate_all

        _clone(tmp_path)
        empty_truth = tmp_path / "truth"
        empty_truth.mkdir()
        run = evaluate_all(tmp_path, empty_truth, ExplodingProvider(), arms=(BASELINE,))
        assert run.cases == []

    def test_a_case_that_will_not_load_is_summarised_as_failed(self, tmp_path: Path) -> None:
        from decision_lens.evaluation.harness import evaluate_all

        directory, truth = _clone(tmp_path)
        (directory / "case_manifest.json").write_text("{not json", encoding="utf-8")
        truth_root = tmp_path / "truth"
        truth_root.mkdir()
        (truth_root / f"{directory.name}.json").write_text(truth.read_text(), encoding="utf-8")
        lines: list[str] = []
        run = evaluate_all(
            tmp_path, truth_root, ExplodingProvider(), arms=(BASELINE,), progress=lines.append
        )
        assert run.cases[0].error
        assert any("failed:" in line for line in lines)


def test_support_levels_outside_the_known_order_never_invent_a_failure() -> None:
    """Both halves of the guard: an unrecognised claim and an unrecognised ceiling."""
    from decision_lens.evaluation.metrics import CaseScore, RecallResult

    empty = RecallResult(found=(), missed=())
    unknown_claim = CaseScore(
        case_id="c",
        arm="a",
        contradictions=empty,
        gaps_reported=0,
        support_claimed="astonishing",
        support_ceiling="moderate",
    )
    unknown_ceiling = CaseScore(
        case_id="c",
        arm="a",
        contradictions=empty,
        gaps_reported=0,
        support_claimed="strong",
        support_ceiling="unheard_of",
    )
    assert not unknown_claim.overstates_support
    assert not unknown_ceiling.overstates_support


def test_the_progress_line_reports_a_scored_arm_not_only_failures(tmp_path: Path) -> None:
    """The success branch of the summary, which only a working arm exercises."""
    from decision_lens.evaluation.harness import evaluate_all
    from decision_lens.llm import CachedDemoProvider, DemoCache

    recordings = Path("evals/recordings")
    if not recordings.is_dir():
        pytest.skip("no evaluation recordings on disk")
    merged = DemoCache()
    for f in recordings.glob("*.json"):
        if f.stem.startswith("_"):
            continue
        merged.responses.update(DemoCache.load(f).responses)
    if not merged.responses:
        pytest.skip("recordings are empty")
    cache_path = tmp_path / "cache.json"
    merged.save(cache_path)

    directory, truth = _clone(tmp_path)
    truth_root = tmp_path / "truth"
    truth_root.mkdir()
    (truth_root / f"{directory.name}.json").write_text(truth.read_text(), encoding="utf-8")

    lines: list[str] = []
    evaluate_all(
        tmp_path,
        truth_root,
        CachedDemoProvider(cache_path),
        arms=(DECISIONLENS,),
        progress=lines.append,
    )
    assert any("contradictions" in line for line in lines)


def test_an_alternatives_citation_that_resolves_is_counted_valid() -> None:
    """The matching branch of the alternative-citation loop."""
    from decision_lens.evaluation.metrics import score_brief
    from decision_lens.models import Alternative, Citation, OptionKind
    from tests.test_evaluation_metrics import RECORDS, _brief, _truth

    option = Alternative(
        id="OPT-1",
        name="n",
        kind=OptionKind.PROCESS_CHANGE,
        description="d",
        supporting=(Citation(evidence_id="EV-1", quote="87.4 percent"),),
    )
    score = score_brief(_brief(alternatives=(option,)), _truth(), RECORDS)
    assert score.citations_total == 1
    assert score.citation_validity == 1.0

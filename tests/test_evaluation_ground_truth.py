"""The answer key's own schema.

An answer key is the ruler. A malformed one does not produce a bad measurement,
it produces a measurement that looks fine and is meaningless — a metric silently
fed by a field nobody spelled correctly. These tests exist because the previous
arrangement, a loose dict validated by assertions written for one file, could not
have caught that at eleven cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from decision_lens.evaluation import GroundTruth
from decision_lens.evaluation.ground_truth import GapImpact, SpanRef

TRUTH_ROOT = Path("evals/ground_truth")


def _minimal() -> dict[str, object]:
    """The smallest key that is still a valid one."""
    return {
        "case_id": "c",
        "version": "1.0",
        "synthetic": True,
        "notice": "All evidence is synthetic and fictional.",
        "authoring_limitation": "Written by the same person who wrote the corpus.",
        "question": "Which intervention should the team prioritise?",
        "desired_outcome": "Fewer failures.",
        "scoring_rules": {
            "recall_denominator": "must_detect only",
            "unplanted_findings": "adjudicated, never counted wrong by default",
            "span_matching": "same evidence record",
            "restraint_scoring": "overstating support fails restraint",
            "forbidden_claims": "each checked independently",
        },
        "expected_alternative_categories": {},
        "recommendation_restraint": {
            "max_defensible_support_level": "moderate",
            "reason": "Nothing here carries more.",
        },
    }


class TestEveryShippedKeyParses:
    """The real ones, not fixtures. A key that stops parsing stops scoring."""

    @pytest.mark.parametrize("path", sorted(TRUTH_ROOT.glob("*.json")), ids=lambda p: p.stem)
    def test_it_validates(self, path: Path) -> None:
        truth = GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))
        assert truth.case_id == path.stem

    @pytest.mark.parametrize("path", sorted(TRUTH_ROOT.glob("*.json")), ids=lambda p: p.stem)
    def test_it_grades_something(self, path: Path) -> None:
        """A key that grades nothing cannot distinguish the arms."""
        truth = GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))
        assert truth.graded_contradictions() or truth.graded_gaps()

    @pytest.mark.parametrize("path", sorted(TRUTH_ROOT.glob("*.json")), ids=lambda p: p.stem)
    def test_it_anchors_itself_in_the_corpus(self, path: Path) -> None:
        truth = GroundTruth.model_validate_json(path.read_text(encoding="utf-8"))
        assert truth.spans(), "an answer key that quotes nothing asserts without evidence"
        assert truth.sources()


class TestSchemaRefusals:
    def test_a_key_claiming_not_to_be_synthetic_is_rejected(self) -> None:
        """Every case here is invented. One saying otherwise asserts real data."""
        with pytest.raises(ValidationError, match="synthetic"):
            GroundTruth.model_validate({**_minimal(), "synthetic": False})

    def test_an_id_reused_across_two_groups_is_rejected(self) -> None:
        payload = _minimal()
        payload["known_facts"] = [{"id": "GT-1", "statement": "s", "source": "a.md", "span": "x"}]
        payload["known_opinions"] = [
            {
                "id": "GT-1",
                "statement": "s",
                "source": "a.md",
                "span": "x",
                "must_not_be_treated_as": "fact",
            }
        ]
        with pytest.raises(ValidationError, match="GT-1"):
            GroundTruth.model_validate(payload)

    def test_a_contradiction_quoting_one_span_twice_is_rejected(self) -> None:
        side = {"source": "a.md", "span": "x"}
        payload = _minimal()
        payload["expected_contradictions"] = [
            {
                "id": "C1",
                "kind": "k",
                "topic": "t",
                "side_a": side,
                "side_b": dict(side),
                "why_it_matters": "w",
                "how_to_resolve": "r",
            }
        ]
        with pytest.raises(ValidationError, match="same span"):
            GroundTruth.model_validate(payload)

    def test_a_contradiction_without_a_resolution_is_rejected(self) -> None:
        """A conflict nobody can settle is a complaint, not a finding."""
        payload = _minimal()
        payload["expected_contradictions"] = [
            {
                "id": "C1",
                "kind": "k",
                "topic": "t",
                "side_a": {"source": "a.md", "span": "x"},
                "side_b": {"source": "b.md", "span": "y"},
                "why_it_matters": "w",
            }
        ]
        with pytest.raises(ValidationError):
            GroundTruth.model_validate(payload)

    def test_an_unknown_gap_impact_is_rejected(self) -> None:
        payload = _minimal()
        payload["expected_missing_evidence"] = [
            {
                "id": "M1",
                "question": "q",
                "impact": "would_do_something_undefined",
                "why_it_matters": "w",
                "how_to_obtain": "h",
            }
        ]
        with pytest.raises(ValidationError):
            GroundTruth.model_validate(payload)

    def test_an_unrecognised_top_level_key_is_rejected(self) -> None:
        """Silence about a misspelled section is how a metric measures nothing."""
        with pytest.raises(ValidationError):
            GroundTruth.model_validate({**_minimal(), "expected_contradicitons": []})

    def test_a_key_without_its_authoring_limitation_is_rejected(self) -> None:
        """No case may ship pretending to be a neutral held-out measurement."""
        payload = _minimal()
        del payload["authoring_limitation"]
        with pytest.raises(ValidationError):
            GroundTruth.model_validate(payload)


class TestGrading:
    def _with_entries(self) -> GroundTruth:
        payload = _minimal()
        payload["expected_contradictions"] = [
            {
                "id": f"C{n}",
                "kind": "k",
                "topic": "t",
                "side_a": {"source": "a.md", "span": f"a{n}"},
                "side_b": {"source": "b.md", "span": f"b{n}"},
                "why_it_matters": "w",
                "how_to_resolve": "r",
                "must_detect": n == 1,
            }
            for n in (1, 2)
        ]
        payload["expected_missing_evidence"] = [
            {
                "id": f"M{n}",
                "question": "q",
                "impact": GapImpact.WOULD_CHANGE_RECOMMENDATION.value,
                "why_it_matters": "w",
                "how_to_obtain": "h",
                "must_detect": n == 1,
            }
            for n in (1, 2)
        ]
        return GroundTruth.model_validate(payload)

    def test_only_must_detect_entries_are_graded(self) -> None:
        truth = self._with_entries()
        assert [c.id for c in truth.graded_contradictions()] == ["C1"]
        assert [g.id for g in truth.graded_gaps()] == ["M1"]

    def test_spans_reach_both_sides_of_every_contradiction(self) -> None:
        truth = self._with_entries()
        owned = [(owner, ref.span) for owner, ref in truth.spans()]
        assert ("C1", "a1") in owned
        assert ("C1", "b1") in owned

    def test_spans_include_optional_anchors(self) -> None:
        """An anchor quotes the corpus too, so it must be checkable like the rest."""
        payload = _minimal()
        payload["known_assumptions"] = [
            {
                "id": "A1",
                "statement": "s",
                "why_it_is_an_assumption": "w",
                "anchor": {"source": "a.md", "span": "the tempting line"},
            }
        ]
        truth = GroundTruth.model_validate(payload)
        assert ("A1", SpanRef(source="a.md", span="the tempting line")) in truth.spans()

    def test_an_absent_anchor_contributes_no_span(self) -> None:
        payload = _minimal()
        payload["known_assumptions"] = [
            {"id": "A1", "statement": "s", "why_it_is_an_assumption": "w"}
        ]
        assert GroundTruth.model_validate(payload).spans() == ()

    def test_sources_lists_every_file_the_key_relies_on(self) -> None:
        truth = self._with_entries()
        assert truth.sources() == frozenset({"a.md", "b.md"})

    def test_a_key_with_no_entries_grades_nothing_without_erroring(self) -> None:
        truth = GroundTruth.model_validate(_minimal())
        assert truth.graded_contradictions() == ()
        assert truth.graded_gaps() == ()
        assert truth.spans() == ()
        assert truth.sources() == frozenset()


def test_the_shipped_keys_are_the_ones_the_cases_expect() -> None:
    """A key file whose case_id disagrees with its filename would score the wrong case."""
    for path in sorted(TRUTH_ROOT.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["case_id"] == path.stem
        assert Path("data", path.stem).is_dir()

"""Validation of the synthetic sample case and its ground truth.

The corpus and the answer key are two files that must agree. Nothing stops them
drifting apart except these tests, and drift is silent: a ground-truth span that
stops resolving does not raise anywhere, it just quietly stops being checkable.

Two properties matter most and are easy to lose:

*   Every ground-truth span must resolve to **exactly one** record. A span that
    matches two records cannot anchor a citation, and a span that matches none is
    an answer key pointing at nothing.
*   Every evidence record must declare itself synthetic **in its own content**,
    not only in the manifest. A record quoted in a brief travels away from its
    directory.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from decision_lens.connectors import LocalFileEvidenceSource
from decision_lens.models import (
    ContradictionKind,
    EvidenceRecord,
    EvidenceRequest,
    EvidenceType,
    GapImpact,
    Horizon,
    OptionKind,
    SupportLevel,
    UserContext,
)

CASE_DIR = Path("data/sample_delivery_exceptions")
GROUND_TRUTH = Path("evals/ground_truth/sample_delivery_exceptions.json")
MANIFEST = CASE_DIR / "case_manifest.json"


def _load(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return payload


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return _load(MANIFEST)


@pytest.fixture(scope="module")
def ground_truth() -> dict[str, Any]:
    return _load(GROUND_TRUTH)


@pytest.fixture(scope="module")
def records() -> tuple[EvidenceRecord, ...]:
    source = LocalFileEvidenceSource(CASE_DIR)
    request = EvidenceRequest(
        query="", requested_by=UserContext(user_id="pm-test"), max_records=500
    )
    return tuple(source.retrieve(request))


def _spans(node: Any, out: list[tuple[str, str]] | None = None) -> list[tuple[str, str]]:
    """Every {source, span} pair anywhere in the ground truth, at any depth."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if "source" in node and "span" in node:
            out.append((node["source"], node["span"]))
        for value in node.values():
            _spans(value, out)
    elif isinstance(node, list):
        for value in node:
            _spans(value, out)
    return out


class TestCorpusIntegrity:
    def test_every_manifest_entry_exists_on_disk(self, manifest: dict[str, Any]) -> None:
        missing = [name for name in manifest["files"] if not (CASE_DIR / name).is_file()]
        assert missing == []

    def test_every_evidence_file_is_listed_in_the_manifest(self, manifest: dict[str, Any]) -> None:
        on_disk = {
            p.name
            for p in CASE_DIR.iterdir()
            if p.is_file() and p.name != MANIFEST.name and not p.name.startswith(".")
        }
        assert on_disk == set(manifest["files"])

    def test_manifest_evidence_types_are_valid(self, manifest: dict[str, Any]) -> None:
        valid = {e.value for e in EvidenceType}
        bad = {
            n: m["evidence_type"]
            for n, m in manifest["files"].items()
            if m["evidence_type"] not in valid
        }
        assert bad == {}

    def test_the_corpus_loads_without_a_single_skip(self) -> None:
        source = LocalFileEvidenceSource(CASE_DIR)
        source.retrieve(
            EvidenceRequest(query="", requested_by=UserContext(user_id="pm"), max_records=500)
        )
        assert source.diagnostics.skipped == ()
        assert source.diagnostics.files_read == len(json.loads(MANIFEST.read_text())["files"])

    def test_every_record_has_resolvable_metadata(
        self, records: tuple[EvidenceRecord, ...]
    ) -> None:
        for record in records:
            assert record.updated_at is not None, record.id
            assert record.owner, record.id
            assert record.product_area == "delivery", record.id

    def test_record_ids_are_unique(self, records: tuple[EvidenceRecord, ...]) -> None:
        ids = [r.id for r in records]
        assert len(set(ids)) == len(ids)


class TestSyntheticLabelling:
    def test_every_record_declares_itself_synthetic_in_its_own_content(
        self, records: tuple[EvidenceRecord, ...]
    ) -> None:
        # A record quoted in a brief travels away from its directory. The manifest
        # will not be there to explain that the evidence is invented.
        unlabelled = [r.id for r in records if "synthetic" not in r.content.lower()]
        assert unlabelled == []

    def test_the_manifest_carries_the_required_notice(self, manifest: dict[str, Any]) -> None:
        assert manifest["synthetic"] is True
        assert "No real Walmart data is used" in manifest["notice"]

    def test_the_ground_truth_carries_the_required_notice(
        self, ground_truth: dict[str, Any]
    ) -> None:
        assert ground_truth["synthetic"] is True
        assert "No real Walmart data is used" in ground_truth["notice"]

    def test_every_walmart_mention_is_a_disclaimer(self) -> None:
        # The word may appear only to deny use or access, never as a data source.
        for path in [*CASE_DIR.iterdir(), GROUND_TRUTH]:
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "walmart" not in line.lower():
                    continue
                assert "no real walmart data" in line.lower() or "no access" in line.lower(), (
                    f"{path.name}: Walmart referenced outside a disclaimer -> {line[:90]}"
                )


class TestGroundTruthSchema:
    REQUIRED = (
        "case_id",
        "version",
        "synthetic",
        "question",
        "scoring_rules",
        "expected_contradictions",
        "expected_missing_evidence",
        "known_facts",
        "known_assumptions",
        "known_opinions",
        "evidence_hazards",
        "known_constraints",
        "governance_issues",
        "unsupported_claims_the_system_must_not_make",
        "expected_alternative_categories",
        "recommendation_restraint",
    )

    def test_required_sections_present(self, ground_truth: dict[str, Any]) -> None:
        assert [k for k in self.REQUIRED if k not in ground_truth] == []

    def test_case_id_matches_the_manifest(
        self, ground_truth: dict[str, Any], manifest: dict[str, Any]
    ) -> None:
        assert ground_truth["case_id"] == manifest["case_id"]

    def test_question_matches_the_manifest(
        self, ground_truth: dict[str, Any], manifest: dict[str, Any]
    ) -> None:
        assert ground_truth["question"] == manifest["question"]

    def test_all_entry_ids_are_unique(self, ground_truth: dict[str, Any]) -> None:
        ids: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if "id" in node and isinstance(node["id"], str):
                    ids.append(node["id"])
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(ground_truth)
        duplicates = {i for i in ids if ids.count(i) > 1}
        assert duplicates == set()

    def test_contradiction_kinds_are_valid_enum_values(self, ground_truth: dict[str, Any]) -> None:
        valid = {k.value for k in ContradictionKind}
        assert all(c["kind"] in valid for c in ground_truth["expected_contradictions"])

    def test_gap_impacts_are_valid_enum_values(self, ground_truth: dict[str, Any]) -> None:
        valid = {i.value for i in GapImpact}
        assert all(m["impact"] in valid for m in ground_truth["expected_missing_evidence"])

    def test_alternative_kinds_and_horizons_are_valid(self, ground_truth: dict[str, Any]) -> None:
        kinds = {k.value for k in OptionKind}
        horizons = {h.value for h in Horizon}
        supports = {s.value for s in SupportLevel}
        for alt in ground_truth["expected_alternative_categories"]["credible"]:
            assert alt["option_kind"] in kinds, alt["name"]
            assert alt["horizon"] in horizons, alt["name"]
            assert alt["support"] in supports, alt["name"]

    def test_constraint_kinds_map_onto_claim_types(self, ground_truth: dict[str, Any]) -> None:
        allowed = {"technical_constraint", "business_constraint", "governance_constraint"}
        assert all(c["kind"] in allowed for c in ground_truth["known_constraints"])


class TestSpanResolution:
    def test_every_span_resolves_to_exactly_one_record(
        self, ground_truth: dict[str, Any], records: tuple[EvidenceRecord, ...]
    ) -> None:
        # Exactly one, not at least one. A span matching two records cannot
        # anchor a citation; a span matching none is an answer key pointing at
        # nothing. Both fail silently without this test.
        problems: list[str] = []
        for source, span in _spans(ground_truth):
            hits = [r for r in records if r.source_id == source and span in r.content]
            if len(hits) != 1:
                problems.append(f"{source} -> {len(hits)} hits for {span[:60]!r}")
        assert problems == []

    def test_the_ground_truth_actually_references_spans(self, ground_truth: dict[str, Any]) -> None:
        # Guards against a refactor that silently drops every anchor and leaves
        # the test above passing over an empty list.
        assert len(_spans(ground_truth)) >= 30

    def test_every_referenced_source_is_a_real_file(self, ground_truth: dict[str, Any]) -> None:
        for source, _ in _spans(ground_truth):
            assert (CASE_DIR / source).is_file(), source

    def test_no_evidence_file_is_left_unanchored(
        self, ground_truth: dict[str, Any], records: tuple[EvidenceRecord, ...]
    ) -> None:
        # A file the answer key never references cannot be scored. Evidence the
        # system may safely ignore at no cost is evidence the evaluation is blind
        # to - and customer_feedback.csv, where the sampling trap lives, was
        # exactly that until this test existed.
        anchored = {
            r.id
            for source, span in _spans(ground_truth)
            for r in records
            if r.source_id == source and span in r.content
        }
        by_file: dict[str, bool] = {}
        for record in records:
            by_file[record.source_id] = (
                by_file.get(record.source_id, False) or record.id in anchored
            )
        assert [f for f, ok in by_file.items() if not ok] == []


class TestPlantedConditions:
    def test_minimum_contradictions(self, ground_truth: dict[str, Any]) -> None:
        assert len(ground_truth["expected_contradictions"]) >= 3

    def test_minimum_must_detect_gaps(self, ground_truth: dict[str, Any]) -> None:
        required = [m for m in ground_truth["expected_missing_evidence"] if m["must_detect"]]
        assert len(required) >= 4

    def test_contradictions_span_more_than_one_kind(self, ground_truth: dict[str, Any]) -> None:
        kinds = {c["kind"] for c in ground_truth["expected_contradictions"]}
        assert len(kinds) >= 2

    def test_every_contradiction_says_how_to_resolve_it(self, ground_truth: dict[str, Any]) -> None:
        # Reporting a disagreement is less useful than reporting a stale citation.
        assert all(c["how_to_resolve"].strip() for c in ground_truth["expected_contradictions"])

    def test_a_non_ai_alternative_is_expected(self, ground_truth: dict[str, Any]) -> None:
        kinds = {
            a["option_kind"] for a in ground_truth["expected_alternative_categories"]["credible"]
        }
        assert kinds - {"ai_assisted", "ai_automated"}

    def test_a_no_build_defer_or_research_alternative_is_expected(
        self, ground_truth: dict[str, Any]
    ) -> None:
        kinds = {
            a["option_kind"] for a in ground_truth["expected_alternative_categories"]["credible"]
        }
        assert kinds & {"no_change", "defer", "further_research"}

    def test_stakeholder_opinions_are_marked_as_not_evidence(
        self, ground_truth: dict[str, Any]
    ) -> None:
        assert ground_truth["known_opinions"]
        assert all(o["must_not_be_treated_as"].strip() for o in ground_truth["known_opinions"])

    def test_an_irrelevant_item_is_planted(self, ground_truth: dict[str, Any]) -> None:
        assert len(ground_truth["irrelevant_evidence"]) >= 1

    def test_the_sampling_hazard_is_recorded(self, ground_truth: dict[str, Any]) -> None:
        # The feedback skew is what tempts the forbidden overgeneralisation, so
        # it belongs in the answer key rather than only in a design note.
        hazards = {h["id"]: h for h in ground_truth["evidence_hazards"]}
        assert hazards, "no evidence hazards recorded"
        assert any(h["source"] == "customer_feedback.csv" for h in hazards.values())

    def test_the_forbidden_overgeneralisation_names_what_tempts_it(
        self, ground_truth: dict[str, Any]
    ) -> None:
        u3 = next(
            c
            for c in ground_truth["unsupported_claims_the_system_must_not_make"]
            if c["id"] == "GT-U3"
        )
        assert u3["tempted_by"] in {h["id"] for h in ground_truth["evidence_hazards"]}

    def test_governance_and_technical_constraints_both_present(
        self, ground_truth: dict[str, Any]
    ) -> None:
        kinds = {c["kind"] for c in ground_truth["known_constraints"]}
        assert "technical_constraint" in kinds
        assert "business_constraint" in kinds
        assert ground_truth["governance_issues"]

    def test_an_outdated_source_is_present(self, manifest: dict[str, Any]) -> None:
        # Real day arithmetic, not year subtraction: a document updated last
        # December is not a stale source, and comparing years alone says it is.
        as_of = date.fromisoformat(manifest["as_of"])
        ages = {
            name: (as_of - date.fromisoformat(meta["updated_at"])).days
            for name, meta in manifest["files"].items()
        }
        assert max(ages.values()) >= 365, ages

    def test_a_misleading_denominator_is_planted(self) -> None:
        text = (CASE_DIR / "prior_experiments.md").read_text(encoding="utf-8")
        assert "80% of surveyed customers" in text
        assert "sent to 15 customers" in text  # the denominator that undoes the claim

    def test_an_executive_preference_is_planted(self) -> None:
        text = (CASE_DIR / "stakeholder_notes.md").read_text(encoding="utf-8")
        assert "I want the AI exception assistant shipped this quarter." in text


class TestRecommendationRestraint:
    def test_no_single_correct_answer_is_encoded(self, ground_truth: dict[str, Any]) -> None:
        restraint = ground_truth["recommendation_restraint"]
        assert restraint["single_correct_answer"] is False
        assert len(restraint["defensible_next_steps"]) >= 2

    def test_strong_support_is_not_defensible_on_this_evidence(
        self, ground_truth: dict[str, Any]
    ) -> None:
        assert (
            ground_truth["recommendation_restraint"]["max_defensible_support_level"] == "moderate"
        )

    def test_ai_requires_conditions(self, ground_truth: dict[str, Any]) -> None:
        gated = {
            e["option_kind"]
            for e in ground_truth["recommendation_restraint"][
                "must_not_recommend_without_conditions"
            ]
        }
        assert "ai_assisted" in gated


class TestScoringRules:
    def test_scoring_rules_are_stated(self, ground_truth: dict[str, Any]) -> None:
        for key in (
            "recall_denominator",
            "unplanted_findings",
            "span_matching",
            "restraint_scoring",
        ):
            assert ground_truth["scoring_rules"][key].strip()

    def test_unplanted_findings_are_not_automatic_false_positives(
        self, ground_truth: dict[str, Any]
    ) -> None:
        # Scoring an unplanted-but-real finding as wrong would penalise the
        # system for being right, which inverts the metric.
        rule = ground_truth["scoring_rules"]["unplanted_findings"].lower()
        assert "adjudication" in rule or "adjudicated" in rule


class TestCorpusArithmetic:
    """The corpus must contain no contradictions beyond the planted ones.

    An accidental inconsistency would be correctly reported by a capable system
    and then scored against it, because it is absent from the answer key.
    """

    def _tickets(self) -> dict[str, dict[str, int]]:
        rows = list(
            csv.DictReader((CASE_DIR / "support_ticket_summaries.csv").read_text().splitlines())
        )
        seg: dict[str, dict[str, int]] = defaultdict(dict)
        for row in rows:
            seg[row["segment"]][row["exception_category"]] = int(row["ticket_count"])
        return seg

    def test_segments_reconcile_to_the_total_per_category(self) -> None:
        seg = self._tickets()
        for category, total in seg["all"].items():
            parts = seg["apartment"].get(category, 0) + seg["house"].get(category, 0)
            assert parts == total, f"{category}: apartment+house={parts} but all={total}"

    def test_segment_shares_sum_to_one_hundred(self) -> None:
        rows = list(
            csv.DictReader((CASE_DIR / "support_ticket_summaries.csv").read_text().splitlines())
        )
        totals: dict[str, float] = defaultdict(float)
        for row in rows:
            totals[row["segment"]] += float(row["share_of_segment_percent"])
        for segment, total in totals.items():
            assert abs(total - 100.0) < 0.15, f"{segment} shares sum to {total}"

    def test_the_scope_conflict_still_holds(self) -> None:
        seg = self._tickets()
        assert max(seg["all"], key=lambda c: seg["all"][c]) == "access_issue"
        assert max(seg["apartment"], key=lambda c: seg["apartment"][c]) == "address_error"

    def test_the_stale_figure_is_traceable_to_a_real_period(self) -> None:
        # The 91% in the objectives document must be findable in the metrics, or
        # the contradiction is a disagreement rather than a stale citation.
        rows = list(csv.DictReader((CASE_DIR / "product_metrics.csv").read_text().splitlines()))
        historic = {
            r["period"]: r["value"]
            for r in rows
            if r["metric"] == "first_attempt_success" and r["segment"] == "all"
        }
        assert "First-attempt delivery success is currently 91%." in (
            CASE_DIR / "business_objectives.md"
        ).read_text(encoding="utf-8")
        assert historic["2025-Q2"] == "91.0"
        assert historic["2026-Q2"] == "87.4"

    def test_first_attempt_success_declines_monotonically(self) -> None:
        rows = list(csv.DictReader((CASE_DIR / "product_metrics.csv").read_text().splitlines()))
        series = sorted(
            (r["period"], float(r["value"]))
            for r in rows
            if r["metric"] == "first_attempt_success" and r["segment"] == "all"
        )
        values = [v for _, v in series]
        assert values == sorted(values, reverse=True), series

    def test_the_feedback_sample_is_skewed_toward_apartments(self) -> None:
        # The trap: generalising from this sample gives the wrong answer overall.
        rows = list(csv.DictReader((CASE_DIR / "customer_feedback.csv").read_text().splitlines()))
        apartments = sum(1 for r in rows if r["dwelling_type"] == "apartment")
        assert apartments > len(rows) / 2

    def test_no_geographic_breakdown_exists_anywhere(self) -> None:
        # Gap GT-M4 must stay open; a rural split would silently close it.
        for path in CASE_DIR.glob("*.csv"):
            text = path.read_text(encoding="utf-8").lower()
            assert "rural" not in text, path.name

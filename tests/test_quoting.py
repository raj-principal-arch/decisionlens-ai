"""Locating the source text behind a near-verbatim quote.

The line this module has to hold is narrow and the tests are shaped around it.
Forgive typography, because a model rewrites a hyphen without meaning anything
by it. Forgive nothing else, because a quote that has had a digit or a negation
changed is a different claim, and repairing it would manufacture the very thing
this product exists to catch.
"""

from __future__ import annotations

import pytest

from decision_lens.quoting import find_quote, normalise

SOURCE = (
    "First-attempt success in the pilot group was 88.1%, against 87.6% in the comparison group."
)
RECORDS = {"EV-1": SOURCE, "EV-2": "Unrelated text about warehouse staffing levels."}


class TestNormalise:
    def test_the_origin_map_has_one_entry_per_folded_character(self) -> None:
        folded, origin = normalise("A-B  C")
        assert len(folded) == len(origin)

    def test_every_origin_indexes_the_character_it_came_from(self) -> None:
        text = "Some-text  here"
        folded, origin = normalise(text)
        for position, source_index in enumerate(origin):
            original = text[source_index]
            expected = " " if (original.isspace() or original == "-") else original.lower()
            assert folded[position] == expected

    def test_runs_of_whitespace_collapse_to_one_space(self) -> None:
        folded, _ = normalise("a \t\n  b")
        assert folded == "a b"

    def test_a_hyphen_and_a_space_fold_together(self) -> None:
        assert normalise("First-attempt")[0] == normalise("First attempt")[0]

    @pytest.mark.parametrize("dash", ["-", "‐", "‑", "‒", "–", "—", "―", "−"])
    def test_every_dash_a_model_substitutes_folds_the_same(self, dash: str) -> None:
        assert normalise(f"cost{dash}effective")[0] == normalise("cost effective")[0]

    @pytest.mark.parametrize(("fancy", "plain"), [("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')])
    def test_typographic_quote_marks_fold_to_straight_ones(self, fancy: str, plain: str) -> None:
        assert normalise(f"the driver{fancy}s note")[0] == normalise(f"the driver{plain}s note")[0]

    def test_case_is_folded(self) -> None:
        assert normalise("Apartment")[0] == normalise("apartment")[0]

    def test_a_multi_character_lowercase_is_left_alone_to_keep_indices_aligned(self) -> None:
        # 'ß'.lower() is 'ß' but 'ß'.casefold() is 'ss'. Using casefold would slide
        # every index after it and hand back a span short by a character.
        text = "straße"
        folded, origin = normalise(text)
        assert len(folded) == len(text)
        assert origin == list(range(len(text)))

    def test_an_empty_string_normalises_to_nothing(self) -> None:
        assert normalise("") == ("", [])


class TestFindingAnExactQuote:
    def test_an_exact_quote_is_found_and_marked_exact(self) -> None:
        match = find_quote("was 88.1%, against", RECORDS)
        assert match is not None
        assert match.evidence_id == "EV-1"
        assert match.exact
        assert match.text == "was 88.1%, against"

    def test_surrounding_whitespace_is_ignored(self) -> None:
        match = find_quote("   was 88.1%   ", RECORDS)
        assert match is not None
        assert match.text == "was 88.1%"

    def test_a_quote_in_two_records_is_refused(self) -> None:
        records = {"EV-1": "the same sentence here", "EV-2": "and the same sentence here too"}
        assert find_quote("the same sentence", records) is None

    def test_an_empty_quote_is_refused(self) -> None:
        assert find_quote("   ", RECORDS) is None


class TestRepairingTypography:
    def test_the_failure_this_module_was_written_for(self) -> None:
        """A live run was discarded over exactly this: one missing hyphen."""
        match = find_quote("First attempt success in the pilot group was 88.1%, against ", RECORDS)
        assert match is not None
        assert match.evidence_id == "EV-1"
        assert not match.exact
        # The whole point: what comes back is the source's own characters, so the
        # repaired citation is verbatim rather than merely close.
        assert match.text in SOURCE
        assert match.text.startswith("First-attempt")

    def test_the_repaired_text_is_always_a_real_substring_of_the_source(self) -> None:
        for quote in (
            "first attempt success",
            "FIRST-ATTEMPT SUCCESS",
            "First   attempt    success",
            "against 87.6% in the comparison group.",
        ):
            match = find_quote(quote, RECORDS)
            assert match is not None, quote
            assert match.text in SOURCE, quote

    def test_a_curly_apostrophe_in_the_quote_still_finds_a_straight_one(self) -> None:
        records = {"EV-1": "the driver's note said nobody answered"}
        match = find_quote("the driver’s note", records)
        assert match is not None
        assert match.text == "the driver's note"

    def test_a_straight_apostrophe_in_the_quote_still_finds_a_curly_one(self) -> None:
        records = {"EV-1": "the driver’s note said nobody answered"}
        match = find_quote("the driver's note", records)
        assert match is not None
        assert match.text == "the driver’s note"

    def test_a_quote_spanning_a_line_break_is_recovered_with_the_break_intact(self) -> None:
        records = {"EV-1": "delivery exceptions rose\nsharply in the second quarter"}
        match = find_quote("exceptions rose sharply", records)
        assert match is not None
        assert match.text == "exceptions rose\nsharply"


class TestWhatMustNeverBeRepaired:
    """Everything here is a different claim, not a different rendering of one."""

    @pytest.mark.parametrize(
        "quote",
        [
            "First-attempt success in the pilot group was 87.6%",
            "First-attempt success in the pilot group was 8.81%",
            "First-attempt success in the pilot group was not 88.1%",
            "First-attempt failure in the pilot group was 88.1%",
            "First-attempt success in the control group was 88.1%",
            "Second-attempt success in the pilot group was 88.1%",
        ],
    )
    def test_a_changed_meaning_is_not_repaired(self, quote: str) -> None:
        assert find_quote(quote, RECORDS) is None

    def test_text_that_appears_nowhere_is_not_repaired(self) -> None:
        assert find_quote("a sentence nobody ever wrote", RECORDS) is None

    def test_a_typography_match_in_two_records_is_refused(self) -> None:
        # Neither is exact, so there is no basis for choosing between them.
        records = {"EV-1": "a cost-effective option", "EV-2": "a cost—effective option"}
        assert find_quote("a cost effective option", records) is None

    def test_a_typography_match_twice_in_one_record_is_refused(self) -> None:
        records = {"EV-1": "cost-effective, and separately cost—effective"}
        assert find_quote("cost effective", records) is None


class TestExactBeatsApproximate:
    """An exact hit ends the search. Folding is a fallback, not a competitor."""

    def test_an_exact_match_wins_over_a_typographic_variant_elsewhere(self) -> None:
        records = {"EV-1": "cost-effective option", "EV-2": "cost effective option"}
        match = find_quote("cost effective option", records)
        assert match is not None
        assert match.evidence_id == "EV-2"
        assert match.exact

    def test_a_quote_appearing_twice_in_one_record_verbatim_needs_no_repair(self) -> None:
        # It is already verbatim, so `contains` passes and nothing is rewritten.
        # Refusing here would reject a citation that was correct all along.
        records = {"EV-1": "cost effective and also cost effective"}
        match = find_quote("cost effective", records)
        assert match is not None
        assert match.exact
        assert match.text in records["EV-1"]

    def test_a_quote_that_folds_away_to_nothing_is_refused(self) -> None:
        assert find_quote("---", RECORDS) is None

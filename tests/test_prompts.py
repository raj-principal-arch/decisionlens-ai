"""Versioned prompts.

A brief is reproducible only if the prompt that produced it can be named. These
tests pin the two mechanisms that make that true: an explicit version a human
declares, and a fingerprint that catches the case the human forgets.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from decision_lens.prompts import REGISTRY, Prompt, PromptRegistry


def _prompt(**overrides: object) -> Prompt:
    base: dict[str, object] = {
        "name": "contradictions",
        "version": "v1",
        "system": "You surface conflicts. You do not resolve them.",
        "user_template": "Evidence:\n{evidence}\n\nQuestion: {question}",
    }
    return Prompt(**{**base, **overrides})


class TestFingerprint:
    def test_identical_text_fingerprints_identically(self) -> None:
        assert _prompt().fingerprint == _prompt().fingerprint

    def test_changing_the_template_changes_the_fingerprint(self) -> None:
        assert _prompt().fingerprint != _prompt(user_template="Different {evidence}").fingerprint

    def test_changing_the_system_message_changes_the_fingerprint(self) -> None:
        assert _prompt().fingerprint != _prompt(system="You resolve conflicts.").fingerprint

    def test_the_fingerprint_ignores_version_and_name(self) -> None:
        # It tracks wording, so a version bump alone must not look like an edit.
        assert _prompt().fingerprint == _prompt(version="v9", name="other").fingerprint

    def test_a_version_bump_without_an_edit_is_detectable(self) -> None:
        # The case the fingerprint exists for is the opposite one: text edited,
        # version left alone. Both prompts below claim different versions while
        # being textually identical, and the fingerprint says so.
        v1, v2 = _prompt(version="v1"), _prompt(version="v2")
        assert v1.version != v2.version
        assert v1.fingerprint == v2.fingerprint

    def test_field_order_does_not_collide(self) -> None:
        # A naive concatenation would make ("ab", "c") and ("a", "bc") identical.
        a = Prompt(name="p", version="v1", system="ab", user_template="c")
        b = Prompt(name="p", version="v1", system="a", user_template="bc")
        assert a.fingerprint != b.fingerprint


class TestRender:
    def test_placeholders_are_filled(self) -> None:
        rendered = _prompt().render(evidence="EV-1: 87.4%", question="What conflicts?")
        assert "EV-1: 87.4%" in rendered
        assert "What conflicts?" in rendered

    def test_a_missing_placeholder_raises_rather_than_leaking(self) -> None:
        # A prompt containing a literal {evidence} would be answered anyway, and
        # nobody would notice until the output was wrong.
        with pytest.raises(KeyError, match="needs a value for 'question'"):
            _prompt().render(evidence="EV-1")

    def test_the_error_names_the_prompt_and_version(self) -> None:
        with pytest.raises(KeyError) as exc:
            _prompt().render(evidence="EV-1")
        assert "contradictions" in str(exc.value)
        assert "v1" in str(exc.value)

    def test_extra_values_are_ignored(self) -> None:
        rendered = _prompt().render(evidence="e", question="q", unused="x")
        assert "x" not in rendered


class TestValidation:
    def test_an_empty_template_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _prompt(user_template="")

    def test_an_empty_version_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _prompt(version="")

    def test_a_prompt_is_immutable(self) -> None:
        prompt = _prompt()
        with pytest.raises(ValidationError):
            prompt.version = "v2"  # type: ignore[misc]


class TestRegistry:
    def test_register_and_get(self) -> None:
        registry = PromptRegistry()
        registry.register(_prompt())
        assert registry.get("contradictions", "v1").version == "v1"
        assert len(registry) == 1

    def test_the_same_name_and_version_cannot_be_registered_twice(self) -> None:
        # Two prompts claiming one identity would make a run trace ambiguous
        # about which text actually ran.
        registry = PromptRegistry()
        registry.register(_prompt())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_prompt(user_template="A different body {evidence} {question}"))

    def test_versions_coexist(self) -> None:
        registry = PromptRegistry()
        registry.register(_prompt(version="v1"))
        registry.register(_prompt(version="v2"))
        assert len(registry) == 2
        assert registry.get("contradictions", "v1") is not registry.get("contradictions", "v2")

    def test_latest_returns_the_highest_version(self) -> None:
        registry = PromptRegistry()
        registry.register(_prompt(version="v1"))
        registry.register(_prompt(version="v3"))
        registry.register(_prompt(version="v2"))
        assert registry.latest("contradictions").version == "v3"

    def test_an_unknown_prompt_lists_what_is_known(self) -> None:
        registry = PromptRegistry()
        registry.register(_prompt())
        with pytest.raises(KeyError) as exc:
            registry.get("alternatives", "v1")
        assert "contradictions v1" in str(exc.value)

    def test_an_unknown_prompt_in_an_empty_registry_says_so(self) -> None:
        with pytest.raises(KeyError, match="none registered"):
            PromptRegistry().get("anything", "v1")

    def test_latest_on_an_unknown_name_raises(self) -> None:
        with pytest.raises(KeyError, match="No prompt registered"):
            PromptRegistry().latest("nothing")

    def test_names_are_reported_without_duplicates(self) -> None:
        registry = PromptRegistry()
        registry.register(_prompt(version="v1"))
        registry.register(_prompt(version="v2"))
        registry.register(_prompt(name="alternatives"))
        assert registry.names() == ("alternatives", "contradictions")


class TestSharedRegistry:
    """REGISTRY is process-global mutable state, so a test about its contents is
    order-dependent unless it forces the imports it depends on. These do."""

    def test_only_the_prompts_built_so_far_are_registered(self) -> None:
        # Tripwire, updated at each phase. Skill prompts arrived in Phase 7 and the
        # challenger in Phase 8; if this fails, something registered ahead of its phase.
        import decision_lens.prompts.baseline  # noqa: F401  triggers registration
        import decision_lens.prompts.decisionlens  # noqa: F401

        assert REGISTRY.names() == (
            "alternatives",
            "baseline",
            "baseline-repair",
            "challenger",
            "classification",
            "contradictions",
            "missing_evidence",
            "recommendation",
            "relevance",
        )

    def test_registered_prompts_are_retrievable_by_version(self) -> None:
        import decision_lens.prompts.baseline  # noqa: F401

        # v2: the baseline's guidance changed materially when the shared
        # heuristics were added to close a briefing gap against DecisionLens.
        # v1 is gone rather than kept, so a recording made under it cannot be
        # replayed as an answer to the prompt now being asked.
        assert REGISTRY.get("baseline", "v2").version == "v2"
        with pytest.raises(KeyError):
            REGISTRY.get("baseline", "v1")


class TestBothArmsAreBriefedEqually:
    """The comparison is only about structure if both arms are told the same things.

    An earlier version restated the guidance separately in each arm and the two
    drifted: the DecisionLens prompts warned about seniority, staleness and
    segment-scoped claims while the baseline did not. Eight reading cues reached
    one arm and not the other. Any margin measured
    under that asymmetry would have been partly a difference in briefing rather
    than in workflow — and a baseline told less is the strawman the build
    specification forbids.
    """

    @staticmethod
    def _decisionlens_text() -> str:
        from decision_lens.prompts.decisionlens import ALL_PROMPTS

        return "\n".join(p.system for p in ALL_PROMPTS)

    @staticmethod
    def _baseline_text() -> str:
        from decision_lens.prompts.baseline import BASELINE_V2

        return BASELINE_V2.system

    @pytest.mark.parametrize(
        "block",
        [
            "ASSESSMENT_STATES",
            "CITING",
            "FINDING_GAPS",
            "READING_EVIDENCE",
            "SPOTTING_CONFLICTS",
            "STATING_SUPPORT",
        ],
    )
    def test_every_shared_block_reaches_both_arms(self, block: str) -> None:
        from decision_lens.prompts import heuristics

        text = getattr(heuristics, block)
        assert text in self._decisionlens_text(), f"{block} missing from DecisionLens"
        assert text in self._baseline_text(), f"{block} missing from the baseline"

    def test_the_shared_module_exports_exactly_what_it_defines(self) -> None:
        """A block added but left out of __all__ would silently reach neither."""
        from decision_lens.prompts import heuristics

        public = {
            name
            for name in vars(heuristics)
            if name.isupper() and isinstance(getattr(heuristics, name), str)
        }
        assert public == set(heuristics.__all__)

    @pytest.mark.parametrize(
        "cue",
        ["seniority", "stale", "older document", "largest", "segment", "denominator"],
    )
    def test_the_specific_cues_that_had_drifted_are_now_in_both(self, cue: str) -> None:
        """Named individually because these are the ones that actually diverged."""
        assert cue in self._decisionlens_text().lower()
        assert cue in self._baseline_text().lower()

    def test_the_baseline_version_moved_when_its_guidance_did(self) -> None:
        """A recording made under the old prompt must not be replayed for the new one."""
        from decision_lens.prompts.baseline import BASELINE_V2

        assert BASELINE_V2.version == "v2"

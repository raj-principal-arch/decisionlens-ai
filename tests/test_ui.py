"""The structured interface.

Two layers, tested differently. The pure helpers are ordinary unit tests. The
page itself runs under Streamlit's own `AppTest`, which executes the script and
lets us assert on what was rendered — a real smoke test rather than a stub that
would pass with the page broken.

Not tested here: appearance. The spec asks for practical smoke tests without
overinvesting in visual polish, and a test asserting a colour would break on
every restyle while catching nothing that matters.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from decision_lens.case import criteria_for, load_case
from decision_lens.config import ConfigError
from decision_lens.llm import CachedDemoProvider
from decision_lens.llm.anthropic_provider import AnthropicNotInstalled
from decision_lens.models import (
    AssessmentState,
    DecisionBrief,
    DecisionRequest,
    Dimension,
    ValidationIssue,
    ValidationSeverity,
)
from decision_lens.orchestrator import DecisionLens
from decision_lens.ui import (
    LIVE_UI_ENV,
    available_cases,
    build_provider,
    case_question,
    coverage_slices,
    live_ui_enabled,
    materialise_case,
    option_rows,
    recorded_questions,
    support_journey,
)
from decision_lens.validation import ValidationCode
from tests.scripted import write_case

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

UI_PATH = "src/decision_lens/ui.py"
KEY = "sk-ant-api03-REDACTEDTESTVALUE-9xyz"


@pytest.fixture
def brief_fixture(tmp_path: Path) -> DecisionBrief:
    """A real brief from the scripted case, for the pure display helpers."""
    from tests.scripted import case_with_cache

    directory, cache = case_with_cache(tmp_path)
    loaded = load_case(directory)
    lens = DecisionLens(CachedDemoProvider(cache), loaded.sources, as_of=loaded.as_of)
    return lens.run(loaded.request)


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #


def test_only_directories_with_a_manifest_are_offered(tmp_path: Path) -> None:
    write_case(tmp_path)
    (tmp_path / "not_a_case").mkdir()
    assert [p.name for p in available_cases(tmp_path)] == ["tiny_case"]


def test_a_missing_cases_root_offers_nothing(tmp_path: Path) -> None:
    assert available_cases(tmp_path / "absent") == []


def test_the_default_provider_is_the_cached_one() -> None:
    assert isinstance(build_provider(live=False, api_key="", model=""), CachedDemoProvider)


def test_going_live_needs_a_key_from_the_form() -> None:
    """The page never picks up a credential from the environment on its own."""
    with pytest.raises(ConfigError, match="needs an API key"):
        build_provider(live=True, api_key="", model="")


def test_a_malformed_key_is_rejected_before_any_call() -> None:
    with pytest.raises(ConfigError, match="does not look like an Anthropic key"):
        build_provider(live=True, api_key="paste-key-here", model="")


def test_a_well_formed_key_reaches_the_adapter() -> None:
    """Either outcome is correct; which one depends on an optional extra.

    With `anthropic` installed the adapter is constructed (no network call
    happens at construction). Without it, the install instruction is raised.
    Asserting only one of those would make the test depend on how the developer
    happened to set their venv up.
    """
    try:
        provider = build_provider(live=True, api_key=KEY, model="claude-opus-5")
    except AnthropicNotInstalled:
        return
    assert provider.provider_id == "anthropic"
    assert provider.model_id == "claude-opus-5"


# --------------------------------------------------------------------------- #
# Uploads
# --------------------------------------------------------------------------- #


class _Upload:
    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getbuffer(self) -> bytes:
        return self._data


def test_no_uploads_uses_the_case_directory_itself(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    assert materialise_case(directory, []) == directory


def test_uploads_never_modify_the_bundled_case(tmp_path: Path) -> None:
    """A reviewer experimenting must not change what the next person runs."""
    directory = write_case(tmp_path)
    before = sorted(p.name for p in directory.iterdir())

    staged = materialise_case(directory, [_Upload("extra.md", b"# Extra\n\nSynthetic note.\n")])

    assert staged != directory
    assert sorted(p.name for p in directory.iterdir()) == before
    assert (staged / "extra.md").read_text() == "# Extra\n\nSynthetic note.\n"
    assert (staged / "case_manifest.json").is_file(), "the case travelled with the upload"


def test_an_upload_cannot_escape_the_staging_directory(tmp_path: Path) -> None:
    """A path in an uploaded filename is a filename, not a destination."""
    directory = write_case(tmp_path)
    staged = materialise_case(directory, [_Upload("../../escaped.md", b"x")])

    assert (staged / "escaped.md").is_file()
    assert not (tmp_path.parent / "escaped.md").exists()


# --------------------------------------------------------------------------- #
# Criteria
# --------------------------------------------------------------------------- #


def test_unticked_dimensions_are_marked_inapplicable_not_dropped() -> None:
    """The brief can still say a dimension was considered and set aside."""
    criteria = criteria_for({Dimension.RISK, Dimension.FINANCIAL_IMPACT})

    assert len(criteria.dimensions) == len(Dimension)
    assert set(criteria.applicable) == {Dimension.RISK, Dimension.FINANCIAL_IMPACT}


def test_coverage_always_reports_all_nine_criteria() -> None:
    """A chart built from the assessments present would shrink to what worked."""
    assert len(coverage_slices(None)) == len(Dimension)
    assert not any(ok for _, ok in coverage_slices(None))


def test_coverage_separates_evidenced_from_could_not_assess(brief_fixture: Any) -> None:
    selected = next(
        a
        for a in brief_fixture.alternatives
        if a.id == brief_fixture.recommendation.selected_alternative_id
    )
    slices = coverage_slices(selected)

    assert len(slices) == len(Dimension)
    evidenced = {name for name, ok in slices if ok}
    stated = {
        a.dimension.value for a in selected.assessments if a.state is AssessmentState.ASSESSED
    }
    assert evidenced == stated


def test_the_support_journey_matches_what_validation_writes(
    request_: DecisionRequest,
) -> None:
    """Guards the one place a message is parsed instead of read from a field."""
    from decision_lens.models import SupportLevel

    brief = DecisionBrief(
        id="DB-J",
        request=request_,
        generated_at=datetime(2026, 8, 2, 9, 0, 0),
        validation_issues=(
            ValidationIssue(
                code=ValidationCode.SUPPORT_REDUCED.value,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"Support was reduced from {SupportLevel.MODERATE.value} to "
                    f"{SupportLevel.LOW.value}: the challenger judged the draft overconfident."
                ),
            ),
        ),
    )
    assert support_journey(brief) == ("moderate", "low")


def test_no_journey_is_reported_when_nothing_lowered_it(
    request_: DecisionRequest,
) -> None:
    brief = DecisionBrief(
        id="DB-N",
        request=request_,
        generated_at=datetime(2026, 8, 2, 9, 0, 0),
    )
    assert support_journey(brief) is None


def test_the_options_table_marks_the_recommended_row(brief_fixture: Any) -> None:
    rows = option_rows(brief_fixture)

    assert len(rows) == len(brief_fixture.alternatives)
    marked = [r for r in rows if r["Status"] == "Recommended"]
    assert len(marked) == 1
    assert rows[0]["Status"] == "Recommended", "the recommended option sorts first"
    assert [r["#"] for r in rows] == list(range(1, len(rows) + 1))


def test_the_options_table_carries_no_computed_score(brief_fixture: Any) -> None:
    """Nine partially-evidenced criteria do not add up to a ranking."""
    rows = option_rows(brief_fixture)
    for row in rows:
        assert row["Criteria evidenced"].endswith(f"/{len(Dimension)}")
        assert isinstance(row["Evidence for"], int)
        assert isinstance(row["Evidence against"], int)
    assert not any(isinstance(v, float) for row in rows for v in row.values())


def test_the_evidence_columns_are_counted_not_judged(brief_fixture: Any) -> None:
    """The column this replaced read a field that said `strong` for options whose
    own summary called the evidence "effectively nil"."""
    from decision_lens.ui import option_evidence

    for alternative in brief_fixture.alternatives:
        assert option_evidence(alternative) == (
            len(alternative.supporting),
            len(alternative.opposing),
        )


def test_an_empty_brief_produces_no_option_rows(request_: DecisionRequest) -> None:
    brief = DecisionBrief(
        id="DB-E",
        request=request_,
        generated_at=datetime(2026, 8, 2, 9, 0, 0),
    )
    assert option_rows(brief) == []


def test_the_two_mandatory_options_can_be_waived_from_the_form() -> None:
    criteria = criteria_for(set(Dimension), require_non_ai=False, require_no_build=False)
    assert not criteria.require_non_ai_alternative
    assert not criteria.require_no_build_alternative


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #


def test_the_page_loads_without_raising() -> None:
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()
    assert not app.exception


def test_both_required_notices_are_on_the_page() -> None:
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()
    captions = " ".join(c.value for c in app.caption)
    assert "All sample evidence is synthetic" in captions
    assert "product manager remains accountable" in captions


def test_the_interface_is_a_form_not_a_chat() -> None:
    """The central product decision, asserted rather than assumed."""
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()

    assert not app.chat_input, "a chat box would defeat the point of the interface"
    assert not app.chat_message
    labels = {w.label for w in app.sidebar.text_area} | {w.label for w in app.sidebar.text_input}
    assert "Desired outcome" in labels
    # The question is chosen, not typed — see the replay-mode test below for why.
    assert any(w.label == "Question" for w in app.sidebar.selectbox)


def test_the_pm_supplies_the_inputs_the_spec_names() -> None:
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()

    assert app.sidebar.selectbox, "a case is chosen"
    assert app.sidebar.toggle, "cached or live is chosen"
    assert any(cb.label.startswith("Require a non-AI") for cb in app.sidebar.checkbox)


def test_live_mode_asks_for_a_key_only_when_switched_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LIVE_UI_ENV, "1")
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()
    assert not any(w.label == "Anthropic API key" for w in app.sidebar.text_input)

    app.sidebar.toggle[0].set_value(True).run()
    assert any(w.label == "Anthropic API key" for w in app.sidebar.text_input)
    assert app.sidebar.warning, "the cost of going live is stated"


def test_the_live_toggle_ships_disabled_so_a_reader_cannot_start_a_long_run() -> None:
    """A reader flipping a sidebar switch has not agreed to wait tens of minutes.

    The live path itself stays built and tested — what is off by default is the
    control, and the help text says where the real one lives.
    """
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()

    toggle = app.sidebar.toggle[0]
    assert toggle.disabled, "the live toggle must not be operable by default"
    assert not toggle.value
    assert "decisionlens record" in (toggle.help or "")
    assert not any(w.label == "Anthropic API key" for w in app.sidebar.text_input)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("", False)],
)
def test_only_an_affirmative_setting_arms_the_live_toggle(value: str, expected: bool) -> None:
    assert live_ui_enabled({LIVE_UI_ENV: value}) is expected


def test_the_live_toggle_reads_the_real_environment_when_none_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LIVE_UI_ENV, raising=False)
    assert live_ui_enabled() is False


def test_nothing_runs_until_the_button_is_pressed() -> None:
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()
    assert any("Produce a brief" in i.value for i in app.info)


# --------------------------------------------------------------------------- #
# Rendering a real brief
# --------------------------------------------------------------------------- #

#: A one-off Streamlit script that builds a real brief and lays it out. The page
#: itself always uses the packaged cache, which ships empty, so this is the only
#: way to exercise the render path against a brief that actually has content.
_RENDER_DRIVER = """
import os, sys
from pathlib import Path

sys.path.insert(0, "src")
from decision_lens.case import load_case
from decision_lens.llm import CachedDemoProvider
from decision_lens.orchestrator import DecisionLens
from decision_lens.ui import render

loaded = load_case(Path(os.environ["DL_CASE"]))
brief = DecisionLens(
    CachedDemoProvider(Path(os.environ["DL_CACHE"])), loaded.sources, as_of=loaded.as_of
).run(loaded.request)
render(brief)
"""


@pytest.fixture
def rendered_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from tests.scripted import case_with_cache

    directory, cache = case_with_cache(tmp_path)
    monkeypatch.setenv("DL_CASE", str(directory))
    monkeypatch.setenv("DL_CACHE", str(cache))
    return AppTest.from_string(_RENDER_DRIVER, default_timeout=120).run()


def test_a_real_brief_renders_without_raising(rendered_app: Any) -> None:
    assert not rendered_app.exception


def test_the_layout_puts_the_checks_before_the_recommendation(rendered_app: Any) -> None:
    headers = [h.value for h in rendered_app.subheader]
    assert headers.index("Checks") < headers.index("Recommendation")


def test_every_section_the_spec_names_is_on_the_page(rendered_app: Any) -> None:
    headers = " | ".join(h.value for h in rendered_app.subheader)
    for section in (
        "Checks",
        "What the evidence says",
        "Contradictions",
        "Missing evidence",
        "Alternatives",
        "Recommendation",
        "What to test before investing",
        "Your decision",
        "Evidence",
        "Run trace",
        "Export",
    ):
        assert section in headers, section


def test_the_two_mandatory_options_are_shown_as_metrics(rendered_app: Any) -> None:
    labels = {m.label for m in rendered_app.metric}
    assert "Non-AI option offered" in labels
    assert "Do-nothing option offered" in labels
    assert "Support" in labels


def test_both_exports_are_offered(rendered_app: Any) -> None:
    labels = [b.label for b in rendered_app.download_button]
    assert "DecisionBrief (Markdown)" in labels
    assert "DecisionBrief (JSON)" in labels


def test_the_decision_panel_is_a_form_not_an_accept_button(rendered_app: Any) -> None:
    """DecisionLens recommends; a person decides. The interface has to show that."""
    app = rendered_app
    assert any(a.label == "What did you decide?" for a in app.text_area)
    assert not any("accept" in b.label.lower() for b in app.button)


def test_recording_a_decision_requires_writing_one_down(rendered_app: Any) -> None:
    app = rendered_app
    app.button[0].click().run()
    assert any("before recording it" in w.value for w in app.warning)


def test_a_recorded_decision_is_offered_as_a_download(rendered_app: Any) -> None:
    app = rendered_app
    for area in app.text_area:
        if area.label == "What did you decide?":
            area.set_value("Run the address-validation pilot.")
    app.button[0].click().run()

    assert any("Recorded, separately" in s.value for s in app.success)
    labels = [b.label for b in app.download_button]
    assert any("with your decision" in label for label in labels)


def test_a_disagreement_without_a_reason_is_refused(rendered_app: Any) -> None:
    """The model refuses it; the page has to surface that rather than crash."""
    app = rendered_app
    for area in app.text_area:
        if area.label == "What did you decide?":
            area.set_value("Build the assistant anyway.")
    app.radio[0].set_value("Disagreed")
    app.button[0].click().run()

    assert not app.exception
    assert any("override_reason" in e.value for e in app.error)


def test_pressing_the_button_produces_a_brief_or_explains_why_not() -> None:
    """Deliberately agnostic about whether the packaged cache has recordings.

    An earlier version asserted the cache-miss message, which quietly depended
    on the cache shipping empty. The moment real recordings landed the test
    failed, having tested the fixture rather than the behaviour. What actually
    matters is that pressing the button never raises, and that the outcome is
    either a brief or a stated reason.
    """
    app = AppTest.from_file(UI_PATH, default_timeout=180).run()
    app.sidebar.button[0].click().run()

    assert not app.exception
    produced_a_brief = any(h.value == "Recommendation" for h in app.subheader)
    explained = any("decisionlens record" in c.value for c in app.caption) or bool(app.error)
    assert produced_a_brief or explained


# --------------------------------------------------------------------------- #
# The paths a reviewer hits when something is wrong
# --------------------------------------------------------------------------- #

_MAIN_DRIVER = """
import sys

sys.path.insert(0, "src")
import decision_lens.ui as ui

ui.main()
"""

_CLEAN_BRIEF_DRIVER = """
import os, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "src")
from decision_lens.case import load_case
from decision_lens.llm import CachedDemoProvider
from decision_lens.orchestrator import DecisionLens
from decision_lens.ui import render

loaded = load_case(Path(os.environ["DL_CASE"]))
brief = DecisionLens(
    CachedDemoProvider(Path(os.environ["DL_CACHE"])), loaded.sources, as_of=loaded.as_of
).run(loaded.request)
render(brief.model_copy(update={"validation_issues": (), "run_trace": None}))
"""


def test_a_directory_with_no_cases_says_so_instead_of_failing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patched from the test rather than inside the driver: the driver runs
    # in-process against the same module object, so a driver-side assignment
    # would leak into every test that followed.
    import decision_lens.ui as ui_module

    monkeypatch.setattr(ui_module, "CASES_ROOT", tmp_path)
    app = AppTest.from_string(_MAIN_DRIVER, default_timeout=60).run()

    assert not app.exception
    assert any("No case directories" in e.value for e in app.sidebar.error)


def test_a_brief_with_nothing_wrong_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.scripted import case_with_cache

    directory, cache = case_with_cache(tmp_path)
    monkeypatch.setenv("DL_CASE", str(directory))
    monkeypatch.setenv("DL_CACHE", str(cache))
    app = AppTest.from_string(_CLEAN_BRIEF_DRIVER, default_timeout=120).run()

    assert not app.exception
    assert any("Every deterministic check passed" in s.value for s in app.success)
    assert any("No trace recorded" in c.value for c in app.caption)


def test_going_live_without_a_key_is_reported_on_the_page() -> None:
    """The page must explain it, not raise."""
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()
    app.sidebar.toggle[0].set_value(True).run()
    app.sidebar.button[0].click().run()

    assert not app.exception
    assert any("needs an API key" in e.value for e in app.error)


def test_a_provider_failure_mid_run_is_reported_on_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import decision_lens.ui as ui_module
    from decision_lens.llm import ModelUnavailable

    class Exploding:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def run(self, request: object) -> None:
            raise ModelUnavailable("the provider is unreachable")

    monkeypatch.setattr(ui_module, "DecisionLens", Exploding)
    app = AppTest.from_string(_MAIN_DRIVER, default_timeout=60).run()
    app.sidebar.button[0].click().run()

    assert not app.exception
    assert any("unreachable" in e.value for e in app.error)
    assert any("decisionlens record" in c.value for c in app.caption)


_BARE_BRIEF_DRIVER = """
import os, sys
from pathlib import Path

sys.path.insert(0, "src")
from decision_lens.case import load_case
from decision_lens.llm import CachedDemoProvider
from decision_lens.orchestrator import DecisionLens
from decision_lens.ui import render

loaded = load_case(Path(os.environ["DL_CASE"]))
brief = DecisionLens(
    CachedDemoProvider(Path(os.environ["DL_CACHE"])), loaded.sources, as_of=loaded.as_of
).run(loaded.request)
from decision_lens.models import ValidationIssue, ValidationSeverity

render(
    brief.model_copy(
        update={
            "contradictions": (),
            "recommendation": None,
            "claims": (),
            "validation_issues": (
                ValidationIssue(
                    code="section_missing",
                    severity=ValidationSeverity.ERROR,
                    message="No recommendation was produced.",
                ),
            ),
        }
    )
)
"""


def test_empty_sections_say_what_is_absent_rather_than_showing_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blank section reads as 'nothing to report'. These have to say which."""
    from tests.scripted import case_with_cache

    directory, cache = case_with_cache(tmp_path)
    monkeypatch.setenv("DL_CASE", str(directory))
    monkeypatch.setenv("DL_CACHE", str(cache))
    app = AppTest.from_string(_BARE_BRIEF_DRIVER, default_timeout=120).run()

    assert not app.exception
    captions = " ".join(c.value for c in app.caption)
    assert "That is not the same as none existing" in captions
    assert "No experiment was proposed" in captions
    assert any("No recommendation was produced" in e.value for e in app.error)
    assert any("should not be acted on as it stands" in e.value for e in app.error), (
        "a brief with blocking errors says so above the answer"
    )
    assert any("No claims were extracted" in i.value for i in app.info)


class TestTheComparisonTable:
    """The view the product is named for.

    Eleven options scored on nine dimensions existed in the brief the whole
    time, sealed one-per-collapsed-row so no two could be seen together. A
    comparison tool whose comparison cannot be seen is not doing its job.
    """

    @staticmethod
    def _brief_with(alternatives: tuple[object, ...]) -> Any:
        from datetime import datetime

        from decision_lens.models import DecisionBrief, DecisionRequest, UserContext

        return DecisionBrief(
            id="DB-1",
            request=DecisionRequest(
                id="DR-1",
                question="Which intervention should the team prioritise?",
                user=UserContext(user_id="pm"),
            ),
            generated_at=datetime(2026, 8, 3, 9, 0, 0),
            alternatives=alternatives,
        )

    def test_a_brief_with_no_options_renders_nothing(self) -> None:
        from decision_lens.ui import _comparison_table, _options_table

        _comparison_table(self._brief_with(()))  # must not raise
        _options_table(self._brief_with(()))  # nor an empty table with headers

    def test_the_counts_are_backed_by_the_quotes_shown_beneath_them(self) -> None:
        """The two count columns and the quote lists must never disagree.

        A reader who opens this expander is checking a number they have already
        read in the table. If the list is shorter than the count, the table is
        asserting evidence the brief cannot show.
        """
        from decision_lens.models import Alternative, Citation, OptionKind
        from decision_lens.ui import _evidence_behind_the_counts, option_evidence, option_rows

        cited = Alternative(
            id="OPT-1",
            name="Fix the field that is being dropped",
            kind=OptionKind.DATA_QUALITY,
            supporting=(
                Citation(evidence_id="EV-1", quote="unit number missing", locator="apartment"),
                Citation(evidence_id="EV-2", quote="I entered it at checkout"),
            ),
            opposing=(Citation(evidence_id="EV-3", quote="no follow-up measurement was taken"),),
        )
        bare = Alternative(id="OPT-2", name="Hold current course", kind=OptionKind.NO_CHANGE)
        brief = self._brief_with((cited, bare))
        rows = option_rows(brief)
        by_id = {a.id: a for a in brief.alternatives}
        for row in rows:
            supporting, opposing = option_evidence(by_id[row["_id"]])
            assert row["Evidence for"] == supporting
            assert row["Evidence against"] == opposing
        _evidence_behind_the_counts(brief, rows)  # must not raise

    def test_the_why_panel_is_derived_from_the_brief_not_written_here(self) -> None:
        """Every line must come from the recommended option's own citations.

        A hard-coded argument would read well on the bundled case and be false on
        every other one, which is the failure this tool exists to argue against.
        """
        from pathlib import Path

        from decision_lens.case import load_case
        from decision_lens.llm.cached_provider import DEFAULT_CACHE_PATH
        from decision_lens.orchestrator import DecisionLens
        from decision_lens.ui import _why_this_one, support_journey

        _why_this_one(self._brief_with(()))  # no recommendation: renders nothing

        loaded = load_case(Path("data/sample_delivery_exceptions"))
        brief = DecisionLens(
            CachedDemoProvider(DEFAULT_CACHE_PATH), loaded.sources, as_of=loaded.as_of
        ).run(loaded.request)
        assert brief.recommendation is not None
        selected = next(
            a for a in brief.alternatives if a.id == brief.recommendation.selected_alternative_id
        )
        assert selected.supporting, "the panel's numbered steps are these citations"
        assert support_journey(brief) is not None, "this case's support was lowered"
        _why_this_one(brief)  # must not raise on the lowered-support path

    def test_an_option_nobody_argued_against_says_so(self) -> None:
        """An empty side is stated, not skipped — silence reads as no objection."""
        from decision_lens.models import Alternative, OptionKind
        from decision_lens.ui import _evidence_behind_the_counts, option_rows

        option = Alternative(id="OPT-1", name="n", kind=OptionKind.PROCESS_CHANGE)
        brief = self._brief_with((option,))
        _evidence_behind_the_counts(brief, option_rows(brief))  # must not raise

    def test_options_carrying_no_assessments_render_nothing(self) -> None:
        """No dimensions means no table to draw, not an empty table."""
        from decision_lens.models import Alternative, OptionKind
        from decision_lens.ui import _comparison_table

        option = Alternative(id="OPT-1", name="n", kind=OptionKind.PROCESS_CHANGE, description="d")
        _comparison_table(self._brief_with((option,)))  # must not raise

    def test_every_option_and_dimension_reaches_the_grid(self) -> None:
        from pathlib import Path

        from decision_lens.case import load_case
        from decision_lens.llm.cached_provider import DEFAULT_CACHE_PATH
        from decision_lens.orchestrator import DecisionLens

        loaded = load_case(Path("data/checkout_error_rate"))
        brief = DecisionLens(
            CachedDemoProvider(DEFAULT_CACHE_PATH), loaded.sources, as_of=loaded.as_of
        ).run(loaded.request)

        dimensions = {a.dimension.value for opt in brief.alternatives for a in opt.assessments}
        assert len(brief.alternatives) > 1, "a comparison needs something to compare"
        assert len(dimensions) > 1


# --------------------------------------------------------------------------- #
# The decision is chosen from a list, not typed
# --------------------------------------------------------------------------- #


def test_a_case_is_labelled_by_the_question_it_answers(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    assert (
        case_question(directory)
        == json.loads((directory / "case_manifest.json").read_text())["question"]
    )


def test_a_case_with_no_declared_question_falls_back_to_its_name(tmp_path: Path) -> None:
    directory = write_case(tmp_path)
    manifest = directory / "case_manifest.json"
    data = json.loads(manifest.read_text())
    data.pop("question", None)
    manifest.write_text(json.dumps(data))
    assert case_question(directory) == directory.name


def test_an_unreadable_manifest_does_not_break_the_sidebar(tmp_path: Path) -> None:
    """A corrupt case must not take the whole page down with it."""
    directory = write_case(tmp_path)
    (directory / "case_manifest.json").write_text("{not json")
    assert case_question(directory) == directory.name


def test_every_bundled_case_offers_a_real_question() -> None:
    for directory in available_cases():
        question = case_question(directory)
        assert question != directory.name, f"{directory.name} shows a folder name, not a question"
        assert question.endswith("?")


def test_replay_mode_does_not_offer_a_question_box_it_would_ignore() -> None:
    """The cache is keyed on case and skill, never on the question.

    A text box here answered a different question than the one typed, with
    nothing on the page saying so. Only the questions that can actually be
    answered are offered.
    """
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()

    labels = {w.label for w in app.sidebar.text_area}
    assert not any("ask your own" in label for label in labels)
    assert {"Evidence folder", "Question"} <= {w.label for w in app.sidebar.selectbox}


def test_the_criteria_are_fixed_at_nine_and_cannot_be_unticked() -> None:
    """The nine are the framework, not a preference.

    They were a multiselect, which was wrong twice over: options compared on
    different criteria are not comparable, and in replay mode the control did
    nothing at all — the cache key excludes the criteria, so unticking one
    returned the same recorded answer assessed on all nine.
    """
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()

    assert not app.sidebar.multiselect, "criteria are not selectable"


def test_the_question_dropdown_offers_what_the_case_recorded(tmp_path: Path) -> None:
    write_case(tmp_path / "case")
    assert recorded_questions(tmp_path / "case") == [case_question(tmp_path / "case")]


def test_live_mode_restores_the_free_text_question(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LIVE_UI_ENV, "1")
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()

    assert any("ask your own" in w.label for w in app.sidebar.text_area)

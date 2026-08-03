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

from pathlib import Path
from typing import Any

import pytest

from decision_lens.case import criteria_for
from decision_lens.config import ConfigError
from decision_lens.llm import CachedDemoProvider
from decision_lens.llm.anthropic_provider import AnthropicNotInstalled
from decision_lens.models import Dimension
from decision_lens.ui import available_cases, build_provider, materialise_case
from tests.scripted import write_case

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

UI_PATH = "src/decision_lens/ui.py"
KEY = "sk-ant-api03-REDACTEDTESTVALUE-9xyz"


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
    assert "Question" in labels
    assert "Desired outcome" in labels


def test_the_pm_supplies_the_inputs_the_spec_names() -> None:
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()

    assert app.sidebar.selectbox, "a case is chosen"
    assert app.sidebar.multiselect, "criteria are chosen"
    assert app.sidebar.toggle, "cached or live is chosen"
    assert any(cb.label.startswith("Require a non-AI") for cb in app.sidebar.checkbox)


def test_live_mode_asks_for_a_key_only_when_switched_on() -> None:
    app = AppTest.from_file(UI_PATH, default_timeout=60).run()
    assert not any(w.label == "Anthropic API key" for w in app.sidebar.text_input)

    app.sidebar.toggle[0].set_value(True).run()
    assert any(w.label == "Anthropic API key" for w in app.sidebar.text_input)
    assert app.sidebar.warning, "the cost of going live is stated"


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
    assert "Non-AI option" in labels
    assert "No-build / defer option" in labels
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

"""The structured interface a product manager actually uses.

A form with named sections, not a chat box. That is a product decision, not a
styling one: the argument DecisionLens makes is that a PM should be able to
*verify* consequential output quickly, and a conversation is the worst possible
shape for verification — it has no sections to check, no stable place for the
evidence, and no way to see what was left out. Everything here is arranged so a
sceptical reader can find the weak part fast.

Three choices worth naming:

*   **The checks come before the answer.** If a brief has blocking errors, that
    is the first thing on the page. Putting it after the recommendation would put
    it where nobody looks once they have read what they came for.
*   **The PM's decision is a separate panel, below and visually apart.** It is
    not a button labelled "accept". DecisionLens recommends; the person decides;
    the interface should make that boundary obvious without explaining it.
*   **Live is built, and switched off by default.** The provider boundary and the
    key handling are real and tested, but the toggle ships disabled: a seven-stage
    live run takes tens of minutes, and a reader who flips it casually learns that
    the slow way. Setting ``DECISIONLENS_ENABLE_LIVE=1`` re-enables it. Even then
    the key comes from the form, never from the environment, so the page cannot
    spend money the person looking at it did not agree to spend.

This module is intentionally thin. Everything it shows comes from tested code in
:mod:`decision_lens.report`, :mod:`decision_lens.case` and the orchestrator, so
the interface has no analysis of its own to get wrong.

Run it with::

    make ui
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Protocol

import altair as alt
import pandas as pd
import streamlit as st

from decision_lens import report
from decision_lens.case import CaseError, LoadedCase, criteria_for, load_case
from decision_lens.config import ConfigError, Settings
from decision_lens.llm import CachedDemoProvider, ModelError, ModelProvider
from decision_lens.llm.anthropic_provider import AnthropicProvider
from decision_lens.models import (
    DECISION_OWNER_NOTICE,
    SYNTHETIC_DATA_NOTICE,
    Alternative,
    AssessmentState,
    Citation,
    ClaimType,
    DecisionBrief,
    Dimension,
    MetricRole,
    ValidationSeverity,
)
from decision_lens.orchestrator import DecisionLens, DecisionLensError, record_pm_decision
from decision_lens.recorder import LIVE_SKILL_TIMEOUT_SECONDS
from decision_lens.skills import SKILL_TIMEOUT_SECONDS
from decision_lens.validation import ValidationCode

CASES_ROOT = Path("data")
DEFAULT_MODEL = "claude-opus-5"

#: Environment variable that re-enables the live toggle in the sidebar.
#:
#: The live path is built and tested; what ships disabled is the *button*. A
#: seven-stage live run is tens of minutes of sequential model calls, and a
#: reader who flips a toggle in a sidebar has not agreed to wait that long or to
#: pay for it. Recording is a deliberate act performed once at the command line
#: (``decisionlens record``); the browser replays what that produced.
LIVE_UI_ENV = "DECISIONLENS_ENABLE_LIVE"


# --------------------------------------------------------------------------- #
# Pure helpers — no Streamlit, so they are testable without a browser
# --------------------------------------------------------------------------- #


def available_cases(root: Path | None = None) -> list[Path]:
    """Case directories that can be run.

    `root` defaults to `CASES_ROOT` at call time rather than through a default
    argument. A default argument would bind the module constant at import, so
    pointing the app at a different directory would silently have no effect.
    """
    resolved = root if root is not None else CASES_ROOT
    if not resolved.is_dir():
        return []
    return sorted(
        p for p in resolved.iterdir() if p.is_dir() and (p / "case_manifest.json").is_file()
    )


class Upload(Protocol):
    """The part of Streamlit's uploaded-file object this module uses."""

    name: str

    def getbuffer(self) -> Any: ...


def materialise_case(directory: Path, uploads: Sequence[Upload]) -> Path:
    """Return a directory holding the case plus any uploaded files.

    Uploads go into a throwaway copy rather than the bundled case: a reviewer
    experimenting in the browser must not be able to modify the evidence that
    ships with the repository, or the next person's run would silently differ.
    """
    if not uploads:
        return directory
    staged = Path(tempfile.mkdtemp(prefix="decisionlens-case-")) / directory.name
    shutil.copytree(directory, staged)
    for upload in uploads:
        (staged / Path(upload.name).name).write_bytes(bytes(upload.getbuffer()))
    return staged


def case_question(directory: Path) -> str:
    """The question a case was built to answer, or its name if it declares none.

    Read straight from the manifest rather than from a table kept here, so a case
    added to `data/` shows up with its real question and no second place to edit.
    """
    manifest = directory / "case_manifest.json"
    try:
        declared = json.loads(manifest.read_text(encoding="utf-8")).get("question")
    except (OSError, ValueError):
        return directory.name
    return str(declared).strip() if declared else directory.name


def recorded_questions(directory: Path) -> list[str]:
    """The questions this case has recorded output for.

    One per case today, because the cache is keyed on case, skill and prompt
    version — so a case carries exactly the question it was recorded against.
    Returned as a list anyway: the shape is what changes when a case is recorded
    against more than one question, and a caller written against a list does not
    have to change with it.
    """
    return [case_question(directory)]


def coverage_slices(alternative: Alternative | None) -> tuple[tuple[str, bool], ...]:
    """Every one of the nine criteria, and whether evidence was found for it.

    All nine are returned whether or not the option carries an assessment for
    them, because a criterion the model never mentioned and a criterion it
    explicitly could not assess are the same fact to a reader: no evidence. A
    chart built only from the assessments present would silently shrink to the
    criteria that happened to work.
    """
    if alternative is None:
        return tuple((d.value, False) for d in Dimension)
    evidenced = {
        a.dimension for a in alternative.assessments if a.state is AssessmentState.ASSESSED
    }
    return tuple((d.value, d in evidenced) for d in Dimension)


#: Matches the sentence :func:`~decision_lens.validation.enforce_support_ceiling`
#: writes when it lowers a support level. Parsing a message is fragile in
#: general; it is safe here because that sentence is built in exactly one place,
#: and `test_the_support_journey_matches_what_validation_writes` fails if the
#: wording drifts.
_REDUCED = re.compile(r"Support was reduced from (\w+) to (\w+)")


def support_journey(brief: DecisionBrief) -> tuple[str, str] | None:
    """What the recommendation stage claimed, and what it was cut to.

    ``None`` when nothing lowered it — which is the honest rendering of "the
    challenger looked and had no objection", not of "the challenger did not run".
    """
    for issue in brief.validation_issues:
        if issue.code == ValidationCode.SUPPORT_REDUCED.value:
            found = _REDUCED.search(issue.message)
            if found:  # pragma: no branch - the code and the wording ship together
                return found.group(1), found.group(2)
    return None


def option_evidence(alternative: Alternative) -> tuple[int, int]:
    """Citations for this option, and citations against it.

    Counted, not judged. An earlier version of this column read the option's
    ``evidence_confidence`` support level instead, which was wrong in a way worth
    recording: that field carried ``strong`` for options whose own summary said
    the evidence was *"effectively nil"*. The model had used it to mean "I am
    confident in this assessment", not "the evidence is good", and nothing
    validated either reading. These two numbers cannot drift from their label —
    every citation counted here has already been resolved against source text.
    """
    return len(alternative.supporting), len(alternative.opposing)


def option_rows(brief: DecisionBrief) -> list[dict[str, Any]]:
    """One row per option, recommended first, then best-supported.

    Carries no composite score. `Criteria evidenced` counts how many of the nine
    stand on evidence; it measures how much is *known* about an option, never how
    good the option is. The sort follows the same rule, which is why the columns
    and the ordering agree and neither claims to rank value.
    """
    selected = brief.recommendation.selected_alternative_id if brief.recommendation else ""

    def sort_key(alternative: Alternative) -> tuple[int, int, int]:
        supporting, opposing = option_evidence(alternative)
        return (
            0 if alternative.id == selected else 1,
            -(supporting - opposing),
            -sum(1 for _, ok in coverage_slices(alternative) if ok),
        )

    rows: list[dict[str, Any]] = []
    for position, alternative in enumerate(sorted(brief.alternatives, key=sort_key), start=1):
        supporting, opposing = option_evidence(alternative)
        evidenced = sum(1 for _, ok in coverage_slices(alternative) if ok)
        rows.append(
            {
                "#": position,
                "Possible feature to build": alternative.name,
                "Kind of change": alternative.kind.value.replace("_", " "),
                "Evidence for": supporting,
                "Evidence against": opposing,
                "Criteria evidenced": f"{evidenced}/{len(Dimension)}",
                "Status": "Recommended" if alternative.id == selected else "",
                "_why_not": alternative.why_not_selected,
                "_id": alternative.id,
            }
        )
    return rows


def live_ui_enabled(env: dict[str, str] | None = None) -> bool:
    """Whether the sidebar's live toggle is operable.

    Off unless deliberately switched on. Anything other than an affirmative value
    reads as off, so a stray or empty setting cannot quietly arm a path that
    spends money and takes tens of minutes.
    """
    source = os.environ if env is None else env
    return source.get(LIVE_UI_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def build_provider(
    live: bool, api_key: str, model: str, cache_path: Path | None = None
) -> ModelProvider:
    """Cached unless the operator asked for live *and* supplied a key.

    The key comes from the form, not from the environment. A page that quietly
    used an exported credential would spend money the person looking at it never
    agreed to spend. `require_anthropic_key` still checks the shape, so a pasted
    placeholder fails here instead of after a round trip.
    """
    if not live:
        return CachedDemoProvider(cache_path)
    key = Settings(anthropic_api_key=api_key).require_anthropic_key()
    return AnthropicProvider(key, model=model or DEFAULT_MODEL)


def severity_counts(brief: DecisionBrief) -> tuple[int, int]:
    errors = sum(1 for i in brief.validation_issues if i.severity is ValidationSeverity.ERROR)
    warnings = sum(1 for i in brief.validation_issues if i.severity is ValidationSeverity.WARNING)
    return errors, warnings


# --------------------------------------------------------------------------- #
# Sidebar — the PM's inputs
# --------------------------------------------------------------------------- #


def _sidebar() -> dict[str, Any]:
    st.sidebar.title("DecisionLens")
    st.sidebar.caption("Evidence-grounded decision support")

    cases = available_cases()
    if not cases:
        st.sidebar.error(f"No case directories under {CASES_ROOT}/")
        st.stop()

    live_available = live_ui_enabled()

    # The decision comes first, and it is a list rather than a text box.
    #
    # A free-text question was worse than useless when replaying: the cache is
    # keyed on case, skill and prompt version and deliberately not on the
    # question, so anything typed here was silently ignored and the brief
    # answered the case's own question instead. The reader got a confident
    # answer to a question they had not asked, with nothing on the page saying
    # so — the exact failure this product exists to prevent.
    #
    # Offering only the questions that can actually be answered removes the
    # trap. It also reads the way a PM thinks: pick the decision, not the folder.
    st.sidebar.subheader("The decision")
    directory = st.sidebar.selectbox(
        "Evidence folder",
        cases,
        format_func=lambda p: p.name.replace("_", " "),
        help="Each folder is a self-contained case: evidence files plus a manifest.",
    )
    questions = recorded_questions(directory)
    st.sidebar.selectbox(
        "Question",
        questions,
        help="The question this folder has recorded output for.",
    )
    st.sidebar.caption(
        f"`data/{directory.name}/` · {len(questions)} recorded question. "
        "The cache is keyed on the case, so this is the only question this "
        "folder can answer offline."
    )

    # Directly under the two things it acts on, and above every optional field.
    #
    # It sat at the foot of the sidebar, below the uploader, two text boxes and
    # three settings — so the one control that does anything was the last thing
    # found. Everything below this line has a working default; a reader who
    # changes nothing should not have to scroll past all of it to start.
    run = st.sidebar.button("Examine this decision", type="primary", width="stretch")
    st.sidebar.caption("Everything below is optional.")
    st.sidebar.divider()

    question = ""
    if live_available:
        question = st.sidebar.text_area(
            "…or ask your own (live mode only)",
            height=80,
            placeholder="Leave blank to use the question above",
        )

    uploaded = st.sidebar.file_uploader(
        "…or add synthetic files to it",
        accept_multiple_files=True,
        help="Files are added to the selected case for this session only. Synthetic data only.",
    )
    outcome = st.sidebar.text_area(
        "Desired outcome", height=80, placeholder="Leave blank to use the case's"
    )
    product_area = st.sidebar.text_input(
        "Product area", placeholder="Leave blank to use the case's"
    )

    # All nine, always, and not selectable.
    #
    # They were a multiselect defaulting to three, on the reasoning that each
    # criterion costs one written assessment per option. Two things were wrong
    # with that. The nine *are* the framework — an option compared on three
    # criteria is not comparable to one compared on nine, and the whole claim of
    # this product is that every option meets the same fixed bar. And in replay
    # mode the control did not even work: `LLMRequest.cache_key` is
    # `case::skill::prompt_version`, so unticking a criterion changed the prompt
    # and got back the same recorded answer, assessed on all nine. The reader was
    # shown a control that silently did nothing — the same trap already removed
    # from the free-text question box.
    st.sidebar.subheader("Criteria")
    st.sidebar.caption(
        "All nine, always. They are the framework, not a preference — options "
        "compared on different criteria are not comparable."
    )
    dimensions = set(Dimension)
    require_non_ai = st.sidebar.checkbox("Require a non-AI option", value=True)
    require_no_build = st.sidebar.checkbox("Require a no-build / defer option", value=True)

    st.sidebar.subheader("Model")
    live = st.sidebar.toggle(
        "Use a live model",
        value=False,
        disabled=not live_available,
        help=(
            "Off replays recorded output: free, offline, identical every run."
            if live_available
            else "Disabled in this build. The page replays recorded runs — instant and "
            "free. A live run is seven sequential model calls over tens of minutes; "
            "record one at the command line with `decisionlens record`."
        ),
    )
    api_key = ""
    model = DEFAULT_MODEL
    if live:
        st.sidebar.warning("Live mode calls a real model and is billed to the key you paste.")
        api_key = st.sidebar.text_input("Anthropic API key", type="password")
        model = st.sidebar.text_input("Model", value=DEFAULT_MODEL)

    return {
        "directory": directory,
        "uploaded": uploaded or [],
        "question": question.strip(),
        "outcome": outcome.strip(),
        "product_area": product_area.strip(),
        "dimensions": dimensions,
        "require_non_ai": require_non_ai,
        "require_no_build": require_no_build,
        "live": live,
        "api_key": api_key,
        "model": model,
        "run": run,
    }


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _checks(brief: DecisionBrief) -> None:
    errors, warnings = severity_counts(brief)
    st.subheader("Checks")

    if errors:
        st.error(f"{errors} error(s). This brief should not be acted on as it stands.")
    elif warnings:
        st.warning(f"Every blocking check passed. {warnings} warning(s) worth reading.")
    else:
        st.success("Every deterministic check passed.")

    if not brief.validation_issues:
        return
    with st.expander(f"All {len(brief.validation_issues)} finding(s)", expanded=bool(errors)):
        for issue in brief.validation_issues:
            marker = "🔴" if issue.severity is ValidationSeverity.ERROR else "🟡"
            st.markdown(f"{marker} `{issue.code}` — {issue.message}")


def _evidence_says(brief: DecisionBrief) -> None:
    st.subheader("What the evidence says")
    if not brief.claims:
        st.info("No claims were extracted.")
        return

    groups = (
        ("Facts", (ClaimType.FACT,)),
        ("Assumptions", (ClaimType.ASSUMPTION,)),
        ("Opinions", (ClaimType.STAKEHOLDER_OPINION,)),
        (
            "Constraints",
            (
                ClaimType.TECHNICAL_CONSTRAINT,
                ClaimType.BUSINESS_CONSTRAINT,
                ClaimType.GOVERNANCE_CONSTRAINT,
            ),
        ),
    )
    tabs = st.tabs(
        [
            f"{label} ({sum(1 for c in brief.claims if c.claim_type in kinds)})"
            for label, kinds in groups
        ]
    )
    for tab, (_, kinds) in zip(tabs, groups, strict=True):
        with tab:
            selected = [c for c in brief.claims if c.claim_type in kinds]
            if not selected:
                st.caption("None identified.")
            for claim in selected:
                cites = " ".join(f"`{c.evidence_id}`" for c in claim.citations) or "_uncited_"
                st.markdown(f"- {claim.statement} {cites}")
                if claim.rationale:
                    st.caption(f"    {claim.rationale}")


def _contradictions(brief: DecisionBrief) -> None:
    st.subheader(f"Contradictions ({len(brief.contradictions)})")
    if not brief.contradictions:
        st.caption("None found. That is not the same as none existing.")
        return
    st.caption("Reported unresolved. DecisionLens does not pick a side.")
    for found in brief.contradictions:
        with st.expander(f"{found.topic} · {found.kind.value}"):
            st.markdown(f"**One side** `{found.side_a.evidence_id}` — “{found.side_a.quote}”")
            st.markdown(f"**The other** `{found.side_b.evidence_id}` — “{found.side_b.quote}”")
            if found.summary:
                st.markdown(found.summary)
            st.info(f"What would settle it: {found.how_to_resolve}")


def _gaps(brief: DecisionBrief) -> None:
    st.subheader(f"Missing evidence ({len(brief.missing_evidence)})")
    st.caption("Evidence that does not exist is as decision-relevant as evidence that does.")
    for gap in brief.missing_evidence:
        with st.expander(f"{gap.question} · {gap.impact.value}"):
            st.markdown(f"**Why it matters** — {gap.why_it_matters}")
            if gap.how_to_obtain:
                st.markdown(f"**How to get it** — {gap.how_to_obtain}")
            st.caption(
                "Searched, not found."
                if gap.was_searched
                else "No source of this kind is connected."
            )


def _comparison_table(brief: DecisionBrief) -> None:
    """Every option against every criterion, in one grid.

    This is the view the product is named for and it was the one thing the
    interface would not show. The assessments existed — eleven options scored on
    nine dimensions — but each option was sealed inside its own collapsed row, so
    a reader could see one option at a time and never compare two. A comparison
    tool whose comparison cannot be seen is not doing its job.

    Deliberately no composite score. The cell says whether the dimension could be
    assessed at all, because "we could not tell" is the answer a ranking would
    erase, and it is usually the more useful one.
    """
    if not brief.alternatives:
        return

    dimensions: list[str] = []
    for alternative in brief.alternatives:
        for assessment in alternative.assessments:
            name = assessment.dimension.value
            if name not in dimensions:
                dimensions.append(name)
    if not dimensions:
        return

    selected = brief.recommendation.selected_alternative_id if brief.recommendation else ""
    header = "| Option | " + " | ".join(d.replace("_", " ") for d in dimensions) + " |"
    rule = "| --- " * (len(dimensions) + 1) + "|"
    rows = [header, rule]
    for alternative in brief.alternatives:
        by_dimension = {a.dimension.value: a.state.value for a in alternative.assessments}
        cells = []
        for dimension in dimensions:
            state = by_dimension.get(dimension)
            if state is None:
                cells.append("—")
            elif state == "assessed":
                cells.append("●")
            else:
                cells.append("·")
        mark = " ←" if alternative.id == selected else ""
        name = alternative.name if len(alternative.name) <= 46 else alternative.name[:45] + "…"
        rows.append(f"| {name}{mark} | " + " | ".join(cells) + " |")

    st.markdown("\n".join(rows))
    st.caption(
        "● assessed from evidence · · could not be assessed · ← recommended. "
        "No score is computed: the dimensions are not commensurable, and a "
        "composite number would hide which cells are empty."
    )


def _alternatives(brief: DecisionBrief) -> None:
    """The option list, and only the option list, open by default.

    This table is what the product is for: eleven options against one fixed bar,
    comparable at a glance. The dot grid and the per-option reasoning are a click
    away — both are reference material a reader reaches for after a row has
    caught their eye, not before.
    """
    st.subheader(f"Alternatives ({len(brief.alternatives)})")
    # Two guarantees, not two statistics. The brief is rejected without either,
    # so what these report is that the check ran and passed — which is why they
    # say what was required rather than just "yes".
    left, right = st.columns(2)
    left.metric(
        "Non-AI option offered",
        "yes" if brief.has_non_ai_alternative else "MISSING",
        help=(
            "**A way to fix this without using AI.**\n\n"
            "Ask AI for options and it suggests AI ones — like asking a car "
            "salesman how to get to work. He will never say *take the bus*.\n\n"
            "So every brief must contain at least one option that solves the "
            "problem with no AI in it. Without one the brief is **rejected in "
            "code**, not warned about.\n\n"
            "It matters because a list of only-AI options makes *the best option* "
            "mean *the best AI option* — the answer is assumed before anything is "
            "compared. In this case the non-AI option won and both AI options "
            "came last."
        ),
    )
    right.metric(
        "Do-nothing option offered",
        "yes" if brief.has_no_build_alternative else "MISSING",
        help=(
            "**The option to change nothing.**\n\n"
            "Build nothing, defer it, or go and research it first. Doing nothing "
            "is always genuinely available, and is sometimes the right call — but "
            "if it is not written on the list, nobody weighs it.\n\n"
            "Listing it makes doing nothing a visible decision with its own "
            "evidence, rather than what happens when no one chooses. Also "
            "**enforced in code**: no such option, no brief.\n\n"
            "Here it is *Hold current course*, and the evidence argues against "
            "it — first-attempt success has fallen every quarter for five "
            "quarters."
        ),
    )
    st.caption(
        "Both are **required**, not counted. Asking a model nicely for a no-build "
        "option is a hope; rejecting the brief when it is missing is a guarantee."
    )

    _options_table(brief)

    with st.expander(f"Every option against every criterion ({len(Dimension)} criteria)"):
        _comparison_table(brief)

    selected = brief.recommendation.selected_alternative_id if brief.recommendation else ""
    with st.expander("The reasoning behind each option"):
        for alternative in brief.alternatives:
            label = f"{alternative.name} · {alternative.kind.value}"
            st.markdown(f"**{label}**" + ("  ← recommended" if alternative.id == selected else ""))
            if alternative.description:
                st.markdown(alternative.description)
            for assessment in alternative.assessments:
                st.markdown(
                    f"- **{assessment.dimension.value}** — {assessment.state.value}: "
                    f"{assessment.summary or '_no summary_'}"
                )
            if alternative.why_not_selected:
                st.caption(f"Not selected: {alternative.why_not_selected}")


def _selected_alternative(brief: DecisionBrief) -> Alternative | None:
    if brief.recommendation is None:
        return None
    wanted = brief.recommendation.selected_alternative_id
    return next((a for a in brief.alternatives if a.id == wanted), None)


#: Evidenced, and not. The only two colours on the page that carry meaning, so
#: nothing else is allowed to use them.
_EVIDENCED = "#3FBFA5"
_BLANK = "#3A4150"

CSS = """
<style>
  .block-container { padding-top: 2.4rem; max-width: 1180px; }
  h1, h2, h3 { letter-spacing: -0.02em; }
  [data-testid="stMetric"] {
      background: #161A22;
      border: 1px solid #242A36;
      border-radius: 12px;
      padding: 1rem 1.15rem;
  }
  [data-testid="stMetricLabel"] p {
      font-size: .74rem !important;
      letter-spacing: .12em;
      text-transform: uppercase;
      color: #8B93A5 !important;
  }
  [data-testid="stMetricValue"] { font-size: 1.9rem; }
  .dl-hero {
      display: flex; align-items: baseline; gap: .9rem; flex-wrap: wrap;
      border-bottom: 1px solid #242A36; padding-bottom: 1rem; margin-bottom: 1.4rem;
  }
  .dl-hero h1 { font-size: 1.7rem; margin: 0; font-weight: 640; }
  .dl-hero .dl-case {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: .8rem; color: #8B93A5;
      background: #161A22; border: 1px solid #242A36;
      border-radius: 6px; padding: .18rem .55rem;
  }
  .dl-card {
      background: #161A22; border: 1px solid #242A36;
      border-radius: 12px; padding: 1.15rem 1.3rem;
  }
  .dl-card h4 { margin: 0 0 .55rem 0; font-size: .74rem; letter-spacing: .12em;
      text-transform: uppercase; color: #8B93A5; font-weight: 600; }
  .dl-chip {
      display: inline-block; font-size: .74rem; border-radius: 999px;
      padding: .16rem .6rem; margin: 0 .3rem .35rem 0;
      border: 1px solid #242A36; color: #C3C9D6;
  }
  .dl-chip.on  { border-color: rgba(63,191,165,.45); color: #7FD9C6;
                 background: rgba(63,191,165,.10); }
  .dl-chip.off { color: #7B8496; }
  .dl-eyebrow {
      font-size: .74rem; letter-spacing: .12em; text-transform: uppercase;
      color: #8B93A5; margin: 2.2rem 0 .5rem 0;
  }
  .dl-table {
      width: 100%; border-collapse: collapse; margin: .3rem 0 .2rem 0;
      font-size: .93rem; table-layout: fixed;
  }
  .dl-table th {
      text-align: left; font-size: .72rem; letter-spacing: .1em;
      text-transform: uppercase; color: #8B93A5; font-weight: 600;
      padding: .55rem .7rem; border-bottom: 1px solid #2E3542; vertical-align: bottom;
  }
  .dl-table td {
      padding: .7rem; border-bottom: 1px solid #1E2430; vertical-align: top;
      color: #D7DBE4; word-wrap: break-word;
  }
  .dl-table td.c, .dl-table th.c { text-align: center; }
  .dl-table td.dim { color: #8B93A5; }
  .dl-table tbody tr:hover { background: #14181F; }
  .dl-table tr.rec { background: rgba(63,191,165,.06); }
  .dl-table tr.rec td { border-bottom-color: rgba(63,191,165,.20); }
  .dl-table td strong { color: #E6E8EE; font-weight: 600; }
  section[data-testid="stSidebar"] { border-right: 1px solid #242A36; }
  div[data-testid="stExpander"] details {
      border: 1px solid #242A36; border-radius: 10px; background: #12161D;
  }
</style>
"""


def _style() -> None:
    """One stylesheet, applied once.

    Streamlit's defaults are built for dashboards that are scanned, not for a
    document that is argued with. The overrides here do one thing: make the two
    states that carry meaning — evidenced, and not — legible at a glance, and
    stop everything else from competing with them.
    """
    st.markdown(CSS, unsafe_allow_html=True)


def _coverage_chart(slices: tuple[tuple[str, bool], ...]) -> alt.LayerChart:
    """A labelled doughnut: nine equal segments, named on the ring.

    Equal segments rather than two proportional arcs, because the nine criteria
    are the framework and a reader should see all nine whether or not evidence
    reached them. The count sits in the hole so the headline figure is readable
    without counting segments, and every segment carries its own name so the
    chart does not depend on a legend to be understood.
    """
    # Evidenced segments first, then the blanks, so the ring reads as one solid
    # arc of what is known against one of what is not — rather than nine
    # alternating slices a reader has to count.
    ordered = sorted(slices, key=lambda s: (not s[1], s[0]))
    frame = pd.DataFrame(
        [
            {
                "Criterion": name.replace("_", " "),
                "State": "Evidenced" if ok else "No evidence",
                "n": 1,
                "Order": position,
            }
            for position, (name, ok) in enumerate(ordered)
        ]
    )

    base = alt.Chart(frame).encode(
        theta=alt.Theta("n:Q", stack=True),
        order=alt.Order("Order:Q"),
        color=alt.Color(
            "State:N",
            scale=alt.Scale(domain=["Evidenced", "No evidence"], range=[_EVIDENCED, _BLANK]),
            legend=alt.Legend(title=None, orient="bottom", labelColor="#C3C9D6"),
        ),
    )
    ring = base.mark_arc(
        innerRadius=52, outerRadius=82, stroke="#0E1015", strokeWidth=3, cornerRadius=2
    ).encode(tooltip=["Criterion:N", "State:N"])
    # `limit=0` is Vega for "do not truncate". At 120 the longest criterion —
    # strategic customer importance — came out as "strategic customer imp…",
    # which reads as a rendering fault rather than a label.
    labels = base.mark_text(radius=104, fontSize=9.5, limit=0).encode(
        text="Criterion:N", color=alt.value("#98A0B0")
    )
    evidenced = sum(1 for _, ok in slices if ok)
    middle = (
        alt.Chart(pd.DataFrame([{"t": f"{evidenced}/{len(Dimension)}"}]))
        .mark_text(fontSize=28, fontWeight=700, color="#E6E8EE", dy=-5)
        .encode(text="t:N")
    )
    caption = (
        alt.Chart(pd.DataFrame([{"t": "criteria evidenced"}]))
        .mark_text(fontSize=11, color="#8B93A5", dy=22)
        .encode(text="t:N")
    )
    # The heading is rendered above the chart in HTML rather than as a Vega
    # title: a Vega title is laid out inside the plot box, so a long one is
    # clipped by the container instead of wrapping.
    chart = (
        alt.layer(ring, labels, middle, caption)
        .properties(height=300, padding={"top": 8, "bottom": 8, "left": 30, "right": 30})
        .configure_view(stroke=None)
        .configure_legend(labelColor="#C3C9D6", symbolSize=90, labelFontSize=12)
    )
    assert isinstance(chart, alt.LayerChart)  # noqa: S101 - narrows the fluent API's Any
    return chart


def _coverage(brief: DecisionBrief) -> None:
    """How much of the framework the evidence could actually fill in.

    First on the page, before the answer. A reader who sees "5 of 9" before they
    see the recommendation reads the recommendation differently, which is the
    entire intent — the chart is a caveat, not an ornament.
    """
    slices = coverage_slices(_selected_alternative(brief))
    blank = [name for name, ok in slices if not ok]

    st.altair_chart(_coverage_chart(slices), width="stretch")
    if blank:
        chips = "".join(f'<span class="dl-chip off">{n.replace("_", " ")}</span>' for n in blank)
        st.markdown(
            f'<div class="dl-card"><h4>No evidence · {len(blank)}</h4>{chips}'
            "<p style='color:#8B93A5;font-size:.8rem;margin:.7rem 0 0 0'>"
            "Absence of evidence is not evidence of low value. Left blank rather "
            "than filled with a plausible guess.</p></div>",
            unsafe_allow_html=True,
        )


def _options_table(brief: DecisionBrief) -> None:
    """The table, then the reasons, cross-referenced by number.

    Hand-rendered rather than `st.dataframe`, which draws to a canvas: column
    alignment cannot be set, long names are clipped mid-word with no way to see
    the rest, and the last column falls off the right edge. The counts are
    centred under their headings because a reader compares them down the column,
    and the names wrap in full because a truncated option is not an option a PM
    can weigh.
    """
    rows = option_rows(brief)
    if not rows:
        return

    head = (
        '<table class="dl-table"><thead><tr>'
        '<th class="c" style="width:3rem">#</th>'
        "<th>Possible feature to build</th>"
        '<th style="width:10rem">Kind of change</th>'
        '<th class="c" style="width:6rem">Evidence<br>for</th>'
        '<th class="c" style="width:6rem">Evidence<br>against</th>'
        '<th class="c" style="width:6.5rem">Criteria<br>evidenced</th>'
        '<th class="c" style="width:8rem">Status</th>'
        "</tr></thead><tbody>"
    )
    cells = []
    for row in rows:
        recommended = bool(row["Status"])
        open_tag = '<tr class="rec">' if recommended else "<tr>"
        chip = '<span class="dl-chip on">Recommended</span>' if recommended else ""
        cells.append(
            open_tag
            + f'<td class="c dim">{row["#"]}</td>'
            + "<td><strong>"
            + escape(row["Possible feature to build"])
            + "</strong></td>"
            + f'<td class="dim">{escape(row["Kind of change"])}</td>'
            + f'<td class="c">{row["Evidence for"]}</td>'
            + f'<td class="c">{row["Evidence against"]}</td>'
            + f'<td class="c">{escape(row["Criteria evidenced"])}</td>'
            + f'<td class="c">{chip}</td></tr>'
        )
    body = "".join(cells)
    st.markdown(head + body + "</tbody></table>", unsafe_allow_html=True)
    st.caption(
        "Recommended first, then by citations for minus citations against. "
        "**This is not a ranking of value** — the nine criteria are not "
        "commensurable and are never combined into a score. **Criteria evidenced** "
        "says how much is *known* about an option, not how good it is."
    )

    _why_this_one(brief)
    _evidence_behind_the_counts(brief, rows)

    with st.expander("Why each option was or was not selected"):
        for row in rows:
            reason = row["_why_not"] or "_Selected. See “Why this one” below._"
            st.markdown(f"**{row['#']}. {row['Possible feature to build']}** — {reason}")


def _why_this_one(brief: DecisionBrief) -> None:
    """The recommended row's argument, in the order a reader asks for it.

    The table answers *what* was chosen and the expander below answers *what the
    counts are*; neither answers *why this one*. That question was previously
    only answerable by reading a support paragraph several hundred words long,
    which is not what a PM does with a table in front of them.

    Built from the brief, never written here: the numbered steps are the
    recommended option's own supporting citations, the catch is its opposing
    one, and the closing line is the support level the challenger left it at.
    Hard-coding this case's argument would make the panel a lie on every other
    case, and a panel that reads well but is not derived from the run is exactly
    the kind of confident-sounding output this tool exists to argue against.
    """
    selected = _selected_alternative(brief)
    if selected is None or brief.recommendation is None:
        return

    with st.expander(f"Why this one? — {selected.name}", expanded=True):
        against = len(selected.opposing)
        plural = "" if against == 1 else "es"
        catches = "no catch" if against == 0 else f"{against} catch{plural}"
        st.markdown(f"**{len(selected.supporting)} reasons for it, and {catches}.**")
        for position, citation in enumerate(selected.supporting, start=1):
            where = f" ({citation.locator})" if citation.locator else ""
            st.markdown(f"{position}. “{citation.quote}” — `{citation.evidence_id}`{where}")

        for citation in selected.opposing:
            st.markdown(f"**The catch** — “{citation.quote}” — `{citation.evidence_id}`")
        if not selected.opposing:
            st.markdown("**The catch** — _nothing in the evidence set argues against it._")

        journey = support_journey(brief)
        support = brief.recommendation.support_level.value
        if journey is not None:
            drafted, final = journey
            st.markdown(
                f"So the support is **{final}**, not {drafted}: the challenger read the "
                "draft and cut it. That is why the recommendation is a first step "
                "rather than a build commitment."
            )
        else:
            st.markdown(
                f"So the support is **{support}** — read the catch above before acting "
                "on this, not after."
            )

        st.caption(
            "Nothing on this panel is written by the interface. Every line is the "
            f"recommended option's own citations, resolved against source text, from "
            f"the run of {brief.generated_at:%-d %b %Y}."
        )


def _evidence_behind_the_counts(brief: DecisionBrief, rows: list[dict[str, Any]]) -> None:
    """The quotes the two count columns are counting.

    A reader who sees *3 for, 1 against* asks what the three are, and until now
    the table could not answer: the numbers sat one expander away from the quotes
    that produced them, filed under per-criterion assessments rather than under
    the counts themselves. Two options in the bundled case share the identical
    3 / 1 / 5-of-9 triple, so the columns alone cannot explain why one of them is
    recommended — only the quotes can, and one piece of evidence appears *for*
    one option and *against* the other.

    Verbatim, with the evidence id beside each, because a quote a reader cannot
    trace back to a record is the thing this whole brief exists to avoid.
    """
    by_id = {alternative.id: alternative for alternative in brief.alternatives}
    with st.expander("The evidence behind those counts"):
        st.caption(
            "Every quote below has already been resolved against the record it "
            "cites. The counts in the table are the length of these two lists — "
            "nothing is weighted, and nothing is added up."
        )
        for row in rows:
            alternative = by_id[row["_id"]]
            st.markdown(f"**{row['#']}. {row['Possible feature to build']}**")
            _citation_list(alternative.supporting, "Evidence for", "none cited")
            _citation_list(alternative.opposing, "Evidence against", "none cited")


def _citation_list(citations: Sequence[Citation], heading: str, empty: str) -> None:
    """One side of one option, quotes first and provenance after.

    An empty side is stated rather than skipped. A missing heading reads as an
    option nobody argued against; "none cited" reads as what it is — an argument
    the evidence set does not make.
    """
    st.markdown(f"*{heading} ({len(citations)})*")
    if not citations:
        st.markdown(f"- _{empty}_")
        return
    for citation in citations:
        where = f" · {citation.locator}" if citation.locator else ""
        st.markdown(f"- “{citation.quote}” — `{citation.evidence_id}`{where}")


def _headline(brief: DecisionBrief) -> None:
    """The answer in one screen: what, how sure, and who lowered it.

    Three figures rather than one, because the number a reader wants — "how
    confident is this?" — is only honest alongside what it started at and what
    cut it. A single confidence chip invites the reading that the system was
    always this sure.
    """
    recommendation = brief.recommendation
    selected = _selected_alternative(brief)
    if recommendation is None:
        st.error("No recommendation was produced. See the checks above and the run trace below.")
        return

    st.subheader("Recommendation")
    st.markdown(f"### {selected.name if selected else recommendation.statement}")

    journey = support_journey(brief)
    drafted = journey[0] if journey else recommendation.support_level.value
    delta = "lowered by challenger" if journey else "challenger agreed"
    evidenced = sum(1 for _, ok in coverage_slices(selected) if ok)

    a, b, c = st.columns(3)
    a.metric(
        "Drafted",
        drafted,
        help="What the recommendation stage claimed before anything checked it.",
    )
    b.metric(
        "Support",
        recommendation.support_level.value,
        delta=delta,
        delta_color="inverse" if journey else "off",
        help="Stage 7 can lower a support level and can never raise one.",
    )
    c.metric(
        "Evidenced",
        f"{evidenced}/{len(Dimension)}",
        help="How much of the nine-criterion framework the evidence could fill in.",
    )
    st.caption(
        "Support is `low` / `moderate` / `strong` — a qualitative judgment, never "
        "a probability. A decimal here would imply a calibration nobody computed."
    )
    # The full statement is a paragraph, not a headline. It stays one click away
    # rather than pushing the option list below the fold.
    with st.expander("The recommendation in full"):
        st.markdown(recommendation.statement)


def _recommendation(brief: DecisionBrief) -> None:
    """The reasoning, folded away.

    All of it is load-bearing and none of it is a headline. Rendered open, the
    four lists below ran to some two thousand words and pushed the option table
    — the thing a PM is actually here to compare — three screens down.
    """
    st.subheader("Why this one")
    recommendation = brief.recommendation
    if recommendation is None:
        return

    with st.expander("What it rests on"):
        st.caption(f"Support rests on: {recommendation.support_basis or 'not stated'}")
        for claim in recommendation.claims:
            cites = " ".join(f"`{c.evidence_id}`" for c in claim.citations) or "_uncited_"
            st.markdown(f"- {claim.statement} {cites}")

    with st.expander("What would change it"):
        for item in recommendation.what_would_change_it or ("_nothing stated_",):
            st.markdown(f"- {item}")
        for item in recommendation.conditions:
            st.markdown(f"- **Condition:** {item}")

    with st.expander("Tradeoffs and risk"):
        for tradeoff in recommendation.tradeoffs:
            st.markdown(f"- {tradeoff.description}")
        for alternative in brief.alternatives:
            for assessment in alternative.assessments:
                if assessment.dimension is Dimension.RISK and assessment.summary:
                    st.markdown(f"- **{alternative.name}** — {assessment.summary}")


def _experiment(brief: DecisionBrief) -> None:
    experiment = brief.recommendation.experiment if brief.recommendation else None
    st.subheader("What to test before investing")
    if experiment is None:
        st.caption("No experiment was proposed.")
        return

    st.markdown(f"**{experiment.hypothesis}**")
    if experiment.method:
        with st.expander("How to run it"):
            st.markdown(experiment.method)
    success, guardrail = st.columns(2)
    success.markdown("**Success metrics**")
    for metric in experiment.metrics:
        if metric.role is MetricRole.SUCCESS:
            success.markdown(f"- {metric.name} {metric.target}")
    guardrail.markdown("**Guardrail metrics**")
    for metric in experiment.metrics:
        if metric.role is MetricRole.GUARDRAIL:
            guardrail.markdown(f"- {metric.name} {metric.target}")


def _pm_decision(brief: DecisionBrief) -> None:
    """Deliberately below the brief, in its own bordered panel.

    Not an "accept" button. The person records what *they* decided, and a
    disagreement is a first-class outcome the form asks them to explain.
    """
    st.divider()
    st.subheader("Your decision")
    st.info(DECISION_OWNER_NOTICE)

    with st.form("pm_decision"):
        decision = st.text_area("What did you decide?", height=90)
        rationale = st.text_area("Why?", height=90)
        agreement = st.radio(
            "Does this match the recommendation?",
            ("Not stated", "Agreed", "Disagreed"),
            horizontal=True,
        )
        override = st.text_input("If you disagreed, why?")
        submitted = st.form_submit_button("Record my decision")

    if not submitted:
        return
    if not decision.strip():
        st.warning("Write down what you decided before recording it.")
        return

    agreed = {"Not stated": None, "Agreed": True, "Disagreed": False}[agreement]
    try:
        recorded = record_pm_decision(
            brief,
            decided_by="pm-local",
            decision=decision.strip(),
            rationale=rationale.strip(),
            agreed_with_recommendation=agreed,
            override_reason=override.strip(),
            decided_at=datetime.now(),
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    st.success("Recorded, separately from the recommendation.")
    st.download_button(
        "Download the brief with your decision (Markdown)",
        report.to_markdown(brief, decision=recorded),
        file_name=f"{brief.id}-with-decision.md",
    )


def _evidence(brief: DecisionBrief) -> None:
    cited = brief.cited_evidence_ids()
    st.subheader(f"Evidence ({len(brief.evidence)})")
    for record in brief.evidence:
        mark = "" if record.id in cited else "  ·  never cited"
        with st.expander(f"{record.id} — {record.title or record.source_id}{mark}"):
            st.caption(
                f"{record.evidence_type.value} · {record.source_reference or record.source_id}"
            )
            st.code(record.content, language=None)


def _trace(brief: DecisionBrief) -> None:
    trace = brief.run_trace
    st.subheader("Run trace")
    if trace is None:
        st.caption("No trace recorded.")
        return
    st.caption(f"{trace.run_id} · {trace.total_latency_ms} ms")
    st.dataframe(
        [
            {
                "stage": s.name,
                "provider": s.provider or "-",
                "model": s.model or "-",
                "prompt": s.prompt_version or "-",
                "in": s.input_tokens,
                "out": s.output_tokens,
                "ms": s.latency_ms,
                "outcome": "ok" if s.succeeded else s.error[:60],
            }
            for s in trace.stages
        ],
        width="stretch",
        hide_index=True,
    )


def _exports(brief: DecisionBrief) -> None:
    st.subheader("Export")
    left, right = st.columns(2)
    left.download_button(
        "DecisionBrief (Markdown)",
        report.to_markdown(brief),
        file_name=f"{brief.id}.md",
        width="stretch",
    )
    right.download_button(
        "DecisionBrief (JSON)",
        report.to_json(brief),
        file_name=f"{brief.id}.json",
        width="stretch",
        mime="application/json",
    )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #


def _run_brief(inputs: dict[str, Any]) -> DecisionBrief | None:
    try:
        loaded: LoadedCase = load_case(
            materialise_case(inputs["directory"], inputs["uploaded"]),
            question=inputs["question"],
            desired_outcome=inputs["outcome"],
            product_area=inputs["product_area"],
            criteria=criteria_for(
                inputs["dimensions"],
                require_non_ai=inputs["require_non_ai"],
                require_no_build=inputs["require_no_build"],
            ),
        )
        provider = build_provider(inputs["live"], inputs["api_key"], inputs["model"])
    except (CaseError, ConfigError) as exc:
        st.error(str(exc))
        return None

    label = "Calling a live model…" if inputs["live"] else "Replaying recorded output…"
    try:
        # A live run is seven sequential model calls over several minutes. A single
        # spinner over the whole thing is indistinguishable from a hung page, so each
        # stage reports as it starts and finishes.
        with st.status(label, expanded=inputs["live"]) as status:
            lens = DecisionLens(
                provider,
                loaded.sources,
                as_of=loaded.as_of,
                timeout_seconds=(
                    LIVE_SKILL_TIMEOUT_SECONDS if inputs["live"] else SKILL_TIMEOUT_SECONDS
                ),
                progress=status.write,
            )
            brief = lens.run(loaded.request)
            status.update(label="Brief ready", state="complete", expanded=False)
            return brief
    except (DecisionLensError, ModelError) as exc:
        st.error(str(exc))
        if not inputs["live"]:
            st.caption(
                "The demo cache may be empty for this case. Run `decisionlens record` once "
                "with an API key to populate it."
            )
        return None


def render(brief: DecisionBrief) -> None:
    """Coverage, then the answer, then the reasons to doubt it, then the detail.

    An earlier version led with the evidence and put the recommendation sixth,
    below forty-odd facts, assumptions, opinions and constraints. That is the
    order in which the analysis was produced and the order a paper is written;
    it is not the order a decision is read. A PM opening this wants the answer,
    then what would change it, and only then the material it was built from.

    The classification tables stay in the brief because they are the audit
    trail — but they are collapsed, because a section nobody can finish is a
    section nobody checks.
    """
    _style()
    _checks(brief)

    # The answer and its coverage side by side, then the option list.
    #
    # Coverage was its own full-width section above the answer, which read as a
    # separate report. Beside the support figures it does the job it is for: the
    # same glance that reads "low" reads "5 of 9 criteria evidenced", and the two
    # are the same fact stated twice.
    answer, coverage = st.columns([1.6, 1])
    with answer:
        _headline(brief)
    with coverage:
        _coverage(brief)

    # The option list is what a PM came to compare, so nothing prose-heavy sits
    # above it. The reasoning is below, and folded.
    st.markdown('<div class="dl-eyebrow">Options on the table</div>', unsafe_allow_html=True)
    _alternatives(brief)
    _recommendation(brief)
    st.divider()

    # The reasons to doubt it. These belong above the raw evidence: a reader who
    # stops here has still seen every material objection.
    _contradictions(brief)
    _gaps(brief)
    _experiment(brief)
    st.divider()

    _pm_decision(brief)
    st.divider()

    with st.expander("How each statement was classified"):
        _evidence_says(brief)
    with st.expander("Evidence and run trace"):
        _evidence(brief)
        _trace(brief)
    _exports(brief)


def main() -> None:  # pragma: no cover - exercised by the Streamlit runtime
    st.set_page_config(page_title="DecisionLens", page_icon="🔍", layout="wide")
    _style()
    inputs = _sidebar()

    st.markdown(
        '<div class="dl-hero"><h1>DecisionLens</h1>'
        f'<span class="dl-case">data/{inputs["directory"].name}/</span>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption(SYNTHETIC_DATA_NOTICE)
    st.caption(DECISION_OWNER_NOTICE)

    if inputs["uploaded"]:
        st.caption(
            f"{len(inputs['uploaded'])} uploaded file(s) will be added to a throwaway copy of "
            "the case. The bundled evidence is never modified. Synthetic data only."
        )

    if "brief" not in st.session_state:
        st.session_state["brief"] = None
    if inputs["run"]:
        st.session_state["brief"] = _run_brief(inputs)

    brief = st.session_state["brief"]
    if brief is None:
        st.info("Choose a case on the left and press **Produce a brief**.")
        return
    render(brief)


# `streamlit run` executes this file as a script, so this is the entry point in
# both that case and a plain `python -m`. Importing the module — which the tests
# do — runs nothing.
if __name__ == "__main__":  # pragma: no cover - driven by the Streamlit runtime
    main()

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
*   **Going live is two deliberate acts.** A toggle, and then a key. The page
    never picks up a credential from the environment on its own.

This module is intentionally thin. Everything it shows comes from tested code in
:mod:`decision_lens.report`, :mod:`decision_lens.case` and the orchestrator, so
the interface has no analysis of its own to get wrong.

Run it with::

    make ui
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import streamlit as st

from decision_lens import report
from decision_lens.case import CaseError, LoadedCase, criteria_for, load_case
from decision_lens.config import ConfigError, Settings
from decision_lens.llm import CachedDemoProvider, ModelError, ModelProvider
from decision_lens.llm.anthropic_provider import AnthropicProvider
from decision_lens.models import (
    DECISION_OWNER_NOTICE,
    SYNTHETIC_DATA_NOTICE,
    ClaimType,
    DecisionBrief,
    Dimension,
    MetricRole,
    ValidationSeverity,
)
from decision_lens.orchestrator import DecisionLens, DecisionLensError, record_pm_decision
from decision_lens.recorder import LIVE_SKILL_TIMEOUT_SECONDS
from decision_lens.skills import SKILL_TIMEOUT_SECONDS

CASES_ROOT = Path("data")
DEFAULT_MODEL = "claude-opus-5"


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

    st.sidebar.subheader("Case")
    directory = st.sidebar.selectbox(
        "Bundled case", cases, format_func=lambda p: p.name, help="A folder of synthetic evidence"
    )
    uploaded = st.sidebar.file_uploader(
        "…or add synthetic files to it",
        accept_multiple_files=True,
        help="Files are added to the selected case for this session only. Synthetic data only.",
    )

    st.sidebar.subheader("The decision")
    question = st.sidebar.text_area(
        "Question", height=80, placeholder="Leave blank to use the case's own question"
    )
    outcome = st.sidebar.text_area(
        "Desired outcome", height=80, placeholder="Leave blank to use the case's"
    )
    product_area = st.sidebar.text_input(
        "Product area", placeholder="Leave blank to use the case's"
    )

    st.sidebar.subheader("Criteria")
    dimensions = st.sidebar.multiselect(
        "Compare options across",
        list(Dimension),
        default=list(Dimension),
        format_func=lambda d: d.value.replace("_", " "),
    )
    require_non_ai = st.sidebar.checkbox("Require a non-AI option", value=True)
    require_no_build = st.sidebar.checkbox("Require a no-build / defer option", value=True)

    st.sidebar.subheader("Model")
    live = st.sidebar.toggle(
        "Use a live model",
        value=False,
        help="Off replays recorded output: free, offline, identical every run.",
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
        "dimensions": set(dimensions),
        "require_non_ai": require_non_ai,
        "require_no_build": require_no_build,
        "live": live,
        "api_key": api_key,
        "model": model,
        "run": st.sidebar.button("Produce a brief", type="primary", width="stretch"),
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
    st.subheader(f"Alternatives ({len(brief.alternatives)})")
    left, right = st.columns(2)
    left.metric("Non-AI option", "yes" if brief.has_non_ai_alternative else "MISSING")
    right.metric("No-build / defer option", "yes" if brief.has_no_build_alternative else "MISSING")

    _comparison_table(brief)

    selected = brief.recommendation.selected_alternative_id if brief.recommendation else ""
    st.caption("Open an option for the reasoning behind each cell.")
    for alternative in brief.alternatives:
        label = f"{alternative.name} · {alternative.kind.value}"
        with st.expander(label + ("  ← recommended" if alternative.id == selected else "")):
            if alternative.description:
                st.markdown(alternative.description)
            for assessment in alternative.assessments:
                st.markdown(
                    f"- **{assessment.dimension.value}** — {assessment.state.value}: "
                    f"{assessment.summary or '_no summary_'}"
                )
            if alternative.why_not_selected:
                st.caption(f"Not selected: {alternative.why_not_selected}")


def _recommendation(brief: DecisionBrief) -> None:
    st.subheader("Recommendation")
    recommendation = brief.recommendation
    if recommendation is None:
        st.error("No recommendation was produced. See the checks above and the run trace below.")
        return

    st.markdown(f"### {recommendation.statement}")
    a, b = st.columns(2)
    a.metric("Support", recommendation.support_level.value, help="Qualitative, never a probability")
    b.metric("Option kind", recommendation.option_kind.value)
    st.caption(f"Support rests on: {recommendation.support_basis or 'not stated'}")

    if recommendation.claims:
        st.markdown("**What it rests on**")
        for claim in recommendation.claims:
            cites = " ".join(f"`{c.evidence_id}`" for c in claim.citations) or "_uncited_"
            st.markdown(f"- {claim.statement} {cites}")

    st.markdown("**What would change it**")
    for item in recommendation.what_would_change_it or ("_nothing stated_",):
        st.markdown(f"- {item}")

    if recommendation.conditions:
        st.markdown("**Conditions**")
        for item in recommendation.conditions:
            st.markdown(f"- {item}")

    if recommendation.tradeoffs:
        st.markdown("**Tradeoffs**")
        for tradeoff in recommendation.tradeoffs:
            st.markdown(f"- {tradeoff.description}")

    risks = [
        f"{alt.name}: {a.summary}"
        for alt in brief.alternatives
        for a in alt.assessments
        if a.dimension is Dimension.RISK and a.summary
    ]
    if risks:
        st.markdown("**Risk**")
        for risk in risks:
            st.markdown(f"- {risk}")


def _experiment(brief: DecisionBrief) -> None:
    experiment = brief.recommendation.experiment if brief.recommendation else None
    st.subheader("What to test before investing")
    if experiment is None:
        st.caption("No experiment was proposed.")
        return

    st.markdown(f"**{experiment.hypothesis}**")
    if experiment.method:
        st.caption(experiment.method)
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

    lens = DecisionLens(
        provider,
        loaded.sources,
        as_of=loaded.as_of,
        timeout_seconds=LIVE_SKILL_TIMEOUT_SECONDS if inputs["live"] else SKILL_TIMEOUT_SECONDS,
    )
    spinner = "Calling a live model…" if inputs["live"] else "Replaying recorded output…"
    try:
        with st.spinner(spinner):
            return lens.run(loaded.request)
    except (DecisionLensError, ModelError) as exc:
        st.error(str(exc))
        if not inputs["live"]:
            st.caption(
                "The demo cache may be empty. Run `decisionlens record` once with an API key, "
                "or switch on live mode above."
            )
        return None


def render(brief: DecisionBrief) -> None:
    """Answer first, then the reasons to doubt it, then the detail.

    An earlier version led with the evidence and put the recommendation sixth,
    below forty-odd facts, assumptions, opinions and constraints. That is the
    order in which the analysis was produced and the order a paper is written;
    it is not the order a decision is read. A PM opening this wants the answer,
    then what would change it, and only then the material it was built from.

    The classification tables stay in the brief because they are the audit
    trail — but they are collapsed, because a section nobody can finish is a
    section nobody checks.
    """
    _checks(brief)
    st.divider()

    # The answer, and immediately what else was on the table.
    _recommendation(brief)
    _alternatives(brief)
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
    inputs = _sidebar()

    st.title("DecisionLens")
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

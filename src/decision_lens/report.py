"""Turning a finished brief into something a person reads.

Distinct from :mod:`decision_lens.rendering`, which formats domain objects into
*prompt* text for a model. This formats them for a product manager who is about
to disagree with them. The two have different audiences and different rules, so
they are different modules.

What the layout is built around:

*   **Order follows how a decision should be read.** What was asked, what was
    found, what conflicts, what is missing, what else could be done — and only
    then what is recommended. A brief that opens with its answer invites a reader
    to accept the answer and skip the working, which is the habit this product
    exists to break.
*   **Every claim carries its citation inline.** A reader checking one statement
    should not have to hold an evidence id in their head and scroll. The evidence
    section repeats the quoted text so a check is a glance, not a search.
*   **Validation issues are not an appendix.** They appear before the
    recommendation, because an error means the recommendation should not be read
    as it stands, and putting that after the answer is putting it where nobody
    looks.
*   **The PM's decision is rendered in its own section, always present.** Empty
    when no decision has been recorded, so the space for it exists in every brief
    and the separation between recommending and deciding is visible on the page.

Both required notices are emitted verbatim from the constants in
:mod:`decision_lens.models`, so they cannot drift from the model layer.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from decision_lens.models import (
    DECISION_OWNER_NOTICE,
    SYNTHETIC_DATA_NOTICE,
    Alternative,
    Citation,
    ClaimType,
    DecisionBrief,
    Dimension,
    EvidenceRecord,
    MetricRole,
    PMDecision,
    ValidationIssue,
    ValidationSeverity,
)

__all__ = ["to_json", "to_markdown"]

#: Claim types that are not facts, grouped for the reader under their own headings.
#: Splitting them is the point: an assumption listed beside a finding reads as one.
_CLAIM_SECTIONS: tuple[tuple[str, tuple[ClaimType, ...]], ...] = (
    ("Facts", (ClaimType.FACT,)),
    ("Assumptions", (ClaimType.ASSUMPTION,)),
    ("Stakeholder opinions", (ClaimType.STAKEHOLDER_OPINION,)),
    (
        "Constraints",
        (
            ClaimType.TECHNICAL_CONSTRAINT,
            ClaimType.BUSINESS_CONSTRAINT,
            ClaimType.GOVERNANCE_CONSTRAINT,
        ),
    ),
)


def _cites(citations: Sequence[Citation]) -> str:
    return " ".join(f"[{c.evidence_id}]" for c in citations) or "_(uncited)_"


def _bullets(items: Sequence[str], empty: str = "_(none)_") -> list[str]:
    return [f"- {item}" for item in items] or [empty]


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _framing(brief: DecisionBrief) -> list[str]:
    request = brief.request
    lines = [
        "## The question",
        "",
        f"**{request.question}**",
        "",
        f"- Desired outcome: {request.desired_outcome or '_(not stated)_'}",
        f"- Product area: {request.user.product_area or '_(not stated)_'}",
        f"- Asked by: {request.user.display_name or request.user.user_id}",
    ]
    if request.time_period:
        lines.append(f"- Period: {request.time_period}")
    applicable = request.criteria.applicable
    lines.append(f"- Compared across: {', '.join(d.value for d in applicable)}")
    return lines


def _issues(issues: Sequence[ValidationIssue]) -> list[str]:
    errors = [i for i in issues if i.severity is ValidationSeverity.ERROR]
    warnings = [i for i in issues if i.severity is ValidationSeverity.WARNING]

    lines = ["## Checks", ""]
    if not issues:
        lines += ["Every deterministic check passed.", ""]
        return lines

    if errors:
        lines += [
            f"**{len(errors)} error(s). This brief should not be acted on as it stands.**",
            "",
        ]
        lines += [f"- `{i.code}` — {i.message}" for i in errors]
        lines.append("")
    if warnings:
        lines += [f"{len(warnings)} warning(s):", ""]
        lines += [f"- `{i.code}` — {i.message}" for i in warnings]
        lines.append("")
    return lines


def _recommendation(brief: DecisionBrief) -> list[str]:
    lines = ["## Recommendation", ""]
    recommendation = brief.recommendation
    if recommendation is None:
        lines += [
            "_No recommendation was produced._ See the checks above for why, and the run "
            "trace below for which stage did not complete.",
            "",
        ]
        return lines

    lines += [
        f"**{recommendation.statement}**",
        "",
        f"- Option kind: `{recommendation.option_kind.value}`",
        f"- Support: **{recommendation.support_level.value}** "
        "— a qualitative judgment, not a probability",
        f"- Support rests on: {recommendation.support_basis or '_(not stated)_'}",
        "",
    ]

    if recommendation.claims:
        lines += ["**What it rests on**", ""]
        lines += [f"- {c.statement} {_cites(c.citations)}" for c in recommendation.claims]
        lines.append("")

    lines += ["**What would change it**", ""]
    lines += _bullets(
        recommendation.what_would_change_it,
        "_(nothing stated — a support level a reader cannot act on is decoration)_",
    )
    lines.append("")

    if recommendation.conditions:
        lines += ["**Conditions**", "", *_bullets(recommendation.conditions), ""]
    return lines


def _experiment(brief: DecisionBrief) -> list[str]:
    lines = ["## What to test before investing", ""]
    experiment = brief.recommendation.experiment if brief.recommendation else None
    if experiment is None:
        lines += ["_No experiment was proposed._", ""]
        return lines

    lines += [f"**{experiment.hypothesis}**", ""]
    if experiment.method:
        lines.append(f"- Method: {experiment.method}")
    if experiment.duration:
        lines.append(f"- Duration: {experiment.duration}")
    lines.append("")

    roles = (("Success metrics", MetricRole.SUCCESS), ("Guardrail metrics", MetricRole.GUARDRAIL))
    for label, role in roles:
        metrics = [m for m in experiment.metrics if m.role is role]
        lines += [f"**{label}**", ""]
        lines += _bullets(
            [f"{m.name}{f' — target {m.target}' if m.target else ''}" for m in metrics]
        )
        lines.append("")
    return lines


def _claims(brief: DecisionBrief) -> list[str]:
    lines = ["## What the evidence says", ""]
    if not brief.claims:
        lines += ["_No claims were extracted._", ""]
        return lines

    for heading, types in _CLAIM_SECTIONS:
        group = [c for c in brief.claims if c.claim_type in types]
        lines += [f"### {heading}", ""]
        if not group:
            lines += ["_(none identified)_", ""]
            continue
        for claim in group:
            suffix = f" `{claim.claim_type.value}`" if len(types) > 1 else ""
            lines.append(f"- {claim.statement} {_cites(claim.citations)}{suffix}")
            if claim.rationale:
                lines.append(f"  - _{claim.rationale}_")
        lines.append("")
    return lines


def _contradictions(brief: DecisionBrief) -> list[str]:
    lines = ["## Contradictions", ""]
    if not brief.contradictions:
        lines += ["_None found. Note this is not the same as none existing._", ""]
        return lines

    lines += ["These are reported unresolved. DecisionLens does not pick a side.", ""]
    for found in brief.contradictions:
        lines += [
            f"### {found.topic} `{found.kind.value}`",
            "",
            f"- One side: [{found.side_a.evidence_id}] “{found.side_a.quote}”",
            f"- The other: [{found.side_b.evidence_id}] “{found.side_b.quote}”",
        ]
        if found.summary:
            lines.append(f"- {found.summary}")
        lines += [f"- **What would settle it:** {found.how_to_resolve}", ""]
    return lines


def _gaps(brief: DecisionBrief) -> list[str]:
    lines = [
        "## Missing evidence",
        "",
        "Evidence that does not exist is as decision-relevant as evidence that does.",
        "",
    ]
    if not brief.missing_evidence:
        lines += ["_No gaps identified._", ""]
        return lines

    for gap in brief.missing_evidence:
        searched = "searched, not found" if gap.was_searched else "no source of this kind connected"
        lines += [
            f"- **{gap.question}** `{gap.impact.value}` _({searched})_",
            f"  - Why it matters: {gap.why_it_matters}",
        ]
        if gap.how_to_obtain:
            lines.append(f"  - How to get it: {gap.how_to_obtain}")
    lines.append("")
    return lines


def _alternative_block(alternative: Alternative) -> list[str]:
    horizon = f" · {alternative.horizon.value}" if alternative.horizon else ""
    lines = [f"### {alternative.name} `{alternative.kind.value}`{horizon}", ""]
    if alternative.description:
        lines += [alternative.description, ""]
    if alternative.supporting:
        lines.append(f"- For: {_cites(alternative.supporting)}")
    if alternative.opposing:
        lines.append(f"- Against: {_cites(alternative.opposing)}")
    if alternative.why_not_selected:
        lines.append(f"- Not selected because: {alternative.why_not_selected}")

    unassessed = alternative.unassessed_dimensions
    if unassessed:
        lines.append(
            f"- Could not be assessed on: {', '.join(d.value for d in unassessed)} "
            "— absence of evidence is not evidence of low value"
        )
    for assessment in alternative.assessments:
        if assessment.summary:
            lines.append(
                f"  - {assessment.dimension.value}: {assessment.summary} "
                f"{_cites(assessment.citations)}"
            )
    lines.append("")
    return lines


def _alternatives(brief: DecisionBrief) -> list[str]:
    lines = ["## Alternatives considered", ""]
    if not brief.alternatives:
        lines += ["_None generated._", ""]
        return lines

    selected = brief.recommendation.selected_alternative_id if brief.recommendation else ""
    for alternative in brief.alternatives:
        block = _alternative_block(alternative)
        if alternative.id == selected:
            block[0] = block[0] + "  ← recommended"
        lines += block

    lines += [
        "**Required options**",
        "",
        f"- Non-AI option present: {'yes' if brief.has_non_ai_alternative else '**no**'}",
        f"- No-build, defer or research option present: "
        f"{'yes' if brief.has_no_build_alternative else '**no**'}",
        "",
    ]
    return lines


def _tradeoffs_and_risks(brief: DecisionBrief) -> list[str]:
    """Tradeoffs are a first-class type; risk is assembled from what the model has.

    There is no `Risk` model. Rather than invent one late, this reports the two
    places risk is actually recorded — the risk dimension of each option, and
    what the recommendation says would change it.
    """
    lines = ["## Tradeoffs and risks", "", "### Tradeoffs", ""]
    tradeoffs = brief.recommendation.tradeoffs if brief.recommendation else ()
    if not tradeoffs:
        lines += ["_(none stated)_", ""]
    for tradeoff in tradeoffs:
        lines.append(f"- {tradeoff.description}")
        if tradeoff.gains:
            lines.append(f"  - Gains: {'; '.join(tradeoff.gains)}")
        if tradeoff.gives_up:
            lines.append(f"  - Gives up: {'; '.join(tradeoff.gives_up)}")
    if tradeoffs:
        lines.append("")

    lines += ["### Risk", ""]
    risk_lines: list[str] = []
    for alternative in brief.alternatives:
        for assessment in alternative.assessments:
            if assessment.dimension is Dimension.RISK and assessment.summary:
                risk_lines.append(f"- {alternative.name}: {assessment.summary}")
    lines += _bullets(risk_lines, "_(no option was assessed on risk)_")
    lines.append("")
    return lines


def _evidence(records: Sequence[EvidenceRecord], brief: DecisionBrief) -> list[str]:
    lines = ["## Evidence", "", f"{len(records)} record(s) informed this brief.", ""]
    cited = brief.cited_evidence_ids()
    for record in records:
        mark = "" if record.id in cited else " _(never cited)_"
        updated = f" · updated {record.updated_at.isoformat()}" if record.updated_at else ""
        lines += [
            f"### [{record.id}] {record.title or record.source_id}{mark}",
            "",
            f"`{record.evidence_type.value}` · {record.source_reference or record.source_id}"
            f"{updated}",
            "",
            "```",
            record.content,
            "```",
            "",
        ]
    return lines


def _trace(brief: DecisionBrief) -> list[str]:
    lines = ["## Run trace", ""]
    trace = brief.run_trace
    if trace is None:
        lines += ["_No trace recorded._", ""]
        return lines

    lines += [
        f"Run `{trace.run_id}` · {trace.total_latency_ms} ms total",
        "",
        "| Stage | Provider | Model | Prompt | Tokens in/out | ms | Outcome |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for stage in trace.stages:
        tokens = f"{stage.input_tokens or '-'}/{stage.output_tokens or '-'}"
        outcome = "ok" if stage.succeeded else f"**failed** — {stage.error[:80]}"
        lines.append(
            f"| {stage.name} | {stage.provider or '-'} | {stage.model or '-'} "
            f"| {stage.prompt_version or '-'} | {tokens} | {stage.latency_ms or '-'} | {outcome} |"
        )
    lines.append("")
    return lines


def _pm_decision(brief: DecisionBrief, decision: PMDecision | None) -> list[str]:
    """Always rendered, even when empty.

    The space for the PM's decision exists in every brief so that the boundary
    between what the system recommended and what a person decided is visible on
    the page rather than implied.
    """
    lines = ["## The product manager's decision", "", f"> {brief.decision_owner_notice}", ""]
    if decision is None:
        lines += [
            "_Not yet recorded._ DecisionLens has recommended; the decision has not been made.",
            "",
        ]
        return lines

    agreement = {
        True: "agreed with the recommendation",
        False: "**disagreed with the recommendation**",
        None: "did not state agreement",
    }[decision.agreed_with_recommendation]

    lines += [
        f"**{decision.decision}**",
        "",
        f"- Decided by {decision.decided_by} on {decision.decided_at.isoformat()}",
        f"- {agreement}",
    ]
    if decision.rationale:
        lines.append(f"- Rationale: {decision.rationale}")
    if decision.override_reason:
        lines.append(f"- Reason for overriding: {decision.override_reason}")
    lines.append("")
    return lines


# --------------------------------------------------------------------------- #
# Public
# --------------------------------------------------------------------------- #


def to_markdown(brief: DecisionBrief, *, decision: PMDecision | None = None) -> str:
    """Render a brief for a human reader.

    Section order is deliberate: the question, then what was found and what is
    wrong with it, and only then the recommendation. A reader who stops early
    should stop on the evidence, not on the answer.
    """
    lines: list[str] = [
        f"# Decision brief — {brief.id}",
        "",
        f"> {SYNTHETIC_DATA_NOTICE}",
        "",
        f"Generated {brief.generated_at.isoformat()}",
        "",
    ]
    lines += _framing(brief)
    lines.append("")
    lines += _issues(brief.validation_issues)
    lines += _claims(brief)
    lines += _contradictions(brief)
    lines += _gaps(brief)
    lines += _alternatives(brief)
    lines += _recommendation(brief)
    lines += _tradeoffs_and_risks(brief)
    lines += _experiment(brief)
    lines += _pm_decision(brief, decision)
    lines += _evidence(brief.evidence, brief)
    lines += _trace(brief)
    return "\n".join(lines).rstrip() + "\n"


def to_json(brief: DecisionBrief, *, decision: PMDecision | None = None, indent: int = 2) -> str:
    """Serialise a brief exactly as the domain model holds it.

    The full object, not a summary. This is the machine-readable half of the
    export pair, and Phase 10 reads it back to score runs — so nothing may be
    dropped for tidiness.
    """
    payload: dict[str, object] = {
        "notices": {
            "synthetic_data": SYNTHETIC_DATA_NOTICE,
            "decision_owner": DECISION_OWNER_NOTICE,
        },
        "brief": brief.model_dump(mode="json"),
        "pm_decision": decision.model_dump(mode="json") if decision else None,
    }
    return json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"

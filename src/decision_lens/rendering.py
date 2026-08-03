"""Turning domain objects into prompt text.

One implementation, shared by the baseline and by every skill. If the two arms
formatted evidence differently, a difference in results could be caused by
presentation rather than by the workflow, and the evaluation would be measuring
the wrong thing.

Content is always reproduced verbatim. Summarising here would make the
instruction to quote verbatim impossible to follow and every citation
uncheckable.
"""

from __future__ import annotations

from collections.abc import Sequence

from decision_lens.models import (
    Alternative,
    Claim,
    Contradiction,
    DecisionRequest,
    EvidenceRecord,
    MissingEvidence,
    Recommendation,
)


def render_evidence(records: Sequence[EvidenceRecord]) -> str:
    """Format evidence with ids a model can cite and metadata it can weigh."""
    blocks: list[str] = []
    for record in records:
        header = f"[{record.id}] {record.title or record.source_id}"
        details = [record.evidence_type.value, f"source: {record.source_id}"]
        if record.updated_at:
            details.append(f"updated: {record.updated_at.isoformat()}")
        if record.owner:
            details.append(f"owner: {record.owner}")
        blocks.append(f"{header}\n({', '.join(details)})\n{record.content}")
    return "\n\n---\n\n".join(blocks) or "(no evidence available)"


def render_criteria(request: DecisionRequest) -> str:
    lines = [
        f"- {c.dimension.value}" + (f" — {c.note}" if c.note else "")
        for c in request.criteria.dimensions
        if c.applies
    ]
    return "\n".join(lines) or "- (no dimensions specified)"


def render_claims(claims: Sequence[Claim]) -> str:
    """Format claims, id first.

    The id is not decoration. The challenger is asked to reclassify claims *by
    id*, and an earlier version of this function omitted them — so the prompt
    demanded an identifier it never showed. A real run duly invented `C3` and
    `C7` for claims actually called `C-003` and `C-007`, and the whole stage was
    rejected. Anything a prompt asks a model to cite back must appear in it.
    """
    if not claims:
        return "(none identified)"
    return "\n".join(
        f"- {c.id} [{c.claim_type.value}] {c.statement} "
        f"({', '.join(str(cit) for cit in c.citations) or 'uncited'})"
        for c in claims
    )


def render_constraints(claims: Sequence[Claim]) -> str:
    """Only the constraint-typed claims, for skills that must respect them."""
    constraints = [c for c in claims if c.claim_type.is_constraint]
    if not constraints:
        return "(none identified)"
    return "\n".join(f"- [{c.claim_type.value}] {c.statement}" for c in constraints)


def render_contradictions(contradictions: Sequence[Contradiction]) -> str:
    if not contradictions:
        return "(none identified)"
    return "\n".join(
        f"- [{c.kind.value}] {c.topic}: {c.summary or 'sides disagree'} ({c.side_a} vs {c.side_b})"
        for c in contradictions
    )


def render_gaps(gaps: Sequence[MissingEvidence]) -> str:
    if not gaps:
        return "(none identified)"
    return "\n".join(f"- [{g.impact.value}] {g.question}" for g in gaps)


def render_recommendation(recommendation: Recommendation | None) -> str:
    """Format a draft recommendation for the challenger to attack.

    Shows the support level and what it rests on, because the challenger's job is
    partly to disagree with those two specifically.
    """
    if recommendation is None:
        return "(no recommendation was produced)"

    lines = [
        f"Statement: {recommendation.statement}",
        f"Option kind: {recommendation.option_kind.value}",
        f"Selected alternative: {recommendation.selected_alternative_id or '(none named)'}",
        f"Support level: {recommendation.support_level.value}",
        f"Support rests on: {recommendation.support_basis or '(not stated)'}",
    ]
    if recommendation.claims:
        lines.append("Supporting claims:")
        lines.append(render_claims(recommendation.claims))
    if recommendation.conditions:
        lines.append("Conditions: " + "; ".join(recommendation.conditions))
    if recommendation.what_would_change_it:
        lines.append("What would change it: " + "; ".join(recommendation.what_would_change_it))
    if recommendation.experiment:
        lines.append(f"Proposed test: {recommendation.experiment.hypothesis}")
    return "\n".join(lines)


def render_alternatives(alternatives: Sequence[Alternative]) -> str:
    if not alternatives:
        return "(none generated)"
    lines: list[str] = []
    for alt in alternatives:
        horizon = f", {alt.horizon.value}" if alt.horizon else ""
        lines.append(f"- {alt.id} {alt.name} ({alt.kind.value}{horizon}): {alt.description}")
        for assessment in alt.assessments:
            lines.append(
                f"    {assessment.dimension.value}: {assessment.state.value} — {assessment.summary}"
            )
    return "\n".join(lines)

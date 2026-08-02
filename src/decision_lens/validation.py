"""Deterministic checks on a finished brief.

Everything here is arithmetic or set membership. No model is asked whether the
brief is good, because a check that can be argued with is not a check — and
because the product's claim is that a PM can verify the output quickly, which is
only true if the verification is mechanical.

The module is split into two halves that stay strictly separate:

*   :func:`validate` **reports and never mutates.** It returns issues. Running it
    twice on the same brief returns the same issues and changes nothing.
*   :func:`enforce_support_ceiling` **is the only thing that lowers a support
    level**, and it is called explicitly by the orchestrator. Confidence reduction
    is a consequential act; burying it inside a checking function would make it a
    side effect nobody reads. It is idempotent, and it writes its reason into
    ``support_basis`` so the reduction is visible in the brief itself rather than
    only in a log.

An ``ERROR`` means the brief must not be presented as it stands. A ``WARNING``
means the reader should know something, but the brief holds.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from decision_lens.models import (
    ClaimType,
    DecisionBrief,
    SupportLevel,
    ValidationIssue,
    ValidationSeverity,
)
from decision_lens.provenance import (
    ProvenanceReport,
    ResolutionFailure,
    check_provenance,
)

__all__ = [
    "CRITICAL_STAGES",
    "SUPPORT_RANK",
    "ValidationCode",
    "enforce_support_ceiling",
    "support_ceiling",
    "validate",
    "weaker_of",
]


# --------------------------------------------------------------------------- #
# Support levels are ordered, but only for comparison
# --------------------------------------------------------------------------- #

#: An ordering, not a scale. The gaps between these are not equal and not
#: measured; the ranks exist so "which of these two is weaker" is answerable, and
#: for nothing else. They are never averaged, summed, or shown to a reader.
SUPPORT_RANK: dict[SupportLevel, int] = {
    SupportLevel.LOW: 0,
    SupportLevel.MODERATE: 1,
    SupportLevel.STRONG: 2,
}


def weaker_of(a: SupportLevel, b: SupportLevel) -> SupportLevel:
    """The more cautious of two support levels."""
    return a if SUPPORT_RANK[a] <= SUPPORT_RANK[b] else b


# --------------------------------------------------------------------------- #
# Codes
# --------------------------------------------------------------------------- #


class ValidationCode(StrEnum):
    """Stable identifiers so Phase 10 can count failures by kind."""

    SOURCE_MISSING = "source_missing"
    CITATION_SPAN_MISSING = "citation_span_missing"
    SECTION_MISSING = "section_missing"
    UNGROUNDED_FACT = "ungrounded_fact"
    UNGROUNDED_CLAIM = "ungrounded_claim"
    STAGE_FAILED = "stage_failed"
    NO_MISSING_EVIDENCE = "no_missing_evidence"
    NON_AI_ALTERNATIVE_MISSING = "non_ai_alternative_missing"
    NO_BUILD_ALTERNATIVE_MISSING = "no_build_alternative_missing"
    CONTESTED_SUPPORT = "contested_support"
    SUPPORT_TOO_HIGH = "support_too_high"
    SUPPORT_REDUCED = "support_reduced"
    UNCITED_EVIDENCE = "uncited_evidence"
    CHALLENGE_FAILED = "challenge_failed"
    CHALLENGE_CONCERN = "challenge_concern"
    #: A note a stage produced about its own work — a staleness count, records
    #: kept by default, evidence set aside. Not a defect; context a reader needs.
    ANALYSIS_NOTE = "analysis_note"


#: Stages whose failure changes how far a reader should trust the brief, rather
#: than merely degrading it. Contradiction detection failing is indistinguishable
#: from "no conflicts found" unless it is said out loud; a recommendation that was
#: never challenged has not been through the process this product describes.
CRITICAL_STAGES = frozenset({"contradictions", "recommendation", "challenger"})


def _issue(
    code: ValidationCode,
    severity: ValidationSeverity,
    message: str,
    location: str = "",
) -> ValidationIssue:
    return ValidationIssue(code=code.value, severity=severity, message=message, location=location)


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def _check_provenance(report: ProvenanceReport) -> list[ValidationIssue]:
    """Source exists, and the quoted span exists inside it.

    Reported as two codes rather than one. A citation naming a record that was
    never retrieved means the analysis wandered outside its evidence; a citation
    naming a real record with text that is not in it means the quote was
    paraphrased or invented. Different causes, different fixes.
    """
    issues: list[ValidationIssue] = []

    for bad in report.failures_of(ResolutionFailure.UNKNOWN_EVIDENCE):
        issues.append(
            _issue(
                ValidationCode.SOURCE_MISSING,
                ValidationSeverity.ERROR,
                bad.describe(),
                bad.ref.location,
            )
        )
    for bad in report.failures_of(ResolutionFailure.QUOTE_NOT_FOUND):
        issues.append(
            _issue(
                ValidationCode.CITATION_SPAN_MISSING,
                ValidationSeverity.ERROR,
                bad.describe(),
                bad.ref.location,
            )
        )
    return issues


def _check_required_sections(brief: DecisionBrief) -> list[ValidationIssue]:
    """A brief missing one of these is not a decision brief."""
    required = (
        ("evidence", bool(brief.evidence), "No evidence was retrieved."),
        ("claims", bool(brief.claims), "No claims were extracted from the evidence."),
        ("alternatives", bool(brief.alternatives), "No alternatives were generated."),
        (
            "recommendation",
            brief.recommendation is not None,
            "No recommendation was produced.",
        ),
    )
    return [
        _issue(ValidationCode.SECTION_MISSING, ValidationSeverity.ERROR, message, name)
        for name, present, message in required
        if not present
    ]


def _check_assumptions_separated(brief: DecisionBrief) -> list[ValidationIssue]:
    """Assumptions must not be wearing a fact label.

    The checkable form of "separate assumptions from facts": a claim typed
    ``fact`` with nothing behind it is an assumption that has been promoted. The
    label is the whole difference between a PM weighing a finding and a PM
    weighing a guess, so an unsupported one is an error rather than a note.
    """
    issues: list[ValidationIssue] = []
    for claim in brief.claims:
        if claim.claim_type is ClaimType.FACT and not claim.is_grounded:
            issues.append(
                _issue(
                    ValidationCode.UNGROUNDED_FACT,
                    ValidationSeverity.ERROR,
                    f"Claim {claim.id} is labelled a fact but cites nothing. An unsupported "
                    "fact is an assumption; label it as one.",
                    f"claim {claim.id}",
                )
            )
    return issues


def _check_recommendation_grounding(brief: DecisionBrief) -> list[ValidationIssue]:
    if brief.recommendation is None:
        return []
    return [
        _issue(
            ValidationCode.UNGROUNDED_CLAIM,
            ValidationSeverity.ERROR,
            f"The recommendation rests on claim {claim.id}, which cites nothing.",
            f"recommendation claim {claim.id}",
        )
        for claim in brief.recommendation.ungrounded_claims
    ]


def _check_contradictions_are_visible(brief: DecisionBrief) -> list[ValidationIssue]:
    """A recommendation resting on contested evidence must show that it is contested.

    Reporting a contradiction in its own section and then quietly building the
    recommendation on one side of it is the exact failure this product exists to
    prevent, and it is the shape a reader is least likely to catch: every claim
    is cited, every citation resolves, and the conflict sits two sections away
    where nobody rereads it while weighing the answer.

    A warning rather than an error. Choosing a side of a live disagreement is a
    legitimate thing for a recommendation to do — doing it silently is not.
    """
    if brief.recommendation is None or not brief.contradictions:
        return []

    contested: dict[str, list[str]] = {}
    for found in brief.contradictions:
        for side in (found.side_a, found.side_b):
            seen = contested.setdefault(side.evidence_id, [])
            if found.id not in seen:
                seen.append(found.id)

    relied_on = {
        citation.evidence_id
        for claim in brief.recommendation.claims
        for citation in claim.citations
    }

    return [
        _issue(
            ValidationCode.CONTESTED_SUPPORT,
            ValidationSeverity.WARNING,
            f"The recommendation rests on {evidence_id}, which is one side of contradiction "
            f"{', '.join(contested[evidence_id])}. The conflict is reported elsewhere in this "
            "brief; a reader weighing the recommendation needs to know its support is "
            "contested rather than settled.",
            "recommendation",
        )
        for evidence_id in sorted(relied_on & set(contested))
    ]


def _check_stages(brief: DecisionBrief) -> list[ValidationIssue]:
    """Say plainly which analyses did not run.

    Without this, a stage that crashed and a stage that found nothing produce an
    identical-looking brief. They are not the same, and the difference decides
    how far the brief can be trusted.
    """
    if brief.run_trace is None:
        return []

    # Grouped by skill, not by attempt. A stage that failed, re-prompted, and
    # failed again leaves two failed entries in the trace for one lost analysis;
    # reporting it twice would inflate the issue count and read as two problems.
    # The last attempt's error is the one that stuck.
    last_error: dict[str, str] = {}
    for stage in brief.run_trace.failed_stages:
        last_error[stage.name.removesuffix("-retry")] = stage.error

    return [
        _issue(
            ValidationCode.STAGE_FAILED,
            ValidationSeverity.ERROR if base in CRITICAL_STAGES else ValidationSeverity.WARNING,
            f"The {base} stage did not complete ({error}). Its section of this brief is "
            "absent because it failed, not because there was nothing to report.",
            f"stage {base}",
        )
        for base, error in last_error.items()
    ]


def _check_gaps_surfaced(brief: DecisionBrief) -> list[ValidationIssue]:
    if brief.missing_evidence:
        return []
    return [
        _issue(
            ValidationCode.NO_MISSING_EVIDENCE,
            ValidationSeverity.WARNING,
            "No missing evidence was identified. Every real decision has something it "
            "cannot see, so an empty gaps section usually means the search was shallow.",
            "missing_evidence",
        )
    ]


def _check_alternatives(brief: DecisionBrief) -> list[ValidationIssue]:
    """The two options a tool built to help AI adoption is most likely to skip."""
    criteria = brief.request.criteria
    issues: list[ValidationIssue] = []

    if criteria.require_non_ai_alternative and not brief.has_non_ai_alternative:
        issues.append(
            _issue(
                ValidationCode.NON_AI_ALTERNATIVE_MISSING,
                ValidationSeverity.ERROR,
                "Every alternative involves AI. A decision process that cannot produce a "
                "non-AI option has assumed its answer.",
                "alternatives",
            )
        )
    if criteria.require_no_build_alternative and not brief.has_no_build_alternative:
        issues.append(
            _issue(
                ValidationCode.NO_BUILD_ALTERNATIVE_MISSING,
                ValidationSeverity.ERROR,
                "There is no no-change, defer, or further-research option. One is required, "
                "and it is often the right answer.",
                "alternatives",
            )
        )
    return issues


def _check_uncited_evidence(brief: DecisionBrief) -> list[ValidationIssue]:
    uncited = brief.uncited_evidence()
    if not uncited:
        return []
    return [
        _issue(
            ValidationCode.UNCITED_EVIDENCE,
            ValidationSeverity.WARNING,
            f"{len(uncited)} of {len(brief.evidence)} retrieved records are never cited: "
            f"{', '.join(e.id for e in uncited)}. Not an error, but worth a look — evidence "
            "the analysis never reached for is where a missed contradiction hides.",
            "evidence",
        )
    ]


def support_ceiling(brief: DecisionBrief, report: ProvenanceReport) -> SupportLevel | None:
    """The highest support level this brief's evidence can carry, or ``None``.

    ``None`` means nothing here constrains it. Two separate grounds, deliberately
    weighted differently:

    *   A broken citation *inside the recommendation* caps at low. The support is
        resting directly on something that could not be verified.
    *   A broken citation elsewhere, or a missing mandatory alternative, caps at
        moderate. The reasoning around the recommendation has a hole in it.
    """
    ceilings: list[SupportLevel] = []

    recommendation_locations = {
        u.ref.location for u in report.unresolved if u.ref.location.startswith("recommendation")
    }
    if recommendation_locations:
        ceilings.append(SupportLevel.LOW)
    if brief.recommendation is not None and brief.recommendation.ungrounded_claims:
        ceilings.append(SupportLevel.LOW)

    if report.unresolved:
        ceilings.append(SupportLevel.MODERATE)

    criteria = brief.request.criteria
    if criteria.require_non_ai_alternative and not brief.has_non_ai_alternative:
        ceilings.append(SupportLevel.MODERATE)
    if criteria.require_no_build_alternative and not brief.has_no_build_alternative:
        ceilings.append(SupportLevel.MODERATE)

    if not ceilings:
        return None
    lowest = ceilings[0]
    for level in ceilings[1:]:
        lowest = weaker_of(lowest, level)
    return lowest


# --------------------------------------------------------------------------- #
# The public checks
# --------------------------------------------------------------------------- #


def validate(
    brief: DecisionBrief,
    *,
    report: ProvenanceReport | None = None,
    extra: Sequence[ValidationIssue] = (),
) -> tuple[ValidationIssue, ...]:
    """Run every deterministic check. Reports; never mutates.

    Args:
        brief: The brief to check.
        report: A provenance report, if one was already computed. Recomputed when
            omitted, so a caller can never accidentally validate against a stale one.
        extra: Issues produced elsewhere — challenger findings, for instance —
            folded in so a reader has one list rather than several.
    """
    resolved_report = report if report is not None else check_provenance(brief)

    issues: list[ValidationIssue] = []
    issues.extend(_check_provenance(resolved_report))
    issues.extend(_check_required_sections(brief))
    issues.extend(_check_assumptions_separated(brief))
    issues.extend(_check_recommendation_grounding(brief))
    issues.extend(_check_contradictions_are_visible(brief))
    issues.extend(_check_stages(brief))
    issues.extend(_check_gaps_surfaced(brief))
    issues.extend(_check_alternatives(brief))
    issues.extend(_check_uncited_evidence(brief))

    ceiling = support_ceiling(brief, resolved_report)
    if (
        brief.recommendation is not None
        and ceiling is not None
        and SUPPORT_RANK[brief.recommendation.support_level] > SUPPORT_RANK[ceiling]
    ):
        issues.append(
            _issue(
                ValidationCode.SUPPORT_TOO_HIGH,
                ValidationSeverity.ERROR,
                f"Support is stated as {brief.recommendation.support_level.value}, but this "
                f"brief's evidence supports at most {ceiling.value}.",
                "recommendation",
            )
        )

    issues.extend(extra)
    return tuple(issues)


def enforce_support_ceiling(
    brief: DecisionBrief,
    *,
    report: ProvenanceReport | None = None,
    challenger_ceiling: SupportLevel | None = None,
) -> tuple[DecisionBrief, tuple[ValidationIssue, ...]]:
    """Lower the recommendation's support level where the evidence requires it.

    The only place in DecisionLens that reduces confidence, so there is exactly
    one thing to read to know when and why it happens. Idempotent: a brief that is
    already at or below its ceiling is returned unchanged with no issue.

    Args:
        challenger_ceiling: What the challenger asked for. Applied together with
            the evidence-derived ceiling rather than separately, so a reduction is
            one act with one explanation instead of two competing ones.
    """
    if brief.recommendation is None:
        return brief, ()

    resolved_report = report if report is not None else check_provenance(brief)
    evidence_ceiling = support_ceiling(brief, resolved_report)

    ceiling = evidence_ceiling
    if challenger_ceiling is not None:
        ceiling = challenger_ceiling if ceiling is None else weaker_of(ceiling, challenger_ceiling)

    current = brief.recommendation.support_level
    if ceiling is None or SUPPORT_RANK[current] <= SUPPORT_RANK[ceiling]:
        return brief, ()

    reasons: list[str] = []
    if evidence_ceiling is not None and SUPPORT_RANK[current] > SUPPORT_RANK[evidence_ceiling]:
        if resolved_report.unresolved:
            reasons.append(f"{len(resolved_report.unresolved)} citation(s) do not resolve")
        if brief.recommendation.ungrounded_claims:
            reasons.append(
                f"{len(brief.recommendation.ungrounded_claims)} supporting claim(s) cite nothing"
            )
        criteria = brief.request.criteria
        if criteria.require_non_ai_alternative and not brief.has_non_ai_alternative:
            reasons.append("no non-AI alternative was generated")
        if criteria.require_no_build_alternative and not brief.has_no_build_alternative:
            reasons.append("no no-build alternative was generated")
    if challenger_ceiling is not None and ceiling is challenger_ceiling:
        reasons.append("the challenger judged the draft overconfident")

    explanation = "; ".join(reasons) or "the evidence does not support the stated level"
    note = f"[Support reduced from {current.value} to {ceiling.value}: {explanation}.]"

    capped = brief.recommendation.model_copy(
        update={
            "support_level": ceiling,
            "support_basis": f"{brief.recommendation.support_basis} {note}".strip(),
        }
    )
    issue = _issue(
        ValidationCode.SUPPORT_REDUCED,
        ValidationSeverity.WARNING,
        f"Support was reduced from {current.value} to {ceiling.value}: {explanation}.",
        "recommendation",
    )
    return brief.model_copy(update={"recommendation": capped}), (issue,)

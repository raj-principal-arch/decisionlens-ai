"""Deterministic citation resolution.

The mechanism behind the product's central claim. A DecisionBrief asserts things
and points at evidence for each one; this module checks every pointer by string
resolution against the retrieved records. Nothing here asks a model anything —
whether a quote appears in a document is not a matter of opinion, and a check
that could be argued with is not a check.

Two distinctions the rest of the system depends on:

*   **A missing source and a missing quote are different failures.** An
    ``unknown_evidence`` citation names a record that was never retrieved: the
    analysis is talking about something outside its own evidence set. A
    ``quote_not_found`` citation names a real record but text that is not in it:
    the quote was paraphrased, or invented. They have different causes and
    different fixes, so they are never collapsed into one error.
*   **Every citation carries where it came from.** ``DecisionBrief.all_citations``
    returns a flat tuple, which is enough to count failures but not to report
    them — "3 citations do not resolve" sends a reader hunting. A
    :class:`CitationRef` names the claim, contradiction, or alternative it was
    found in, so validation can say exactly what to look at.

An *unresolvable* citation is not the same as an *ungrounded* claim. A claim with
a broken citation tried to show its work and failed; a claim with no citations at
all never tried. Both are reported, separately, because a reader draws different
conclusions from each.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from decision_lens.models import Citation, Claim, DecisionBrief, EvidenceRecord

__all__ = [
    "BriefSection",
    "CitationRef",
    "ProvenanceReport",
    "ResolutionFailure",
    "UnresolvedCitation",
    "check_provenance",
    "iter_citations",
]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class BriefSection(StrEnum):
    """Where in a brief a citation was found.

    Machine-readable so Phase 10 can report citation validity per section rather
    than as one number: a brief whose failures are all in the recommendation is a
    different problem from one whose failures are scattered.
    """

    CLAIMS = "claims"
    CONTRADICTIONS = "contradictions"
    PRIORITY_EXCEPTIONS = "priority_exceptions"
    ALTERNATIVES = "alternatives"
    ASSESSMENTS = "assessments"
    RECOMMENDATION = "recommendation"


class ResolutionFailure(StrEnum):
    """Why a citation could not be resolved."""

    #: Names an evidence id that is not in the brief's evidence set.
    UNKNOWN_EVIDENCE = "unknown_evidence"
    #: Names a real record, but the quoted text does not appear in it.
    QUOTE_NOT_FOUND = "quote_not_found"


class CitationRef(_Frozen):
    """One citation, plus enough context to tell a reader where to look."""

    citation: Citation
    section: BriefSection
    #: Human-readable path, e.g. ``claim CL-003`` or ``contradiction CN-001 side_a``.
    location: str

    def failure(self, by_id: dict[str, EvidenceRecord]) -> ResolutionFailure | None:
        """Resolve against the evidence set. ``None`` means the citation is good."""
        record = by_id.get(self.citation.evidence_id)
        if record is None:
            return ResolutionFailure.UNKNOWN_EVIDENCE
        if not record.contains(self.citation.quote):
            return ResolutionFailure.QUOTE_NOT_FOUND
        return None

    def describe(self) -> str:
        quote = self.citation.quote
        shown = quote if len(quote) <= 60 else f"{quote[:57]}..."
        return f"{self.location} cites {self.citation.evidence_id} {shown!r}"


class UnresolvedCitation(_Frozen):
    """A citation that did not resolve, and why."""

    ref: CitationRef
    reason: ResolutionFailure

    def describe(self) -> str:
        if self.reason is ResolutionFailure.UNKNOWN_EVIDENCE:
            return (
                f"{self.ref.location} cites {self.ref.citation.evidence_id}, which is not in "
                "the evidence retrieved for this decision."
            )
        return (
            f"{self.ref.describe()}, but that text does not appear in the record. "
            "The quote must be verbatim."
        )


class ProvenanceReport(_Frozen):
    """The result of checking every pointer in a brief."""

    refs: tuple[CitationRef, ...] = ()
    unresolved: tuple[UnresolvedCitation, ...] = ()
    #: Claims that carry no citation at all — a different failure from a broken one.
    ungrounded_claims: tuple[Claim, ...] = ()
    #: Retrieved but never referenced. Not an error; a signal about coverage.
    uncited_evidence_ids: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return len(self.refs)

    @property
    def resolved(self) -> int:
        return self.total - len(self.unresolved)

    @property
    def is_clean(self) -> bool:
        return not self.unresolved

    @property
    def validity(self) -> float | None:
        """Fraction of citations that resolve.

        ``None`` when there are no citations at all, which is deliberately not
        reported as 1.0: a brief that cites nothing has perfect citation validity
        only in the sense that it never risked anything.
        """
        return None if not self.total else self.resolved / self.total

    def failures_of(self, reason: ResolutionFailure) -> tuple[UnresolvedCitation, ...]:
        return tuple(u for u in self.unresolved if u.reason is reason)


# --------------------------------------------------------------------------- #
# Walking a brief
# --------------------------------------------------------------------------- #


def _claim_refs(claims: tuple[Claim, ...], section: BriefSection, prefix: str) -> list[CitationRef]:
    refs: list[CitationRef] = []
    for claim in claims:
        for citation in claim.citations:
            refs.append(
                CitationRef(citation=citation, section=section, location=f"{prefix} {claim.id}")
            )
        for citation in claim.opposing_citations:
            refs.append(
                CitationRef(
                    citation=citation,
                    section=section,
                    location=f"{prefix} {claim.id} (opposing)",
                )
            )
    return refs


def iter_citations(brief: DecisionBrief) -> tuple[CitationRef, ...]:
    """Every citation in a brief, each tagged with where it was found.

    Kept deliberately in step with :meth:`DecisionBrief.all_citations`. A test
    asserts the two return the same citations in the same order, so this cannot
    drift into checking a subset of the brief while appearing to check all of it.
    """
    refs: list[CitationRef] = _claim_refs(brief.claims, BriefSection.CLAIMS, "claim")

    for contradiction in brief.contradictions:
        for side, citation in (("side_a", contradiction.side_a), ("side_b", contradiction.side_b)):
            refs.append(
                CitationRef(
                    citation=citation,
                    section=BriefSection.CONTRADICTIONS,
                    location=f"contradiction {contradiction.id} {side}",
                )
            )

    for exception in brief.priority_exceptions:
        for citation in exception.citations:
            refs.append(
                CitationRef(
                    citation=citation,
                    section=BriefSection.PRIORITY_EXCEPTIONS,
                    location=f"priority exception {exception.id}",
                )
            )

    for alternative in brief.alternatives:
        for citation in alternative.supporting:
            refs.append(
                CitationRef(
                    citation=citation,
                    section=BriefSection.ALTERNATIVES,
                    location=f"alternative {alternative.id} (supporting)",
                )
            )
        for citation in alternative.opposing:
            refs.append(
                CitationRef(
                    citation=citation,
                    section=BriefSection.ALTERNATIVES,
                    location=f"alternative {alternative.id} (opposing)",
                )
            )
        for assessment in alternative.assessments:
            for citation in assessment.citations:
                refs.append(
                    CitationRef(
                        citation=citation,
                        section=BriefSection.ASSESSMENTS,
                        location=(f"alternative {alternative.id} / {assessment.dimension.value}"),
                    )
                )

    if brief.recommendation:
        refs.extend(
            _claim_refs(
                brief.recommendation.claims, BriefSection.RECOMMENDATION, "recommendation claim"
            )
        )

    return tuple(refs)


def check_provenance(brief: DecisionBrief) -> ProvenanceReport:
    """Resolve every citation in a brief against its evidence."""
    by_id = brief.evidence_by_id()
    refs = iter_citations(brief)

    unresolved: list[UnresolvedCitation] = []
    for ref in refs:
        reason = ref.failure(by_id)
        if reason is not None:
            unresolved.append(UnresolvedCitation(ref=ref, reason=reason))

    ungrounded = [c for c in brief.claims if not c.is_grounded]
    if brief.recommendation:
        ungrounded.extend(c for c in brief.recommendation.claims if not c.is_grounded)

    return ProvenanceReport(
        refs=refs,
        unresolved=tuple(unresolved),
        ungrounded_claims=tuple(ungrounded),
        uncited_evidence_ids=tuple(e.id for e in brief.uncited_evidence()),
    )

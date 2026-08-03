"""The answer key for one case, and the rules for scoring against it.

Ground truth was a loose JSON dictionary held together by assertions written for
one specific file. That was survivable while there was one case. It stops being
survivable at eleven, because the failure mode is silent: a ground-truth entry
with a misspelled key is simply not read, the metric it feeds quietly measures
nothing, and the number still prints.

So the schema is a model. A case whose answer key does not parse cannot be
scored at all, which is the correct outcome — a measurement taken against a
malformed answer key is worse than no measurement, since it looks like one.

Two conventions run through this file.

**Every claim about the evidence carries the span it rests on.** `source` names a
file in the case directory and `span` quotes it verbatim. That is the same
discipline the product imposes on itself, applied to the thing judging it: an
answer key that asserts a contradiction exists without quoting both sides is an
opinion about the corpus, not a fact about it. :func:`spans` walks the whole
structure so every one of them can be checked against the files on disk.

**`must_detect` separates the graded from the noted.** Recall is measured only
over entries marked `must_detect`. Everything else is recorded because it is
true and worth knowing, but a system that misses it is not marked down —
otherwise the recall denominator becomes whatever the author happened to notice
while writing the corpus, which is not a property of the system under test.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "CredibleAlternative",
    "EvidenceHazard",
    "ExpectedAlternatives",
    "ExpectedContradiction",
    "ExpectedGap",
    "ForbiddenClaim",
    "GapImpact",
    "GroundTruth",
    "IrrelevantEvidence",
    "KnownAssumption",
    "KnownConstraint",
    "KnownFact",
    "KnownOpinion",
    "RecommendationRestraint",
    "ScoringRules",
    "Sourced",
    "SpanRef",
]


class _HasId(Protocol):
    """Structural type for the id walk: every answer-key entry carries one."""

    @property
    def id(self) -> str: ...


class _Anchored(Protocol):
    """Entries that optionally point at the line which tempts them."""

    @property
    def id(self) -> str: ...

    @property
    def anchor(self) -> SpanRef | None: ...


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class GapImpact(StrEnum):
    """How much a missing piece of evidence would change the decision."""

    WOULD_CHANGE_RECOMMENDATION = "would_change_recommendation"
    WOULD_CHANGE_CONFIDENCE = "would_change_confidence"
    WOULD_CHANGE_SEQUENCING = "would_change_sequencing"
    WOULD_REFINE_SCOPE = "would_refine_scope"
    CONTEXT_ONLY = "context_only"


class SpanRef(_Frozen):
    """A verbatim quotation from one named file in the case directory."""

    source: str = Field(min_length=1)
    span: str = Field(min_length=1)


class Sourced(_Frozen):
    """Base for any entry that must point at real text.

    Kept separate from :class:`SpanRef` because most entries carry an id and a
    statement alongside the quotation, and inheriting is cheaper than repeating.
    """

    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    span: str = Field(min_length=1)


class ExpectedContradiction(_Frozen):
    """Two statements in the corpus that cannot both be acted on as written."""

    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    side_a: SpanRef
    side_b: SpanRef
    why_it_matters: str = Field(min_length=1)
    #: What would settle it. Required, because a contradiction nobody can resolve
    #: is a complaint rather than a finding, and the product promises to say what
    #: would settle each conflict it raises.
    how_to_resolve: str = Field(min_length=1)
    must_detect: bool = True

    @model_validator(mode="after")
    def _sides_must_differ(self) -> ExpectedContradiction:
        if self.side_a == self.side_b:
            raise ValueError(f"{self.id}: both sides quote the same span")
        return self


class ExpectedGap(_Frozen):
    """Evidence that does not exist and whose absence changes the decision."""

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    impact: GapImpact
    why_it_matters: str = Field(min_length=1)
    how_to_obtain: str = Field(min_length=1)
    #: Where the corpus comes closest to answering the question without doing so
    #: — the line that shows the gap is real rather than merely unsearched.
    anchor: SpanRef | None = None
    #: Whether the corpus was actually searched for this. A gap nobody looked for
    #: is a guess about what is absent.
    was_searched: bool = True
    must_detect: bool = True


class KnownFact(Sourced):
    statement: str = Field(min_length=1)


class KnownAssumption(_Frozen):
    """Carries no span: an assumption is precisely what the corpus does not say."""

    id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    why_it_is_an_assumption: str = Field(min_length=1)
    #: The line that gets mistaken for evidence of it.
    anchor: SpanRef | None = None


class KnownOpinion(Sourced):
    statement: str = Field(min_length=1)
    #: What treating this as evidence would wrongly license.
    must_not_be_treated_as: str = Field(min_length=1)


class KnownConstraint(Sourced):
    statement: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    #: Options this rules out or bounds. Empty when the constraint shapes the
    #: decision without eliminating anything outright.
    blocks: tuple[str, ...] = ()


class GovernanceIssue(Sourced):
    statement: str = Field(min_length=1)
    affects: tuple[str, ...] = ()
    #: Optional: for most entries the statement already carries the reason, and
    #: demanding a separate sentence produced restatement rather than insight.
    why_it_matters: str = ""


class EvidenceHazard(Sourced):
    """A property of the corpus that invites a wrong reading of correct data."""

    hazard: str = Field(min_length=1)
    description: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    must_detect: bool = False


class IrrelevantEvidence(Sourced):
    why_irrelevant: str = Field(min_length=1)


class ForbiddenClaim(_Frozen):
    """A conclusion the corpus tempts but does not support.

    The most useful entries in an answer key. Recall measures what a system
    found; these measure what it was willing to say without support, which is
    the failure that actually costs somebody a decision.
    """

    id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    why_forbidden: str = Field(min_length=1)
    #: The hazard id that makes this claim tempting, when there is one.
    tempted_by: str = ""
    #: The line a reader would point at while making the forbidden claim.
    anchor: SpanRef | None = None


class CredibleAlternative(_Frozen):
    """An option a competent PM could defend on this evidence.

    Not a required answer. Options are not scored by matching this list — a
    system that proposes something sensible nobody thought of is not wrong.
    """

    name: str = Field(min_length=1)
    option_kind: str = Field(min_length=1)
    horizon: str = Field(min_length=1)
    support: str = Field(min_length=1)
    note: str = ""


class ExpectedAlternatives(_Frozen):
    must_include_at_least_one_non_ai: bool = True
    must_include_at_least_one_no_build_defer_or_research: bool = True
    credible: tuple[CredibleAlternative, ...] = ()


class ForbiddenRecommendation(_Frozen):
    option_kind: str = Field(min_length=1)
    why: str = Field(min_length=1)


class RecommendationRestraint(_Frozen):
    """How much confidence the evidence can carry, and what must be said aloud.

    `single_correct_answer` is usually false and that is deliberate. Most real
    decisions have several defensible next steps, and an answer key that insists
    on one would score restraint as error.
    """

    single_correct_answer: bool = False
    max_defensible_support_level: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    defensible_next_steps: tuple[str, ...] = ()
    must_not_recommend_without_conditions: tuple[ForbiddenRecommendation, ...] = ()
    restraint_signals_that_must_appear: tuple[str, ...] = ()


class ScoringRules(_Frozen):
    """Written down before results exist, so they cannot be tuned to them."""

    recall_denominator: str = Field(min_length=1)
    unplanted_findings: str = Field(min_length=1)
    span_matching: str = Field(min_length=1)
    restraint_scoring: str = Field(min_length=1)
    forbidden_claims: str = Field(min_length=1)


class GroundTruth(_Frozen):
    """Everything known to be true about one case."""

    case_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    synthetic: bool
    notice: str = Field(min_length=1)
    #: Who wrote this and why that limits what it can prove. Required, so no case
    #: can ship pretending to be a neutral held-out measurement.
    authoring_limitation: str = Field(min_length=1)
    question: str = Field(min_length=1)
    desired_outcome: str = Field(min_length=1)
    scoring_rules: ScoringRules
    expected_contradictions: tuple[ExpectedContradiction, ...] = ()
    expected_missing_evidence: tuple[ExpectedGap, ...] = ()
    known_facts: tuple[KnownFact, ...] = ()
    known_assumptions: tuple[KnownAssumption, ...] = ()
    known_opinions: tuple[KnownOpinion, ...] = ()
    evidence_hazards: tuple[EvidenceHazard, ...] = ()
    known_constraints: tuple[KnownConstraint, ...] = ()
    governance_issues: tuple[GovernanceIssue, ...] = ()
    unsupported_claims_the_system_must_not_make: tuple[ForbiddenClaim, ...] = ()
    irrelevant_evidence: tuple[IrrelevantEvidence, ...] = ()
    expected_alternative_categories: ExpectedAlternatives
    recommendation_restraint: RecommendationRestraint

    @model_validator(mode="after")
    def _must_declare_itself_synthetic(self) -> GroundTruth:
        if not self.synthetic:
            raise ValueError(
                f"{self.case_id}: every case in this repository is synthetic. A ground "
                "truth claiming otherwise would assert real data that does not exist."
            )
        return self

    @model_validator(mode="after")
    def _ids_are_unique(self) -> GroundTruth:
        seen: dict[str, str] = {}
        for group, entries in self._id_groups():
            for entry in entries:
                previous = seen.get(entry.id)
                if previous is not None:
                    raise ValueError(f"id {entry.id!r} used in both {previous} and {group}")
                seen[entry.id] = group
        return self

    def _id_groups(self) -> Iterator[tuple[str, Sequence[_HasId]]]:
        yield "expected_contradictions", self.expected_contradictions
        yield "expected_missing_evidence", self.expected_missing_evidence
        yield "known_facts", self.known_facts
        yield "known_assumptions", self.known_assumptions
        yield "known_opinions", self.known_opinions
        yield "evidence_hazards", self.evidence_hazards
        yield "known_constraints", self.known_constraints
        yield "governance_issues", self.governance_issues
        yield "unsupported_claims", self.unsupported_claims_the_system_must_not_make
        yield "irrelevant_evidence", self.irrelevant_evidence

    def spans(self) -> tuple[tuple[str, SpanRef], ...]:
        """Every (owner id, quotation) in the answer key, at any depth.

        Used to check the key against the files on disk. Anything that quotes the
        corpus has to appear here, or it goes unchecked and can drift out of
        agreement with the evidence it claims to describe.
        """
        found: list[tuple[str, SpanRef]] = []
        anchored_entries: tuple[_Anchored, ...] = (
            *self.expected_missing_evidence,
            *self.known_assumptions,
            *self.unsupported_claims_the_system_must_not_make,
        )
        for anchored in anchored_entries:
            if anchored.anchor is not None:
                found.append((anchored.id, anchored.anchor))
        for entry in self.expected_contradictions:
            found.append((entry.id, entry.side_a))
            found.append((entry.id, entry.side_b))
        for group in (
            self.known_facts,
            self.known_opinions,
            self.known_constraints,
            self.governance_issues,
            self.evidence_hazards,
            self.irrelevant_evidence,
        ):
            found.extend((e.id, SpanRef(source=e.source, span=e.span)) for e in group)
        return tuple(found)

    def graded_contradictions(self) -> tuple[ExpectedContradiction, ...]:
        return tuple(c for c in self.expected_contradictions if c.must_detect)

    def graded_gaps(self) -> tuple[ExpectedGap, ...]:
        return tuple(g for g in self.expected_missing_evidence if g.must_detect)

    def sources(self) -> frozenset[str]:
        """Every case file the answer key refers to."""
        return frozenset(ref.source for _, ref in self.spans())

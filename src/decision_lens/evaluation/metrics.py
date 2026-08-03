"""Scoring one brief against one answer key.

Everything here is deterministic. Nothing in this module asks a model anything,
which is the point: these are the numbers the evaluation's argument rests on, and
a measurement produced by the same family of system being measured is not
independent. Judgment-dependent checks — whether a brief *made* a forbidden
claim, whether a reported gap is the same gap the key describes — live in
:mod:`decision_lens.evaluation.judge` and are labelled as model-based wherever
they are reported.

The matching rules were written into each case's `scoring_rules` before any
result existed, and this module implements them rather than improving on them:

**Recall counts only `must_detect` entries.** The rest are recorded and not
graded. A denominator made of everything the author happened to notice is a
property of the author, not of the system.

**A span matches when it resolves to the same evidence record.** Not string
equality — a system may quote a longer or shorter passage from the same record
and be equally right. So a reported contradiction matches a planted one when it
cites both of the records the planted one cites.

**An unplanted finding is not a false positive.** The corpus has one author and
may contain conflicts they did not intend. Reporting one is set aside for
adjudication, never silently counted as an error, because scoring it wrong by
default would penalise the system for being right.

**Naming the right option while overstating support is a restraint failure,**
not a correct recommendation. Restraint is scored separately from selection for
exactly that reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from decision_lens.evaluation.ground_truth import GroundTruth, SpanRef
from decision_lens.models import DecisionBrief, EvidenceRecord, SupportLevel
from decision_lens.quoting import normalise

__all__ = [
    "CaseScore",
    "RecallResult",
    "RecordIndex",
    "score_brief",
]

#: Ordered weakest to strongest, so "did it claim more than the key allows" is a
#: comparison rather than a table of special cases.
_SUPPORT_ORDER: tuple[str, ...] = ("low", "moderate", "strong")

# Whether an option counts as non-AI or as no-build is asked of the brief
# itself, via DecisionBrief.has_non_ai_alternative and .has_no_build_alternative.
# A second table of option kinds here would be a copy of the product's own
# definition, free to drift from it, and the evaluation would then be scoring a
# rule the product does not enforce.


class RecordIndex:
    """Resolves a ground-truth quotation to the evidence record holding it.

    The answer key names files; the brief cites record ids. Nothing can be
    compared until one is expressed in terms of the other, and that translation
    is this class's whole job.
    """

    def __init__(self, records: tuple[EvidenceRecord, ...]) -> None:
        self._records = records
        self._folded = {r.id: normalise(r.content)[0] for r in records}

    def resolve(self, ref: SpanRef) -> str | None:
        """The record id whose content holds this span, or None if ambiguous.

        Ambiguity returns None rather than a guess. A span appearing in two
        records cannot identify one of them, and inventing a preference here
        would quietly decide a recall outcome on a coin toss.
        """
        candidates = [r.id for r in self._records if r.source_id == ref.source]
        exact = [rid for rid in candidates if ref.span in self._content(rid)]
        if len(exact) == 1:
            return exact[0]
        folded_span = normalise(ref.span)[0].strip()
        loose = [rid for rid in candidates if folded_span in self._folded[rid]]
        return loose[0] if len(loose) == 1 else None

    def _content(self, record_id: str) -> str:
        return next(r.content for r in self._records if r.id == record_id)


@dataclass(frozen=True)
class RecallResult:
    """How many graded entries were found, and which were missed."""

    found: tuple[str, ...]
    missed: tuple[str, ...]
    #: Reported findings matching no graded entry. Held for adjudication, never
    #: scored as wrong — see the module docstring.
    unadjudicated: int = 0
    #: Graded entries whose spans could not be resolved to a record. These are
    #: excluded from the denominator: a key entry the harness cannot locate is a
    #: broken measurement, not a miss by the system.
    unresolvable: tuple[str, ...] = ()

    @property
    def graded(self) -> int:
        return len(self.found) + len(self.missed)

    @property
    def recall(self) -> float | None:
        """None rather than 0.0 when nothing is graded — no data is not a zero."""
        return len(self.found) / self.graded if self.graded else None


@dataclass
class CaseScore:
    """Every deterministic measurement for one brief on one case."""

    case_id: str
    arm: str
    contradictions: RecallResult
    gaps_reported: int
    citations_total: int = 0
    citations_resolved: int = 0
    claims_total: int = 0
    claims_uncited: int = 0
    alternatives: int = 0
    has_non_ai_option: bool = False
    has_no_build_option: bool = False
    recommended_option_exists: bool = False
    support_claimed: str = ""
    support_ceiling: str = ""
    blocking_errors: int = 0
    warnings: int = 0
    failed_stages: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)

    @property
    def citation_validity(self) -> float | None:
        if not self.citations_total:
            return None
        return self.citations_resolved / self.citations_total

    @property
    def overstates_support(self) -> bool:
        """Did the brief claim more confidence than the key allows?

        Unknown levels are treated as not overstating. Guessing that an
        unrecognised label means "too strong" would invent a failure.
        """
        if self.support_claimed not in _SUPPORT_ORDER:
            return False
        if self.support_ceiling not in _SUPPORT_ORDER:
            return False
        return _SUPPORT_ORDER.index(self.support_claimed) > _SUPPORT_ORDER.index(
            self.support_ceiling
        )

    @property
    def actionable(self) -> bool:
        """Whether a reader could act on this at all.

        A brief with a recommendation pointing at an option it did not produce
        is not a weaker answer, it is not an answer.
        """
        return bool(self.support_claimed) and self.recommended_option_exists


def score_brief(
    brief: DecisionBrief,
    truth: GroundTruth,
    records: tuple[EvidenceRecord, ...],
) -> CaseScore:
    """Measure one brief against one answer key. Never raises."""
    index = RecordIndex(records)
    score = CaseScore(
        case_id=truth.case_id,
        arm="",
        contradictions=_contradiction_recall(brief, truth, index),
        gaps_reported=len(brief.missing_evidence),
    )
    _score_citations(brief, records, score)
    _score_alternatives(brief, score)
    _score_recommendation(brief, truth, score)
    _score_validation(brief, score)
    return score


def _contradiction_recall(
    brief: DecisionBrief, truth: GroundTruth, index: RecordIndex
) -> RecallResult:
    """A planted conflict counts as found when both its records are cited."""
    reported: list[frozenset[str]] = [
        frozenset({c.side_a.evidence_id, c.side_b.evidence_id}) for c in brief.contradictions
    ]
    matched_reports: set[int] = set()
    found: list[str] = []
    missed: list[str] = []
    unresolvable: list[str] = []

    for expected in truth.graded_contradictions():
        a = index.resolve(expected.side_a)
        b = index.resolve(expected.side_b)
        if a is None or b is None:
            unresolvable.append(expected.id)
            continue
        wanted = frozenset({a, b})
        hit = next(
            (i for i, pair in enumerate(reported) if pair == wanted and i not in matched_reports),
            None,
        )
        if hit is None:
            missed.append(expected.id)
        else:
            matched_reports.add(hit)
            found.append(expected.id)

    return RecallResult(
        found=tuple(found),
        missed=tuple(missed),
        unadjudicated=len(reported) - len(matched_reports),
        unresolvable=tuple(unresolvable),
    )


def _score_citations(
    brief: DecisionBrief, records: tuple[EvidenceRecord, ...], score: CaseScore
) -> None:
    by_id = {r.id: r for r in records}
    total = 0
    resolved = 0
    for claim in brief.claims:
        score.claims_total += 1
        if not claim.citations:
            score.claims_uncited += 1
        for citation in (*claim.citations, *claim.opposing_citations):
            total += 1
            record = by_id.get(citation.evidence_id)
            if record is not None and record.contains(citation.quote):
                resolved += 1
    for alternative in brief.alternatives:
        for citation in (*alternative.supporting, *alternative.opposing):
            total += 1
            record = by_id.get(citation.evidence_id)
            if record is not None and record.contains(citation.quote):
                resolved += 1
    score.citations_total = total
    score.citations_resolved = resolved


def _score_alternatives(brief: DecisionBrief, score: CaseScore) -> None:
    score.alternatives = len(brief.alternatives)
    score.has_non_ai_option = brief.has_non_ai_alternative
    score.has_no_build_option = brief.has_no_build_alternative


def _score_recommendation(brief: DecisionBrief, truth: GroundTruth, score: CaseScore) -> None:
    score.support_ceiling = truth.recommendation_restraint.max_defensible_support_level
    recommendation = brief.recommendation
    if recommendation is None:
        score.notes.append("no recommendation was produced")
        return
    level = recommendation.support_level
    score.support_claimed = level.value if isinstance(level, SupportLevel) else str(level)
    selected = recommendation.selected_alternative_id
    score.recommended_option_exists = any(a.id == selected for a in brief.alternatives)
    if not score.recommended_option_exists:
        score.notes.append(
            f"recommendation selects {selected!r}, which is not among the "
            f"{len(brief.alternatives)} options in the brief"
        )


def _score_validation(brief: DecisionBrief, score: CaseScore) -> None:
    score.blocking_errors = sum(1 for i in brief.validation_issues if i.blocks_presentation)
    score.warnings = len(brief.validation_issues) - score.blocking_errors
    trace = brief.run_trace
    if trace is not None:
        score.failed_stages = tuple(s.name for s in trace.stages if not s.succeeded)

"""The controlled DecisionLens workflow.

One orchestrator running a fixed sequence. There is no planner here, no agent
choosing its next move, and no loop that continues until something decides it is
finished. The sequence is written out in `run` and does not vary by input, which
is what makes a wrong answer attributable to a stage rather than to a system.
That attribution is the entire difference between this and the single-call
baseline it is measured against.

Four properties the implementation is built around:

*   **Partial failure degrades the brief; it never aborts the run.** A stage that
    fails is recorded in the trace and produces a validation issue saying its
    section is absent *because it failed*, not because there was nothing to
    report. A brief missing one analysis is more useful than no brief, provided
    the gap is impossible to miss.
*   **The model never supplies evidence.** Skills receive records the connectors
    retrieved and return judgments about them. The brief is assembled around the
    real records, so a citation either resolves against retrieved text or is
    reported — there is no path by which analysis can introduce its own sources.
*   **Confidence is reduced in exactly one place.** The challenger and the
    evidence checks both feed :func:`~decision_lens.validation.enforce_support_ceiling`,
    which applies the weakest ceiling once and writes its reason into the brief.
*   **The PM's decision is not produced here.** ``run`` returns a recommendation.
    :func:`record_pm_decision` is a separate call a person makes afterwards, and
    keeping them apart is what allows disagreement between the two to be measured.

Retrieval is written as an independent pass per source so it can be parallelised
later without restructuring anything. It is sequential today because the only
connector reads local files, and concurrency that buys nothing costs clarity.

The workflow::

    DecisionRequest
          |
          v
    check request ......... no evidence source configured -> DecisionLensError
          |
          v
    retrieve .............. each source independently; a dead one is a note
          |
          v
    normalize ............. drop repeated ids and duplicate passages
          |
          +-- no evidence -> a brief that says so; no skill is run
          |
          v
    relevance ............. which records bear on the decision
    classification ........ claims, and how each should be read
    contradictions ........ conflicts, surfaced and left unresolved
    missing evidence ...... what the decision needs and does not have
    alternatives .......... options, including non-AI and no-build
    recommendation ........ a draft, never an approval
    challenger ............ the eight fixed questions
          |
          v
    provenance ............ resolve every citation against real text
    support ceiling ....... lower confidence once, with its reason
    validate .............. deterministic checks -> ValidationIssue
          |
          v
    DecisionBrief + RunTrace
          |
          v   a separate call, made by a person
    record_pm_decision -> PMDecision

Any stage from relevance to challenger may fail. The run continues, and the
absent section is reported as absent-because-it-failed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import TypeVar

from pydantic import BaseModel

from decision_lens.connectors.base import EvidenceSource, EvidenceSourceError
from decision_lens.llm import ModelProvider
from decision_lens.models import (
    Alternative,
    Claim,
    Contradiction,
    DecisionBrief,
    DecisionRequest,
    EvidenceClassification,
    EvidenceRecord,
    EvidenceRequest,
    MissingEvidence,
    PMDecision,
    Recommendation,
    RunStage,
    RunTrace,
    ValidationIssue,
    ValidationSeverity,
)
from decision_lens.provenance import check_provenance
from decision_lens.skills import (
    SKILL_TIMEOUT_SECONDS,
    AlternativesSkill,
    ClassificationSkill,
    ContradictionsSkill,
    MissingEvidenceSkill,
    RecommendationSkill,
    RelevanceSkill,
    Skill,
    SkillContext,
    SkillError,
)
from decision_lens.skills.challenger import (
    ChallengeOutput,
    ChallengerSkill,
    ChallengeVerdict,
)
from decision_lens.validation import (
    ValidationCode,
    enforce_support_ceiling,
    validate,
)

T = TypeVar("T", bound=BaseModel)

__all__ = ["DecisionLens", "DecisionLensError", "record_pm_decision"]


class DecisionLensError(RuntimeError):
    """The workflow could not run at all.

    Deliberately rare. Only conditions that make a brief meaningless raise —
    having no evidence source configured, for instance. Everything downstream of
    retrieval degrades instead, because a brief that reports its own holes is
    worth more than an exception.
    """

    def __init__(self, message: str, trace: RunTrace | None = None) -> None:
        super().__init__(message)
        self.trace = trace


class DecisionLens:
    """The controlled workflow.

    Args:
        provider: Any `ModelProvider` — the cached demo provider, a live adapter,
            or a test double. The orchestrator neither knows nor cares which.
        sources: One or more evidence sources. Retrieved from in order.
        as_of: The date staleness is measured against. Injected so a run is
            reproducible.
        clock: Fixed timestamp for the run, for the same reason.
        allow_retry: Whether skills may re-prompt once after a broken requirement.
        timeout_seconds: Per-skill deadline.
        progress: Called with one line as each stage starts and finishes. A live
            run takes minutes and produced no output at all until it was over,
            which is indistinguishable from being hung. Same callback shape the
            recorder already defines and the CLI already consumes.
    """

    def __init__(
        self,
        provider: ModelProvider,
        sources: Sequence[EvidenceSource],
        *,
        as_of: date | None = None,
        clock: datetime | None = None,
        allow_retry: bool = True,
        timeout_seconds: float = SKILL_TIMEOUT_SECONDS,
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.provider = provider
        self.sources = tuple(sources)
        self.as_of = as_of
        self.clock = clock
        self.allow_retry = allow_retry
        self.timeout_seconds = timeout_seconds
        self.progress = progress

    def _say(self, line: str) -> None:
        if self.progress is not None:
            self.progress(line)

    def _now(self) -> datetime:
        return self.clock or datetime.now()

    # -- 1. the request ------------------------------------------------------ #

    def _check_request(self, request: DecisionRequest) -> None:
        """Shape is already guaranteed by the model; this checks the run is possible."""
        if not self.sources:
            raise DecisionLensError(
                f"No evidence source is configured, so nothing can be retrieved for "
                f"{request.id!r}. DecisionLens does not answer from the model's own "
                "knowledge: a brief with no evidence behind it is the thing this product "
                "exists to prevent."
            )

    # -- 2. retrieval -------------------------------------------------------- #

    def _retrieve(
        self, request: DecisionRequest, stages: list[RunStage], notes: list[str]
    ) -> tuple[EvidenceRecord, ...]:
        """Ask every source. One dead connector degrades the brief, it does not stop it.

        Each source is independent of the others, which is what would make this
        safe to parallelise later.
        """
        evidence_request = EvidenceRequest(
            requested_by=request.user,
            product_area=request.user.product_area,
            time_period=request.time_period,
            labels=request.labels,
        )

        collected: list[EvidenceRecord] = []
        for source in self.sources:
            name = f"retrieve:{source.source_system.value}"
            started = self._now()
            try:
                records = tuple(source.retrieve(evidence_request))
            except EvidenceSourceError as exc:
                stages.append(RunStage(name=name, started_at=started, error=str(exc)))
                notes.append(
                    f"The {source.source_system.value} source failed and contributed no "
                    f"evidence: {exc}"
                )
                continue
            stages.append(RunStage(name=name, started_at=started, ended_at=self._now()))
            collected.extend(records)

        return tuple(collected)

    # -- 3. normalization ---------------------------------------------------- #

    @staticmethod
    def _normalize(
        records: Sequence[EvidenceRecord], notes: list[str]
    ) -> tuple[EvidenceRecord, ...]:
        """Drop duplicates across sources, keeping the first of each.

        Two rules, both about citations staying unambiguous. A repeated id would
        make a citation point at two different records; identical content under
        two ids would let the same passage be counted twice as independent
        support, which is how a single opinion becomes a consensus.
        """
        kept: list[EvidenceRecord] = []
        seen_ids: set[str] = set()
        seen_content: set[tuple[str, str]] = set()
        duplicate_ids = 0
        duplicate_content = 0

        for record in records:
            if record.id in seen_ids:
                duplicate_ids += 1
                continue
            fingerprint = (record.source_reference, record.content)
            if fingerprint in seen_content:
                duplicate_content += 1
                continue
            seen_ids.add(record.id)
            seen_content.add(fingerprint)
            kept.append(record)

        if duplicate_ids:
            notes.append(
                f"{duplicate_ids} record(s) repeated an evidence id already seen and were "
                "dropped; a citation to a repeated id would be ambiguous."
            )
        if duplicate_content:
            notes.append(
                f"{duplicate_content} record(s) duplicated content already retrieved from "
                "the same reference and were dropped; counting one passage twice would "
                "overstate how much independent support exists."
            )
        return tuple(kept)

    # -- skill execution ----------------------------------------------------- #

    def _attempt(
        self,
        skill: Skill[T],
        context: SkillContext,
        stages: list[RunStage],
        notes: list[str],
    ) -> T | None:
        """Run one skill. Returns ``None`` if it failed, having recorded why."""
        self._say(f"{skill.name} …")
        try:
            run = skill.run(context)
        except SkillError as exc:
            self._say(f"{skill.name} — failed")
            if exc.stages:
                stages.extend(exc.stages)
            else:  # pragma: no cover - defensive; skills always attach a stage
                stages.append(RunStage(name=skill.name, error=str(exc)))
            return None
        stages.extend(run.stages)
        notes.extend(run.warnings)
        self._say(f"{skill.name} — done")
        return run.output

    # -- 4-14. the analysis sequence ----------------------------------------- #

    def run(self, request: DecisionRequest) -> DecisionBrief:
        """Produce a decision brief. The sequence below is fixed and total."""
        started = self._now()
        self._check_request(request)

        stages: list[RunStage] = []
        notes: list[str] = []

        evidence = self._normalize(self._retrieve(request, stages, notes), notes)
        if not evidence:
            notes.append(
                "No evidence was retrieved, so no analysis was attempted. Running the "
                "skills against an empty evidence set would produce confident text with "
                "nothing behind it."
            )
            return self._assemble(request, (), _Analysis(), stages, notes, started)

        context = SkillContext(request=request, evidence=evidence)
        analysis = _Analysis()

        # 4. Which evidence bears on the decision.
        relevance = self._attempt(
            RelevanceSkill(
                self.provider, allow_retry=self.allow_retry, timeout_seconds=self.timeout_seconds
            ),
            context,
            stages,
            notes,
        )
        if relevance is not None and relevance.relevant_ids:
            keep = set(relevance.relevant_ids)
            selected = tuple(r for r in evidence if r.id in keep)
            if selected:
                if relevance.excluded:
                    notes.append(
                        f"{len(relevance.excluded)} record(s) were set aside as not bearing "
                        "on this decision and are not part of the brief: "
                        + "; ".join(f"{e.evidence_id} ({e.reason})" for e in relevance.excluded)
                    )
                evidence = selected
                context = SkillContext(request=request, evidence=evidence)

        # 5-6. Claims, and how each should be read.
        classification = self._attempt(
            ClassificationSkill(
                self.provider,
                as_of=self.as_of,
                allow_retry=self.allow_retry,
                timeout_seconds=self.timeout_seconds,
            ),
            context,
            stages,
            notes,
        )
        if classification is not None:
            analysis.claims = classification.claims
            analysis.classifications = classification.classifications

        # 7. Conflicts, surfaced and left unresolved.
        contradictions = self._attempt(
            ContradictionsSkill(
                self.provider, allow_retry=self.allow_retry, timeout_seconds=self.timeout_seconds
            ),
            context,
            stages,
            notes,
        )
        if contradictions is not None:
            analysis.contradictions = contradictions.contradictions

        # 8. What the decision needs and does not have.
        gaps = self._attempt(
            MissingEvidenceSkill(
                self.provider, allow_retry=self.allow_retry, timeout_seconds=self.timeout_seconds
            ),
            context,
            stages,
            notes,
        )
        if gaps is not None:
            analysis.missing_evidence = gaps.gaps

        # 9-12. Options, including the ones nobody asks for.
        alternatives = self._attempt(
            AlternativesSkill(
                self.provider,
                constraints=tuple(c for c in analysis.claims if c.claim_type.is_constraint),
                allow_retry=self.allow_retry,
                timeout_seconds=self.timeout_seconds,
            ),
            context,
            stages,
            notes,
        )
        if alternatives is not None:
            analysis.alternatives = alternatives.alternatives

        # 13. A recommendation, or a recommendation to validate further.
        recommendation = self._attempt(
            RecommendationSkill(
                self.provider,
                alternatives=analysis.alternatives,
                contradictions=analysis.contradictions,
                gaps=analysis.missing_evidence,
                allow_retry=self.allow_retry,
                timeout_seconds=self.timeout_seconds,
            ),
            context,
            stages,
            notes,
        )
        if recommendation is not None:
            analysis.recommendation = recommendation.recommendation

        # 14. Argue with it before a person has to.
        challenge = self._attempt(
            ChallengerSkill(
                self.provider,
                recommendation=analysis.recommendation,
                alternatives=analysis.alternatives,
                claims=analysis.claims,
                contradictions=analysis.contradictions,
                gaps=analysis.missing_evidence,
                allow_retry=self.allow_retry,
                timeout_seconds=self.timeout_seconds,
            ),
            context,
            stages,
            notes,
        )
        if challenge is not None:
            analysis.apply_challenge(challenge)

        return self._assemble(request, evidence, analysis, stages, notes, started, challenge)

    # -- 15-18. validate, then assemble -------------------------------------- #

    def _assemble(
        self,
        request: DecisionRequest,
        evidence: tuple[EvidenceRecord, ...],
        analysis: _Analysis,
        stages: list[RunStage],
        notes: list[str],
        started: datetime,
        challenge: ChallengeOutput | None = None,
    ) -> DecisionBrief:
        """Build the brief, check it, lower support if the evidence requires it."""
        ended = self._now()
        trace = RunTrace(
            run_id=f"decisionlens-{request.id}",
            request_id=request.id,
            stages=tuple(stages),
            started_at=started,
            ended_at=ended,
        )

        draft = DecisionBrief(
            id=f"DL-{request.id}",
            request=request,
            generated_at=started,
            evidence=evidence,
            classifications=analysis.classifications,
            claims=analysis.claims,
            contradictions=analysis.contradictions,
            missing_evidence=analysis.missing_evidence,
            alternatives=analysis.alternatives,
            recommendation=analysis.recommendation,
            run_trace=trace,
        )

        # 15. Resolve every citation, then run the deterministic checks.
        report = check_provenance(draft)

        # 16. The one place support is lowered.
        capped, ceiling_issues = enforce_support_ceiling(
            draft,
            report=report,
            challenger_ceiling=challenge.recommended_support if challenge else None,
        )

        extra = list(ceiling_issues)
        extra.extend(_challenge_issues(challenge))
        extra.extend(_notes_as_issues(notes))

        issues = validate(capped, report=check_provenance(capped), extra=tuple(extra))
        return capped.model_copy(update={"validation_issues": issues})


# --------------------------------------------------------------------------- #
# Analysis accumulation
# --------------------------------------------------------------------------- #


class _Analysis:
    """The results collected so far. Mutable on purpose, and never leaves this module.

    A plain container rather than a frozen model because it is filled in stage by
    stage, and a stage that failed simply leaves its field at the empty default —
    which is exactly the partial-failure behaviour the workflow requires.
    """

    def __init__(self) -> None:
        self.claims: tuple[Claim, ...] = ()
        self.classifications: tuple[EvidenceClassification, ...] = ()
        self.contradictions: tuple[Contradiction, ...] = ()
        self.missing_evidence: tuple[MissingEvidence, ...] = ()
        self.alternatives: tuple[Alternative, ...] = ()
        self.recommendation: Recommendation | None = None

    def apply_challenge(self, challenge: ChallengeOutput) -> None:
        """Apply the challenger's corrections before anything is validated.

        Order matters. A claim the challenger relabels from fact to opinion must
        be relabelled *before* the "unsupported fact" check runs, or the brief
        reports a defect the challenger already caught and fixed.

        The support level is deliberately not touched here — that goes through
        `enforce_support_ceiling` with everything else that lowers confidence.
        """
        if challenge.reclassify:
            corrections = {r.claim_id: r for r in challenge.reclassify}
            self.claims = tuple(
                claim.reclassified(corrections[claim.id].new_type, corrections[claim.id].reason)
                if claim.id in corrections
                else claim
                for claim in self.claims
            )

        if self.recommendation is None:
            return

        updates: dict[str, object] = {}
        if challenge.what_would_change_it:
            merged = self.recommendation.what_would_change_it + tuple(
                item
                for item in challenge.what_would_change_it
                if item not in self.recommendation.what_would_change_it
            )
            updates["what_would_change_it"] = merged
        if challenge.what_to_test:
            additions = tuple(
                f"Test before investing: {item}"
                for item in challenge.what_to_test
                if f"Test before investing: {item}" not in self.recommendation.conditions
            )
            updates["conditions"] = self.recommendation.conditions + additions
        if updates:
            self.recommendation = self.recommendation.model_copy(update=updates)


# --------------------------------------------------------------------------- #
# Turning findings and notes into issues
# --------------------------------------------------------------------------- #


def _challenge_issues(challenge: ChallengeOutput | None) -> list[ValidationIssue]:
    """Challenger findings surface where a reader already looks for doubts.

    `DecisionBrief` has no field for a challenge report, and adding one would put
    the challenger's output somewhere separate from every other reason to
    distrust the brief. Validation issues are that place already.
    """
    if challenge is None:
        return []

    issues: list[ValidationIssue] = []
    for finding in challenge.findings:
        if finding.verdict is ChallengeVerdict.PASSES:
            continue
        failed = finding.verdict is ChallengeVerdict.FAILS
        issues.append(
            ValidationIssue(
                code=(
                    ValidationCode.CHALLENGE_FAILED if failed else ValidationCode.CHALLENGE_CONCERN
                ).value,
                severity=ValidationSeverity.ERROR if failed else ValidationSeverity.WARNING,
                message=f"Challenge — {finding.question.value}: {finding.explanation}",
                location="recommendation",
            )
        )
    return issues


def _notes_as_issues(notes: Sequence[str]) -> list[ValidationIssue]:
    """Stage notes become warnings so they reach the reader rather than a log."""
    return [
        ValidationIssue(
            code=ValidationCode.ANALYSIS_NOTE.value,
            severity=ValidationSeverity.WARNING,
            message=note,
            location="run",
        )
        for note in notes
    ]


# --------------------------------------------------------------------------- #
# 19. The PM's decision, recorded separately
# --------------------------------------------------------------------------- #


def record_pm_decision(
    brief: DecisionBrief,
    *,
    decided_by: str,
    decision: str,
    rationale: str = "",
    agreed_with_recommendation: bool | None = None,
    override_reason: str = "",
    decided_at: datetime | None = None,
) -> PMDecision:
    """Record what the product manager actually decided.

    A separate call, not a step of `run`, and that separation is the point.
    DecisionLens recommends; a person decides. Keeping the two apart is what makes
    disagreement between them measurable instead of invisible — and disagreement
    is among the more useful signals this system can produce about its own quality.
    """
    return PMDecision(
        brief_id=brief.id,
        decided_by=decided_by,
        decided_at=decided_at or datetime.now(),
        decision=decision,
        rationale=rationale,
        agreed_with_recommendation=agreed_with_recommendation,
        override_reason=override_reason,
    )

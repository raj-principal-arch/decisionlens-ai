"""The recommendation challenger.

The stage that argues with the draft recommendation before a person has to. It
asks the eight fixed questions from the build specification and reports what is
wrong; it never rewrites the recommendation or produces a better one, because a
challenger that authors is no longer checking anything.

Three rules enforced in code rather than requested in the prompt:

*   **All eight questions must be answered, exactly once each.** A challenger that
    skips the awkward question is worse than no challenger, because silence reads
    as approval of something never examined.
*   **Confidence can only go down.** The challenger may recommend lowering the
    support level. An attempt to raise it is discarded and reported. A reviewer
    that can talk itself into more certainty has stopped being a reviewer.
*   **Two answers are arithmetic, not judgment.** Whether a non-AI option and a
    no-build option *exist* is counted from the alternatives. The model judges
    only whether they were argued seriously; if the option is absent, the verdict
    is forced to ``fails`` whatever the model said.

The challenger's findings do not get a field of their own on ``DecisionBrief``.
They surface as validation issues, which is where a reader already looks for
reasons to distrust a brief.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from decision_lens.llm import ModelProvider
from decision_lens.models import (
    Alternative,
    Citation,
    Claim,
    ClaimType,
    Contradiction,
    MissingEvidence,
    Recommendation,
    SupportLevel,
)
from decision_lens.prompts import Prompt
from decision_lens.prompts.decisionlens import CHALLENGER_V1
from decision_lens.rendering import (
    render_alternatives,
    render_claims,
    render_contradictions,
    render_evidence,
    render_gaps,
    render_recommendation,
)
from decision_lens.skills.base import SKILL_TIMEOUT_SECONDS, Skill, SkillContext
from decision_lens.validation import weaker_of


def canonical_claim_id(claim_id: str) -> str:
    """Reduce a claim id to letters and significant digits: ``C-002`` -> ``c2``.

    Used to resolve a reformatted id back to the claim it means. Real runs
    answered ``C2``, ``C4`` and ``C8`` for claims shown to them as ``C-002``,
    ``C-004`` and ``C-008``, twice, with the ids plainly in the prompt and the
    rejection naming them. An instruction that has been ignored twice is not a
    control.

    Resolution is only accepted when the canonical form matches exactly one
    claim, so this narrows a mechanical formatting difference and never guesses
    between candidates. Ambiguity is still rejected.
    """
    letters = "".join(c for c in claim_id if c.isalpha()).lower()
    digits = "".join(c for c in claim_id if c.isdigit()).lstrip("0")
    return f"{letters}{digits}"


def _resolve(claim_id: str, claims: Sequence[Claim]) -> str | None:
    """The real id this one means, or ``None`` if that is not unambiguous."""
    if any(c.id == claim_id for c in claims):
        return claim_id
    wanted = canonical_claim_id(claim_id)
    matches = {c.id for c in claims if canonical_claim_id(c.id) == wanted}
    return matches.pop() if len(matches) == 1 else None


class ChallengeQuestion(StrEnum):
    """The eight questions, fixed by the build specification.

    An enum rather than free text so "did the challenger answer all of them" is a
    set comparison instead of a judgment call.
    """

    CLAIMS_SUPPORTED = "claims_supported"
    CONTRADICTIONS_CONSIDERED = "contradictions_considered"
    PREFERENCE_AS_EVIDENCE = "preference_as_evidence"
    NON_AI_CONSIDERED = "non_ai_considered"
    NO_BUILD_CONSIDERED = "no_build_considered"
    OVERCONFIDENT = "overconfident"
    WHAT_COULD_MAKE_IT_WRONG = "what_could_make_it_wrong"
    WHAT_TO_TEST = "what_to_test"


class ChallengeVerdict(StrEnum):
    PASSES = "passes"  # looked, found nothing wrong
    CONCERN = "concern"  # a real problem the reader should know about
    FAILS = "fails"  # the recommendation should not stand as written


class ChallengeFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    question: ChallengeQuestion
    verdict: ChallengeVerdict
    explanation: str = Field(min_length=1)
    citations: tuple[Citation, ...] = ()


class ClaimReclassification(BaseModel):
    """A claim the challenger says is mislabelled.

    The single most useful thing this stage produces: a stakeholder's preference
    carried through the workflow as a fact will otherwise reach a decision wearing
    the authority of evidence.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    claim_id: str = Field(min_length=1)
    new_type: ClaimType
    reason: str = Field(min_length=1)


class ChallengeOutput(BaseModel):
    """What the challenger found, and what it wants changed."""

    model_config = ConfigDict(extra="ignore")

    findings: tuple[ChallengeFinding, ...] = ()
    reclassify: tuple[ClaimReclassification, ...] = ()
    #: Lower than the draft's level, or absent. Never higher — see `refine`.
    recommended_support: SupportLevel | None = None
    what_would_change_it: tuple[str, ...] = ()
    what_to_test: tuple[str, ...] = ()

    def by_question(self) -> dict[ChallengeQuestion, ChallengeFinding]:
        return {f.question: f for f in self.findings}

    def verdict_for(self, question: ChallengeQuestion) -> ChallengeVerdict | None:
        found = self.by_question().get(question)
        return None if found is None else found.verdict

    @property
    def failing(self) -> tuple[ChallengeFinding, ...]:
        return tuple(f for f in self.findings if f.verdict is ChallengeVerdict.FAILS)

    @property
    def concerns(self) -> tuple[ChallengeFinding, ...]:
        return tuple(f for f in self.findings if f.verdict is ChallengeVerdict.CONCERN)


class ChallengerSkill(Skill[ChallengeOutput]):
    """Attacks a draft recommendation.

    Args:
        provider: Any `ModelProvider`.
        recommendation: The draft under review. ``None`` is accepted so a run
            whose recommendation stage failed can still be challenged on its
            alternatives and claims rather than skipping the stage silently.
        alternatives: Used to compute whether non-AI and no-build options exist.
        claims: Reclassification targets must be among these.
    """

    def __init__(
        self,
        provider: ModelProvider,
        *,
        recommendation: Recommendation | None = None,
        alternatives: Sequence[Alternative] = (),
        claims: Sequence[Claim] = (),
        contradictions: Sequence[Contradiction] = (),
        gaps: Sequence[MissingEvidence] = (),
        allow_retry: bool = True,
        timeout_seconds: float = SKILL_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(provider, allow_retry=allow_retry, timeout_seconds=timeout_seconds)
        self.recommendation = recommendation
        self.alternatives = tuple(alternatives)
        self.claims = tuple(claims)
        self.contradictions = tuple(contradictions)
        self.gaps = tuple(gaps)

    @property
    def name(self) -> str:
        return "challenger"

    @property
    def prompt(self) -> Prompt:
        return CHALLENGER_V1

    @property
    def output_model(self) -> type[ChallengeOutput]:
        return ChallengeOutput

    def render_values(self, context: SkillContext) -> dict[str, str]:
        return {
            "question": context.request.question,
            "desired_outcome": context.request.desired_outcome or "(not stated)",
            "recommendation": render_recommendation(self.recommendation),
            "alternatives": render_alternatives(self.alternatives),
            "claims": render_claims(self.claims),
            "contradictions": render_contradictions(self.contradictions),
            "gaps": render_gaps(self.gaps),
            "evidence": render_evidence(context.evidence),
            "schema": json.dumps(ChallengeOutput.model_json_schema(), separators=(",", ":")),
        }

    # -- deterministic requirements ----------------------------------------- #

    def violations(self, output: ChallengeOutput, context: SkillContext) -> tuple[str, ...]:
        problems: list[str] = []

        answered = [f.question for f in output.findings]
        missing = [q for q in ChallengeQuestion if q not in set(answered)]
        if missing:
            problems.append(
                "These questions were not answered: "
                f"{', '.join(q.value for q in missing)}. Answer all eight; skipping one "
                "certifies something you did not examine."
            )
        duplicated = sorted({q.value for q in answered if answered.count(q) > 1})
        if duplicated:
            problems.append(
                f"These questions were answered more than once: {', '.join(duplicated)}. "
                "Give exactly one verdict per question."
            )

        for finding in output.findings:
            bad = context.unresolvable(finding.citations)
            if bad:
                quotes = "; ".join(f"{c.evidence_id}: {c.quote[:60]!r}" for c in bad)
                problems.append(
                    f"The {finding.question.value} finding cites text not in the "
                    f"evidence ({quotes})"
                )

        unresolvable = sorted(
            {r.claim_id for r in output.reclassify if _resolve(r.claim_id, self.claims) is None}
        )
        if unresolvable:
            known = ", ".join(c.id for c in self.claims[:5]) or "none were supplied"
            problems.append(
                f"These claim ids match no claim: {', '.join(unresolvable)}. Use the ids "
                f"exactly as given (they look like: {known})."
            )

        if output.failing and not output.what_would_change_it:
            problems.append(
                "A finding failed, but nothing is listed under what_would_change_it. "
                "Saying a recommendation should not stand without saying what would fix "
                "it leaves the reader stuck."
            )

        return tuple(problems)

    # -- computed corrections ------------------------------------------------ #

    def refine(
        self, output: ChallengeOutput, context: SkillContext
    ) -> tuple[ChallengeOutput, tuple[str, ...]]:
        """Override the two arithmetic answers, and refuse any raise in confidence."""
        findings = list(output.findings)
        warnings: list[str] = []

        # Rewrite reformatted claim ids to the ones that actually exist. Only
        # ever an unambiguous match — `violations` has already rejected anything
        # that resolves to zero claims or to more than one.
        reclassify = []
        for item in output.reclassify:
            resolved = _resolve(item.claim_id, self.claims)
            if resolved is not None and resolved != item.claim_id:
                warnings.append(
                    f"Claim id {item.claim_id!r} was read as {resolved!r}, the only claim it "
                    "could mean."
                )
                item = item.model_copy(update={"claim_id": resolved})
            reclassify.append(item)

        existence = (
            (
                ChallengeQuestion.NON_AI_CONSIDERED,
                any(not a.kind.is_ai for a in self.alternatives),
                "No non-AI option was generated at all, so it cannot have been considered "
                "seriously.",
            ),
            (
                ChallengeQuestion.NO_BUILD_CONSIDERED,
                any(a.kind.is_no_build for a in self.alternatives),
                "No no-change, defer, or further-research option was generated at all, so "
                "it cannot have been considered seriously.",
            ),
        )

        for question, exists, reason in existence:
            if exists:
                continue
            index = next((i for i, f in enumerate(findings) if f.question is question), None)
            if index is None:
                continue
            if findings[index].verdict is not ChallengeVerdict.FAILS:
                warnings.append(f"{question.value}: verdict overridden to fails. {reason}")
            findings[index] = findings[index].model_copy(
                update={
                    "verdict": ChallengeVerdict.FAILS,
                    "explanation": f"{reason} (Counted from the alternatives, not judged.) "
                    f"The reviewer wrote: {findings[index].explanation}",
                }
            )

        recommended = output.recommended_support
        if recommended is not None and self.recommendation is not None:
            allowed = weaker_of(recommended, self.recommendation.support_level)
            if allowed is not recommended:
                warnings.append(
                    f"The challenger asked to raise support from "
                    f"{self.recommendation.support_level.value} to {recommended.value}. "
                    "Discarded: a challenger may lower confidence, never raise it."
                )
                recommended = None

        return (
            output.model_copy(
                update={
                    "findings": tuple(findings),
                    "reclassify": tuple(reclassify),
                    "recommended_support": recommended,
                }
            ),
            tuple(warnings),
        )

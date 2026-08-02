"""Recommendation analysis.

Chooses among the alternatives and says how firmly, with what it rests on and
what would change it. It recommends; it does not approve. The product manager
owns the decision, and nothing in this skill records one.

Deterministic parts:

*   **Strong support requires grounded claims.** If any claim behind the
    recommendation cites text that is not in the evidence, the support level is
    capped. A confident recommendation resting on an unverifiable quote is the
    exact failure mode this product exists to catch, and catching it is
    arithmetic, not judgment.
*   **The chosen option must exist.** A recommendation naming an alternative that
    was never generated cannot be acted on.
*   **`what_would_change_it` is required at strong support.** A support level a
    reader cannot act on is decoration.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from decision_lens.llm import ModelProvider
from decision_lens.models import (
    Alternative,
    Contradiction,
    MissingEvidence,
    Recommendation,
    SupportLevel,
)
from decision_lens.prompts import Prompt
from decision_lens.prompts.decisionlens import RECOMMENDATION_V1
from decision_lens.rendering import (
    render_alternatives,
    render_contradictions,
    render_evidence,
    render_gaps,
)
from decision_lens.skills.base import SKILL_TIMEOUT_SECONDS, Skill, SkillContext


class RecommendationOutput(BaseModel):
    """The recommended option and the conditions on it."""

    model_config = ConfigDict(extra="ignore")

    recommendation: Recommendation


class RecommendationSkill(Skill[RecommendationOutput]):
    def __init__(
        self,
        provider: ModelProvider,
        *,
        alternatives: Sequence[Alternative] = (),
        contradictions: Sequence[Contradiction] = (),
        gaps: Sequence[MissingEvidence] = (),
        allow_retry: bool = True,
        timeout_seconds: float = SKILL_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(provider, allow_retry=allow_retry, timeout_seconds=timeout_seconds)
        self.alternatives = tuple(alternatives)
        self.contradictions = tuple(contradictions)
        self.gaps = tuple(gaps)

    @property
    def name(self) -> str:
        return "recommendation"

    @property
    def prompt(self) -> Prompt:
        return RECOMMENDATION_V1

    @property
    def output_model(self) -> type[RecommendationOutput]:
        return RecommendationOutput

    def render_values(self, context: SkillContext) -> dict[str, str]:
        return {
            "question": context.request.question,
            "desired_outcome": context.request.desired_outcome or "(not stated)",
            "alternatives": render_alternatives(self.alternatives),
            "contradictions": render_contradictions(self.contradictions),
            "gaps": render_gaps(self.gaps),
            "evidence": render_evidence(context.evidence),
            "schema": json.dumps(RecommendationOutput.model_json_schema(), separators=(",", ":")),
        }

    def violations(self, output: RecommendationOutput, context: SkillContext) -> tuple[str, ...]:
        rec = output.recommendation
        problems: list[str] = []

        known = {a.id for a in self.alternatives}
        if (
            self.alternatives
            and rec.selected_alternative_id
            and rec.selected_alternative_id not in known
        ):
            problems.append(
                f"The recommendation selects {rec.selected_alternative_id!r}, which is not "
                f"one of the alternatives ({', '.join(sorted(known))})."
            )

        for claim in rec.claims:
            bad = context.unresolvable(claim.citations)
            if bad:
                quotes = "; ".join(f"{c.evidence_id}: {c.quote[:60]!r}" for c in bad)
                problems.append(f"Claim {claim.id!r} cites text not in the evidence ({quotes})")

        if rec.support_level is SupportLevel.STRONG and not rec.what_would_change_it:
            problems.append(
                "Strong support must state what would change it. A support level a reader "
                "cannot act on is decoration."
            )

        return tuple(problems)

    def refine(
        self, output: RecommendationOutput, context: SkillContext
    ) -> tuple[RecommendationOutput, tuple[str, ...]]:
        """Cap support when the recommendation rests on ungrounded claims.

        Computed, not judged: a claim with no citation, or one whose quote does
        not appear in the evidence, cannot support a strong recommendation. The
        model is not asked to police itself here because the check is exact.
        """
        rec = output.recommendation
        if rec.support_level is not SupportLevel.STRONG:
            return output, ()

        ungrounded = [
            c for c in rec.claims if not c.is_grounded or context.unresolvable(c.citations)
        ]
        if not ungrounded:
            return output, ()

        capped = rec.model_copy(
            update={
                "support_level": SupportLevel.MODERATE,
                "support_basis": (
                    f"{rec.support_basis} "
                    f"[Support reduced from strong: {len(ungrounded)} supporting claim(s) "
                    "are ungrounded or cite text absent from the evidence.]"
                ).strip(),
            }
        )
        return output.model_copy(update={"recommendation": capped}), (
            f"Support reduced from strong to moderate: {len(ungrounded)} claim(s) unverifiable.",
        )

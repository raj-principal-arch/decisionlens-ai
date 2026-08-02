"""Alternative generation.

Produces the options a product manager could actually choose. This skill carries
the two rules the whole product is judged on, and they are enforced in code
rather than requested in a prompt:

*   At least one option that does not involve AI.
*   At least one no-change, defer, or further-research option.

An instruction can be ignored; a check cannot. A tool built to help PMs adopt AI
that reflexively recommends AI is a sales instrument, and PMs will correctly stop
trusting it — so the guard against that is a test, not a sentence.

When the model breaks either rule, the skill re-prompts once naming the broken
rule and then fails. It never inserts the missing option itself: DecisionLens
authoring an alternative and presenting it as analysis is the fabrication this
product exists to prevent.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from decision_lens.llm import ModelProvider
from decision_lens.models import Alternative, AssessmentState, Claim
from decision_lens.prompts import Prompt
from decision_lens.prompts.decisionlens import ALTERNATIVES_V1
from decision_lens.rendering import (
    render_constraints,
    render_criteria,
    render_evidence,
)
from decision_lens.skills.base import SKILL_TIMEOUT_SECONDS, Skill, SkillContext


class AlternativesOutput(BaseModel):
    """Credible options, including the ones nobody wants to hear."""

    model_config = ConfigDict(extra="ignore")

    alternatives: tuple[Alternative, ...] = ()

    @property
    def has_non_ai(self) -> bool:
        return any(not a.kind.is_ai for a in self.alternatives)

    @property
    def has_no_build(self) -> bool:
        return any(a.kind.is_no_build for a in self.alternatives)


class AlternativesSkill(Skill[AlternativesOutput]):
    def __init__(
        self,
        provider: ModelProvider,
        *,
        constraints: tuple[Claim, ...] = (),
        allow_retry: bool = True,
        timeout_seconds: float = SKILL_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(provider, allow_retry=allow_retry, timeout_seconds=timeout_seconds)
        self.constraints = constraints

    @property
    def name(self) -> str:
        return "alternatives"

    @property
    def prompt(self) -> Prompt:
        return ALTERNATIVES_V1

    @property
    def output_model(self) -> type[AlternativesOutput]:
        return AlternativesOutput

    def render_values(self, context: SkillContext) -> dict[str, str]:
        return {
            "question": context.request.question,
            "desired_outcome": context.request.desired_outcome or "(not stated)",
            "criteria": render_criteria(context.request),
            "constraints": render_constraints(self.constraints),
            "evidence": render_evidence(context.evidence),
            "schema": json.dumps(AlternativesOutput.model_json_schema(), separators=(",", ":")),
        }

    def violations(self, output: AlternativesOutput, context: SkillContext) -> tuple[str, ...]:
        problems: list[str] = []

        if not output.alternatives:
            problems.append("No alternatives were generated.")
        if output.alternatives and not output.has_non_ai:
            problems.append(
                "Every option involves AI. At least one option must not: process change, "
                "training, documentation, data quality, UX change, rules-based automation, "
                "buy, partner, no change, defer, or further research."
            )
        if output.alternatives and not output.has_no_build:
            problems.append(
                "There is no no-change, defer, or further-research option. One is required, "
                "and it is often the right answer."
            )

        for alt in output.alternatives:
            bad = context.unresolvable(alt.supporting + alt.opposing)
            if bad:
                quotes = "; ".join(f"{c.evidence_id}: {c.quote[:60]!r}" for c in bad)
                problems.append(f"Alternative {alt.id!r} cites text not in the evidence ({quotes})")
            for assessment in alt.assessments:
                unresolved = context.unresolvable(assessment.citations)
                if unresolved:
                    problems.append(
                        f"Alternative {alt.id!r} dimension {assessment.dimension.value} cites "
                        "text not in the evidence"
                    )

        ids = [a.id for a in output.alternatives]
        if len(set(ids)) != len(ids):
            problems.append("Alternative ids must be unique; the recommendation refers to them.")

        return tuple(problems)

    def refine(
        self, output: AlternativesOutput, context: SkillContext
    ) -> tuple[AlternativesOutput, tuple[str, ...]]:
        """Report, but do not correct, how much of the comparison is unassessable."""
        unassessed = sum(
            1
            for alt in output.alternatives
            for a in alt.assessments
            if a.state is AssessmentState.CANNOT_ASSESS
        )
        assessed = sum(len(alt.assessments) for alt in output.alternatives)
        if not assessed or not unassessed:
            return output, ()
        return output, (
            f"{unassessed} of {assessed} dimension assessments could not be made from the "
            "available evidence.",
        )

"""Contradiction detection.

Surfaces conflicting evidence and refuses to resolve it. Silently discarding one
side of a disagreement is the failure this product exists to prevent, so the
skill reports both sides with citations and says what would settle it.

Deterministic parts:

*   **Both sides must resolve.** A contradiction anchored on a quote that does not
    exist is worse than no contradiction: it sends a reader to check something
    that was never there.
    Note what is deliberately *not* checked: the two sides may come from the same
    record. A document that says one thing in one section and the opposite in
    another is genuinely self-contradictory, and a rule rejecting that would
    discard real findings. Identical sides are already refused by the model.
*   **Resolution guidance is required.** Reporting that two sources disagree is
    less useful than reporting that one of them is quoting a stale figure.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from decision_lens.models import Contradiction
from decision_lens.prompts import Prompt
from decision_lens.prompts.decisionlens import CONTRADICTIONS_V1
from decision_lens.rendering import render_evidence
from decision_lens.skills.base import Skill, SkillContext


class ContradictionsOutput(BaseModel):
    """Conflicts found in the evidence, presented unresolved."""

    model_config = ConfigDict(extra="ignore")

    contradictions: tuple[Contradiction, ...] = ()


class ContradictionsSkill(Skill[ContradictionsOutput]):
    @property
    def name(self) -> str:
        return "contradictions"

    @property
    def prompt(self) -> Prompt:
        return CONTRADICTIONS_V1

    @property
    def output_model(self) -> type[ContradictionsOutput]:
        return ContradictionsOutput

    def render_values(self, context: SkillContext) -> dict[str, str]:
        return {
            "question": context.request.question,
            "evidence": render_evidence(context.evidence),
            "schema": json.dumps(ContradictionsOutput.model_json_schema(), separators=(",", ":")),
        }

    def violations(self, output: ContradictionsOutput, context: SkillContext) -> tuple[str, ...]:
        problems: list[str] = []
        for found in output.contradictions:
            bad = context.unresolvable((found.side_a, found.side_b))
            if bad:
                quotes = "; ".join(f"{c.evidence_id}: {c.quote[:60]!r}" for c in bad)
                problems.append(
                    f"Contradiction {found.id!r} cites text that is not in the evidence ({quotes})"
                )
            if not found.how_to_resolve.strip():
                problems.append(
                    f"Contradiction {found.id!r} does not say how to resolve it. Reporting a "
                    "disagreement without saying what would settle it leaves the reader "
                    "no better off."
                )
        return tuple(problems)

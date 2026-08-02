"""Missing-evidence detection.

Names the evidence the decision needs and does not have. This is the skill that
keeps an unevidenced option in the conversation on honest terms: a method that
reads absence of evidence as evidence of low value systematically defunds
anything new, because a bet has no track record by definition.

Deterministic parts:

*   **A gap must not cite evidence as proof of itself.** A gap is a claim about
    absence; anchoring it to a quote is a category error and usually means the
    model has reported something it *found* rather than something missing.
*   **Unpopulated fields are detected in code.** A metric row present in the data
    with no value is a gap a scan can find with certainty, so it is found by a
    scan and merged in rather than left to chance. Blank is not zero.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict

from decision_lens.models import GapImpact, MissingEvidence
from decision_lens.prompts import Prompt
from decision_lens.prompts.decisionlens import MISSING_EVIDENCE_V1
from decision_lens.rendering import render_evidence
from decision_lens.skills.base import Skill, SkillContext

#: A CSV row rendered by the connector drops blank values, so a metric name with
#: no accompanying value line is a field that exists and was never populated.
_METRIC_LINE = re.compile(r"^metric:\s*(?P<name>.+)$", re.MULTILINE)
_VALUE_LINE = re.compile(r"^value:\s*\S", re.MULTILINE)


class MissingEvidenceOutput(BaseModel):
    """Gaps between what the decision needs and what the evidence contains."""

    model_config = ConfigDict(extra="ignore")

    gaps: tuple[MissingEvidence, ...] = ()


class MissingEvidenceSkill(Skill[MissingEvidenceOutput]):
    @property
    def name(self) -> str:
        return "missing_evidence"

    @property
    def prompt(self) -> Prompt:
        return MISSING_EVIDENCE_V1

    @property
    def output_model(self) -> type[MissingEvidenceOutput]:
        return MissingEvidenceOutput

    def render_values(self, context: SkillContext) -> dict[str, str]:
        return {
            "question": context.request.question,
            "desired_outcome": context.request.desired_outcome or "(not stated)",
            "evidence": render_evidence(context.evidence),
            "schema": json.dumps(MissingEvidenceOutput.model_json_schema(), separators=(",", ":")),
        }

    def violations(self, output: MissingEvidenceOutput, context: SkillContext) -> tuple[str, ...]:
        problems: list[str] = []
        if not output.gaps:
            problems.append(
                "No gaps were identified. Every real decision has something it cannot see; "
                "if nothing is missing, say what you checked for and found."
            )
        for gap in output.gaps:
            if not gap.why_it_matters.strip():
                problems.append(f"Gap {gap.id!r} does not say why it matters to this decision.")
        return tuple(problems)

    def refine(
        self, output: MissingEvidenceOutput, context: SkillContext
    ) -> tuple[MissingEvidenceOutput, tuple[str, ...]]:
        """Add unpopulated metrics found by scanning, if the model missed them."""
        already = {g.question.lower() for g in output.gaps}
        found: list[MissingEvidence] = []

        for record in context.evidence:
            match = _METRIC_LINE.search(record.content)
            if match is None or _VALUE_LINE.search(record.content):
                continue
            metric = match.group("name").strip()
            question = f"What is the value of {metric}?"
            if any(metric.lower() in seen for seen in already):
                continue
            found.append(
                MissingEvidence(
                    id=f"MG-AUTO-{record.id}",
                    question=question,
                    impact=GapImpact.WOULD_REFINE_SCOPE,
                    why_it_matters=(
                        f"The metric {metric!r} exists in the data but was never populated. "
                        "A blank is not a zero, and treating it as one would understate "
                        "whatever it measures."
                    ),
                    how_to_obtain=f"Populate {metric} in the source system.",
                    was_searched=True,
                )
            )

        if not found:
            return output, ()
        warnings = (f"{len(found)} unpopulated metric field(s) were found by scanning and added.",)
        return output.model_copy(update={"gaps": output.gaps + tuple(found)}), warnings

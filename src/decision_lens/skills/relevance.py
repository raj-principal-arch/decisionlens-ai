"""Relevance selection.

Decides which evidence bears on the decision. Deliberately generous: an excluded
record is invisible to every later stage, so a wrong exclusion is silent and
permanent, while a wrong inclusion is merely noise a later skill can ignore.

Deterministic parts:

*   Every selected or excluded id must be a real record. A model that invents an
    id has not selected anything, and the violation is caught rather than
    trusted.
*   Anything the model failed to mention is **kept**, not dropped. Silence is not
    an exclusion decision, and defaulting the other way would let an incomplete
    answer quietly shrink the evidence base.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from decision_lens.prompts import Prompt
from decision_lens.prompts.decisionlens import RELEVANCE_V1
from decision_lens.rendering import render_evidence
from decision_lens.skills.base import Skill, SkillContext


class ExcludedRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class RelevanceOutput(BaseModel):
    """Which records bear on the decision, and what was set aside."""

    model_config = ConfigDict(extra="ignore")

    relevant_ids: tuple[str, ...] = ()
    excluded: tuple[ExcludedRecord, ...] = ()


class RelevanceSkill(Skill[RelevanceOutput]):
    @property
    def name(self) -> str:
        return "relevance"

    @property
    def prompt(self) -> Prompt:
        return RELEVANCE_V1

    @property
    def output_model(self) -> type[RelevanceOutput]:
        return RelevanceOutput

    def render_values(self, context: SkillContext) -> dict[str, str]:
        return {
            "question": context.request.question,
            "desired_outcome": context.request.desired_outcome or "(not stated)",
            "evidence": render_evidence(context.evidence),
            "schema": json.dumps(RelevanceOutput.model_json_schema(), separators=(",", ":")),
        }

    def violations(self, output: RelevanceOutput, context: SkillContext) -> tuple[str, ...]:
        known = set(context.by_id())
        invented = [i for i in output.relevant_ids if i not in known]
        invented += [e.evidence_id for e in output.excluded if e.evidence_id not in known]
        if invented:
            return (
                f"These evidence ids do not exist: {', '.join(sorted(set(invented)))}. "
                "Use only ids from the evidence list.",
            )
        return ()

    def refine(
        self, output: RelevanceOutput, context: SkillContext
    ) -> tuple[RelevanceOutput, tuple[str, ...]]:
        """Keep anything the model did not explicitly decide about.

        Silence is not an exclusion. Treating an unmentioned record as excluded
        would let an incomplete answer shrink the evidence base without anyone
        seeing it happen.
        """
        excluded_ids = {e.evidence_id for e in output.excluded}
        selected = tuple(r.id for r in context.evidence if r.id not in excluded_ids)
        unmentioned = [
            r.id for r in context.evidence if r.id not in set(output.relevant_ids) | excluded_ids
        ]
        warnings = (
            (
                f"{len(unmentioned)} record(s) were neither selected nor excluded and have "
                "been kept.",
            )
            if unmentioned
            else ()
        )
        return output.model_copy(update={"relevant_ids": selected}), warnings

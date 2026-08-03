"""Evidence classification.

Extracts statements from evidence and labels how each should be read: fact,
assumption, stakeholder opinion, or one of the three constraint kinds.

Deterministic parts:

*   **Every citation must resolve.** A claim quoting text that does not appear in
    the record it names is rejected, and the model is told which one failed.
    Without this the classification is fluent and unverifiable, which is exactly
    the state this product exists to fix.
*   **Staleness is calculated, never judged.** Age comes from the record dates and
    the case date. The prompt explicitly tells the model not to guess at it,
    because a model estimating "about a year old" is inventing a number that a
    subtraction already answers.
"""

from __future__ import annotations

import json
from datetime import date

from pydantic import BaseModel, ConfigDict

from decision_lens.llm import ModelProvider
from decision_lens.models import (
    Claim,
    EvidenceClassification,
    EvidenceType,
    SupportLevel,
)
from decision_lens.prompts import Prompt
from decision_lens.prompts.decisionlens import CLASSIFICATION_V2
from decision_lens.rendering import render_evidence
from decision_lens.skills.base import SKILL_TIMEOUT_SECONDS, Skill, SkillContext

#: A source older than this is flagged stale. A year covers a full planning cycle,
#: so anything beyond it predates the current set of assumptions.
STALE_AFTER_DAYS = 365

#: Evidence types that are weak by their nature, whatever they say. An opinion is
#: not made stronger by being recent, and a vendor benchmark is not evidence about
#: this organisation.
_INHERENTLY_WEAK = frozenset({EvidenceType.STAKEHOLDER_INPUT})


def _support_from_record(evidence_type: EvidenceType, is_stale: bool) -> SupportLevel:
    """How much weight a record can bear, from the record itself.

    Deliberately never returns STRONG. Whether a specific passage strongly
    supports a specific claim is judgment about content, and a rule that awarded
    it from metadata alone would be inventing confidence.

    Note what is NOT considered: whether any claim happened to cite the record.
    An uncited record is unused, not weak, and conflating the two would
    systematically mislabel evidence the analysis simply did not reach for.
    Uncited evidence is reported separately, by DecisionBrief.uncited_evidence().
    """
    if is_stale or evidence_type in _INHERENTLY_WEAK:
        return SupportLevel.LOW
    return SupportLevel.MODERATE


def _rationale(evidence_type: EvidenceType, is_stale: bool, age: int | None, as_of: date) -> str:
    reasons: list[str] = []
    if is_stale:
        reasons.append(f"{age} days old at {as_of.isoformat()}")
    if evidence_type in _INHERENTLY_WEAK:
        reasons.append(f"{evidence_type.value} records report belief, not measurement")
    return "; ".join(reasons)


class ClassificationOutput(BaseModel):
    """Claims extracted from the evidence, each labelled with how to read it."""

    model_config = ConfigDict(extra="ignore")

    claims: tuple[Claim, ...] = ()
    #: Filled in deterministically by `refine`, not by the model.
    classifications: tuple[EvidenceClassification, ...] = ()


class ClassificationSkill(Skill[ClassificationOutput]):
    def __init__(
        self,
        provider: ModelProvider,
        *,
        as_of: date | None = None,
        allow_retry: bool = True,
        timeout_seconds: float = SKILL_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(provider, allow_retry=allow_retry, timeout_seconds=timeout_seconds)
        self.as_of = as_of or date.today()

    @property
    def name(self) -> str:
        return "classification"

    @property
    def prompt(self) -> Prompt:
        return CLASSIFICATION_V2

    @property
    def output_model(self) -> type[ClassificationOutput]:
        return ClassificationOutput

    def render_values(self, context: SkillContext) -> dict[str, str]:
        return {
            "question": context.request.question,
            "evidence": render_evidence(context.evidence),
            "schema": json.dumps(ClassificationOutput.model_json_schema(), separators=(",", ":")),
        }

    def violations(self, output: ClassificationOutput, context: SkillContext) -> tuple[str, ...]:
        problems: list[str] = []
        for claim in output.claims:
            bad = context.unresolvable(claim.citations)
            if bad:
                quotes = "; ".join(f"{c.evidence_id}: {c.quote[:60]!r}" for c in bad)
                problems.append(
                    f"Claim {claim.id!r} cites text that is not in the evidence ({quotes})"
                )
        if not output.claims:
            problems.append("No claims were extracted. The evidence is not empty.")
        return tuple(problems)

    def refine(
        self, output: ClassificationOutput, context: SkillContext
    ) -> tuple[ClassificationOutput, tuple[str, ...]]:
        """Compute per-record classification from the record itself.

        Evidence type comes from the record's own metadata, and age from its
        dates. Neither is a judgment, so neither is asked of the model.
        """
        classifications: list[EvidenceClassification] = []
        stale_count = 0

        for record in context.evidence:
            age = record.age_days(self.as_of)
            is_stale = age is not None and age >= STALE_AFTER_DAYS
            stale_count += int(is_stale)
            classifications.append(
                EvidenceClassification(
                    evidence_id=record.id,
                    evidence_type=record.evidence_type,
                    support_level=_support_from_record(record.evidence_type, is_stale),
                    rationale=_rationale(record.evidence_type, is_stale, age, self.as_of),
                    is_stale=is_stale,
                    age_days=age,
                )
            )

        warnings = (
            (f"{stale_count} source(s) are at least {STALE_AFTER_DAYS} days old.",)
            if stale_count
            else ()
        )
        return output.model_copy(update={"classifications": tuple(classifications)}), warnings

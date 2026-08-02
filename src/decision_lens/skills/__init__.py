"""Analysis skills interpret evidence. They do not retrieve it.

Each skill takes evidence that has already been retrieved and returns one kind of
structured judgment. Skills never reach a data source, and they never call each
other — the orchestrator sequences them. That constraint keeps every step
separately runnable and separately testable, which is what makes the reasoning
auditable rather than merely fluent.

The six skills map one-to-one onto the mechanisms the product hypothesis names:

    relevance.py         which evidence bears on the decision
    classification.py    fact, assumption, opinion, or constraint
    contradictions.py    conflicts surfaced, never resolved
    missing_evidence.py  what the decision needs and does not have
    alternatives.py      options, including non-AI and no-build
    recommendation.py    a recommendation, never an approval

A seventh, `challenger.py`, is not an analysis of the evidence but of the draft
recommendation, so it runs last and only after one exists.

Every skill is hybrid: it computes what is computable and asks the model only for
judgment. Staleness is date arithmetic, citation resolution is string matching,
and the mandatory non-AI and no-build options are enum checks. An instruction can
be ignored; a check cannot.
"""

from decision_lens.skills.alternatives import AlternativesOutput, AlternativesSkill
from decision_lens.skills.base import (
    SKILL_TIMEOUT_SECONDS,
    Skill,
    SkillContext,
    SkillError,
    SkillRun,
    SkillViolation,
)
from decision_lens.skills.challenger import (
    ChallengeFinding,
    ChallengeOutput,
    ChallengeQuestion,
    ChallengerSkill,
    ChallengeVerdict,
    ClaimReclassification,
)
from decision_lens.skills.classification import ClassificationOutput, ClassificationSkill
from decision_lens.skills.contradictions import ContradictionsOutput, ContradictionsSkill
from decision_lens.skills.missing_evidence import (
    MissingEvidenceOutput,
    MissingEvidenceSkill,
)
from decision_lens.skills.recommendation import RecommendationOutput, RecommendationSkill
from decision_lens.skills.relevance import RelevanceOutput, RelevanceSkill

#: The approved set. Nothing else is a skill.
SKILL_NAMES = (
    "relevance",
    "classification",
    "contradictions",
    "missing_evidence",
    "alternatives",
    "recommendation",
    "challenger",
)

__all__ = [
    "SKILL_NAMES",
    "SKILL_TIMEOUT_SECONDS",
    "AlternativesOutput",
    "AlternativesSkill",
    "ChallengeFinding",
    "ChallengeOutput",
    "ChallengeQuestion",
    "ChallengeVerdict",
    "ChallengerSkill",
    "ClaimReclassification",
    "ClassificationOutput",
    "ClassificationSkill",
    "ContradictionsOutput",
    "ContradictionsSkill",
    "MissingEvidenceOutput",
    "MissingEvidenceSkill",
    "RecommendationOutput",
    "RecommendationSkill",
    "RelevanceOutput",
    "RelevanceSkill",
    "Skill",
    "SkillContext",
    "SkillError",
    "SkillRun",
    "SkillViolation",
]

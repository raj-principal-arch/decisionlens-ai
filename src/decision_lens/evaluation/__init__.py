"""Evaluation: ground truth, case checking, metrics, and the harness.

Kept apart from the product code on purpose. Nothing the agent does at runtime
may read a ground-truth file — a system that can see the answer key is not being
measured, it is being flattered.
"""

from __future__ import annotations

from decision_lens.evaluation.ground_truth import (
    CredibleAlternative,
    EvidenceHazard,
    ExpectedContradiction,
    ExpectedGap,
    ForbiddenClaim,
    GroundTruth,
    KnownAssumption,
    KnownConstraint,
    KnownFact,
    KnownOpinion,
    Sourced,
)

__all__ = [
    "CredibleAlternative",
    "EvidenceHazard",
    "ExpectedContradiction",
    "ExpectedGap",
    "ForbiddenClaim",
    "GroundTruth",
    "KnownAssumption",
    "KnownConstraint",
    "KnownFact",
    "KnownOpinion",
    "Sourced",
]

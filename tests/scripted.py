"""A tiny, self-contained case and a cache that answers it.

Not a test module — a builder used by the CLI, report and interface tests.

Deliberately small rather than the bundled 56-record corpus. Those tests are
about wiring: does the command load a case, produce a brief, write the files,
pick the right exit code. Driving them through the full corpus would make them
slow, couple them to evidence that exists to exercise the analysis skills, and
turn an unrelated corpus edit into a broken CLI test.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from decision_lens.llm import CachedResponse, DemoCache
from decision_lens.models import (
    Alternative,
    AssessmentState,
    Citation,
    Claim,
    ClaimType,
    Contradiction,
    ContradictionKind,
    Dimension,
    DimensionAssessment,
    ExperimentPlan,
    GapImpact,
    Metric,
    MetricRole,
    MissingEvidence,
    OptionKind,
    Recommendation,
    SupportLevel,
    Tradeoff,
)
from decision_lens.skills import (
    AlternativesOutput,
    ChallengeFinding,
    ChallengeOutput,
    ChallengeQuestion,
    ChallengeVerdict,
    ClassificationOutput,
    ContradictionsOutput,
    MissingEvidenceOutput,
    RecommendationOutput,
    RelevanceOutput,
)

CASE_ID = "tiny_case"
QUESTION = "Which intervention should the team prioritize to reduce delivery exceptions?"
OUTCOME = "Improve first-attempt delivery success."

FACT = "Address errors account for 40% of delivery exceptions."
EXEC = "The VP wants an AI assistant for drivers."
GOV = "Delivery photos must not be retained beyond 30 days."

RECORDED_AT = datetime(2026, 8, 1, 12, 0, 0)


def write_case(root: Path, *, case_id: str = CASE_ID, question: str = QUESTION) -> Path:
    """Create a runnable case directory. Returns the directory."""
    directory = root / case_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "support_tickets.md").write_text(f"# Support\n\n{FACT}\n", encoding="utf-8")
    (directory / "stakeholder_notes.md").write_text(f"# Notes\n\n{EXEC}\n", encoding="utf-8")
    (directory / "governance.md").write_text(f"# Policy\n\n{GOV}\n", encoding="utf-8")
    (directory / "case_manifest.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "synthetic": True,
                "notice": "All evidence here is synthetic and fictional.",
                "question": question,
                "desired_outcome": OUTCOME,
                "product_area": "delivery",
                "as_of": "2026-08-02",
                "files": {
                    "support_tickets.md": {"evidence_type": "operational_record"},
                    "stakeholder_notes.md": {"evidence_type": "stakeholder_input"},
                    "governance.md": {"evidence_type": "governance_policy"},
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return directory


def _cite(evidence_id: str, quote: str) -> Citation:
    return Citation(evidence_id=evidence_id, quote=quote)


def _script(ids: dict[str, str]) -> dict[str, str]:
    """Coherent analysis for the tiny case, keyed by skill name.

    `ids` maps a marker (``fact``/``exec``/``gov``) to the evidence id the
    connector actually assigned, since ids are content hashes and cannot be
    hard-coded.
    """
    fact_cite = _cite(ids["fact"], FACT)
    exec_cite = _cite(ids["exec"], EXEC)
    gov_cite = _cite(ids["gov"], GOV)

    claims = (
        Claim(
            id="CL-1",
            statement="Address quality is the largest driver of delivery exceptions.",
            claim_type=ClaimType.FACT,
            citations=(fact_cite,),
        ),
        Claim(
            id="CL-2",
            statement="Leadership prefers an AI driver assistant.",
            claim_type=ClaimType.STAKEHOLDER_OPINION,
            citations=(exec_cite,),
            rationale="A preference, not a measurement. Seniority does not convert it.",
        ),
        Claim(
            id="CL-3",
            statement="Delivery photos cannot be retained beyond 30 days.",
            claim_type=ClaimType.GOVERNANCE_CONSTRAINT,
            citations=(gov_cite,),
        ),
    )

    alternatives = (
        Alternative(
            id="ALT-1",
            name="Validate addresses at checkout",
            kind=OptionKind.DATA_QUALITY,
            description="Catch malformed addresses before dispatch.",
            supporting=(fact_cite,),
            assessments=(
                DimensionAssessment(
                    dimension=Dimension.RISK,
                    state=AssessmentState.ASSESSED,
                    summary="Low: no customer-facing model output.",
                    citations=(fact_cite,),
                ),
                DimensionAssessment(
                    dimension=Dimension.FINANCIAL_IMPACT,
                    state=AssessmentState.CANNOT_ASSESS,
                    summary="No cost estimate exists for validation tooling.",
                ),
            ),
        ),
        Alternative(
            id="ALT-2",
            name="AI driver assistant",
            kind=OptionKind.AI_ASSISTED,
            description="Suggest exception handling to drivers in the app.",
            opposing=(gov_cite,),
            why_not_selected="Blocked by the photo-retention limit until resolved.",
        ),
        Alternative(
            id="ALT-3",
            name="Gather more evidence first",
            kind=OptionKind.FURTHER_RESEARCH,
            description="Measure exception causes by segment for one quarter.",
        ),
    )

    recommendation = Recommendation(
        statement="Validate addresses at checkout before considering an AI assistant.",
        option_kind=OptionKind.DATA_QUALITY,
        selected_alternative_id="ALT-1",
        claims=(claims[0],),
        support_level=SupportLevel.MODERATE,
        support_basis="One operational record, no cost estimate.",
        what_would_change_it=("A measured baseline by delivery segment.",),
        tradeoffs=(
            Tradeoff(
                id="TR-1",
                description="Checkout friction in exchange for fewer failed deliveries.",
                gains=("Fewer exceptions",),
                gives_up=("A step at checkout",),
                alternative_ids=("ALT-1",),
            ),
        ),
        experiment=ExperimentPlan(
            id="EX-1",
            hypothesis="Address validation reduces exceptions by a measurable margin.",
            method="Hold out one region for four weeks.",
            duration="4 weeks",
            metrics=(
                Metric(name="exception rate", role=MetricRole.SUCCESS, target="down 10%"),
                Metric(name="checkout completion", role=MetricRole.GUARDRAIL, target="no drop"),
            ),
        ),
    )

    return {
        "relevance": RelevanceOutput(relevant_ids=tuple(ids.values())).model_dump_json(),
        "classification": ClassificationOutput(claims=claims).model_dump_json(),
        "contradictions": ContradictionsOutput(
            contradictions=(
                Contradiction(
                    id="CN-1",
                    topic="the leading cause of exceptions",
                    kind=ContradictionKind.CLAIM_CONFLICT,
                    side_a=fact_cite,
                    side_b=exec_cite,
                    summary="The ticket data and the VP disagree about the cause.",
                    how_to_resolve="Recount exceptions by cause for the last quarter.",
                ),
            )
        ).model_dump_json(),
        "missing_evidence": MissingEvidenceOutput(
            gaps=(
                MissingEvidence(
                    id="MG-1",
                    question="What does address validation cost to run?",
                    impact=GapImpact.WOULD_CHANGE_SUPPORT_LEVEL,
                    why_it_matters="The business case depends on it.",
                    how_to_obtain="Ask the platform team for a build estimate.",
                ),
            )
        ).model_dump_json(),
        "alternatives": AlternativesOutput(alternatives=alternatives).model_dump_json(),
        "recommendation": RecommendationOutput(recommendation=recommendation).model_dump_json(),
        "challenger": ChallengeOutput(
            findings=tuple(
                ChallengeFinding(
                    question=q,
                    verdict=(
                        ChallengeVerdict.CONCERN
                        if q is ChallengeQuestion.OVERCONFIDENT
                        else ChallengeVerdict.PASSES
                    ),
                    explanation=f"Reviewed {q.value}.",
                )
                for q in ChallengeQuestion
            ),
            what_to_test=("Whether validation catches the addresses that actually fail.",),
        ).model_dump_json(),
    }


def evidence_ids(directory: Path) -> dict[str, str]:
    """Ask the connector what ids it assigned, since they are content hashes."""
    from decision_lens.connectors import LocalFileEvidenceSource
    from decision_lens.models import EvidenceRequest, UserContext

    records = LocalFileEvidenceSource(directory).retrieve(
        EvidenceRequest(requested_by=UserContext(user_id="pm-test"))
    )
    by_source = {r.source_id: r.id for r in records}
    return {
        "fact": by_source["support_tickets.md"],
        "exec": by_source["stakeholder_notes.md"],
        "gov": by_source["governance.md"],
    }


def write_cache(directory: Path, cache_path: Path, *, case_id: str = CASE_ID) -> Path:
    """Populate a demo cache that answers the tiny case. Returns the path."""
    cache = DemoCache()
    for skill, text in _script(evidence_ids(directory)).items():
        cache.add(
            CachedResponse(
                key=f"{case_id}::{skill}::v1",
                text=text,
                recorded_from_model="claude-opus-5",
                recorded_at=RECORDED_AT,
                input_tokens=900,
                output_tokens=250,
            )
        )
    cache.save(cache_path)
    return cache_path


def case_with_cache(root: Path) -> tuple[Path, Path]:
    """The common setup: a case directory and a cache that answers it."""
    directory = write_case(root)
    cache_path = write_cache(directory, root / "cache.json")
    return directory, cache_path

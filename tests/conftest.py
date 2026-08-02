"""Shared builders for model tests.

Each builder returns a minimal valid object so a test can vary one field and say
plainly what it is testing. All content is synthetic.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from decision_lens.models import (
    Citation,
    Claim,
    ClaimType,
    DecisionBrief,
    DecisionRequest,
    EvidenceRecord,
    EvidenceRequest,
    EvidenceType,
    SourceSystem,
    UserContext,
)

GENERATED_AT = datetime(2026, 8, 2, 9, 0, 0)
TODAY = date(2026, 8, 2)

# The verbatim text every fixture cites. Kept as a constant so a test cannot
# accidentally cite something the record does not contain.
QUOTE = "Address errors account for 40% of delivery exceptions."
CONTENT = f"Support ticket review, Q2.\n{QUOTE}\nRemaining causes are varied."


@pytest.fixture
def user() -> UserContext:
    return UserContext(user_id="pm-001", display_name="PM One", product_area="delivery")


@pytest.fixture
def request_(user: UserContext) -> DecisionRequest:
    return DecisionRequest(
        id="DR-001",
        question="Which intervention should the team prioritize to reduce delivery exceptions?",
        desired_outcome="Improve first-attempt delivery success.",
        user=user,
    )


@pytest.fixture
def evidence() -> EvidenceRecord:
    return EvidenceRecord(
        id="EV-0001",
        source_system=SourceSystem.LOCAL_FILE,
        source_id="support_ticket_summaries.csv",
        source_reference="data/sample_delivery_exceptions/support_ticket_summaries.csv",
        title="Support ticket summaries (synthetic)",
        content=CONTENT,
        evidence_type=EvidenceType.OPERATIONAL_RECORD,
        created_at=date(2026, 4, 1),
        updated_at=date(2026, 6, 1),
        owner="support-ops",
        retrieved_at=GENERATED_AT,
        product_area="delivery",
    )


@pytest.fixture
def citation() -> Citation:
    return Citation(evidence_id="EV-0001", quote=QUOTE, locator="L2")


@pytest.fixture
def claim(citation: Citation) -> Claim:
    return Claim(
        id="CL-001",
        statement="Address quality is the largest single driver of delivery exceptions.",
        claim_type=ClaimType.FACT,
        citations=(citation,),
    )


@pytest.fixture
def evidence_request(user: UserContext) -> EvidenceRequest:
    return EvidenceRequest(query="delivery exceptions", requested_by=user)


@pytest.fixture
def brief(request_: DecisionRequest, evidence: EvidenceRecord) -> DecisionBrief:
    return DecisionBrief(
        id="DB-001",
        request=request_,
        generated_at=GENERATED_AT,
        evidence=(evidence,),
    )

"""Typed domain model for DecisionLens.

Every type here serves one property: a reader of a `DecisionBrief` must be able to
trace any statement back to the evidence that produced it, or see plainly that no
evidence exists. Ungrounded assertions are representable only so that provenance
checking (Phase 8) can find and remove them.

This module holds no business logic beyond validation and derived properties.
Retrieval lives in `decision_lens.connectors`; interpretation in
`decision_lens.skills`; sequencing in `decision_lens.orchestrator`.

Two deliberate simplifications of the concept list in the build specification,
both approved before implementation:

*   Fact, Assumption, StakeholderOpinion and Constraint are one `Claim` model
    carrying a `ClaimType`. Classification is what the system *does*, so a label
    must be cheap to change — the recommendation challenger reclassifies a claim
    when it catches stakeholder preference being treated as evidence.
*   SuccessMetric and GuardrailMetric are one `Metric` carrying a `MetricRole`,
    for the same reason.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DECISION_OWNER_NOTICE",
    "SYNTHETIC_DATA_NOTICE",
    # enums
    "AssessmentState",
    "ClaimType",
    "ContradictionKind",
    "Dimension",
    "EvidenceType",
    "GapImpact",
    "Horizon",
    "MetricRole",
    "OptionKind",
    "PriorityExceptionKind",
    "SourceSystem",
    "SupportLevel",
    "ValidationSeverity",
    # request and context
    "DecisionCriteria",
    "DecisionRequest",
    "DimensionCriterion",
    "UserContext",
    # evidence
    "Citation",
    "EvidenceExcerpt",
    "EvidenceRecord",
    "EvidenceRequest",
    # analysis
    "Alternative",
    "Claim",
    "Contradiction",
    "DimensionAssessment",
    "EvidenceClassification",
    "MissingEvidence",
    "PriorityException",
    "Tradeoff",
    # recommendation
    "ExperimentPlan",
    "Metric",
    "Recommendation",
    # output
    "DecisionBrief",
    "PMDecision",
    "RunStage",
    "RunTrace",
    "ValidationIssue",
]

# Rendered on every brief. DecisionLens recommends; it does not decide.
DECISION_OWNER_NOTICE = (
    "DecisionLens supports the decision process. The product manager remains "
    "accountable for the final decision."
)

SYNTHETIC_DATA_NOTICE = "All sample evidence is synthetic. No real Walmart data is used."


class _Frozen(BaseModel):
    """Immutable, strict base. Unknown fields are an error, not a silent drop."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


# --------------------------------------------------------------------------- #
# 1. Enumerations
# --------------------------------------------------------------------------- #


class SourceSystem(StrEnum):
    """Where evidence came from.

    Only `LOCAL_FILE` is implemented. The enterprise members are declared so the
    connector roadmap is typed rather than merely described, and so a brief built
    against real systems needs no model change.
    """

    LOCAL_FILE = "local_file"
    JIRA = "jira"
    CONFLUENCE = "confluence"
    PRODUCT_METRICS = "product_metrics"
    CUSTOMER_FEEDBACK = "customer_feedback"
    SUPPORT_TICKETS = "support_tickets"
    OKRS = "okrs"
    EXPERIMENTS = "experiments"
    GOVERNANCE = "governance"
    TECHNICAL_DOCS = "technical_docs"
    PRIOR_DECISIONS = "prior_decisions"


class EvidenceType(StrEnum):
    """What kind of artifact a record is. A property of the record, not a judgment."""

    QUANTITATIVE_METRIC = "quantitative_metric"
    QUALITATIVE_RESEARCH = "qualitative_research"
    OPERATIONAL_RECORD = "operational_record"
    STRATEGY_DOCUMENT = "strategy_document"
    GOVERNANCE_POLICY = "governance_policy"
    EXPERIMENT_RESULT = "experiment_result"
    STAKEHOLDER_INPUT = "stakeholder_input"
    PRIOR_DECISION = "prior_decision"


class ClaimType(StrEnum):
    """How a single extracted statement should be read.

    These six are the classification targets required of the analysis workflow.
    The distinction that matters most to a PM is the second: an assumption written
    down long enough starts to read like a finding.
    """

    FACT = "fact"
    ASSUMPTION = "assumption"
    STAKEHOLDER_OPINION = "stakeholder_opinion"
    TECHNICAL_CONSTRAINT = "technical_constraint"
    BUSINESS_CONSTRAINT = "business_constraint"
    GOVERNANCE_CONSTRAINT = "governance_constraint"

    @property
    def is_constraint(self) -> bool:
        return self in {
            ClaimType.TECHNICAL_CONSTRAINT,
            ClaimType.BUSINESS_CONSTRAINT,
            ClaimType.GOVERNANCE_CONSTRAINT,
        }

    @property
    def is_evidence(self) -> bool:
        """Only a fact is evidence. Opinion and assumption are not, however confident."""
        return self is ClaimType.FACT


class SupportLevel(StrEnum):
    """How well evidence backs a statement.

    Qualitative judgments, deliberately worded to resist being read as calibrated
    probabilities. They are not probabilities and must never be presented as such.
    """

    LOW = "low"
    MODERATE = "moderate"
    STRONG = "strong"


class Horizon(StrEnum):
    """Which investment horizon an option belongs to."""

    CORE = "core"
    ADJACENT = "adjacent"
    INNOVATION = "innovation"


class OptionKind(StrEnum):
    """The kind of intervention an option represents.

    Ordered deliberately: doing nothing, deferring, and researching come first,
    AI comes last. DecisionLens must never assume AI is the right answer, and a
    brief listing no non-AI option has not considered the problem.
    """

    NO_CHANGE = "no_change"
    DEFER = "defer"
    FURTHER_RESEARCH = "further_research"
    PROCESS_CHANGE = "process_change"
    TRAINING_OR_DOCUMENTATION = "training_or_documentation"
    DATA_QUALITY = "data_quality"
    UX_CHANGE = "ux_change"
    RULES_BASED_AUTOMATION = "rules_based_automation"
    BUY = "buy"
    PARTNER = "partner"
    AI_ASSISTED = "ai_assisted"
    AI_AUTOMATED = "ai_automated"

    @property
    def is_ai(self) -> bool:
        return self in {OptionKind.AI_ASSISTED, OptionKind.AI_AUTOMATED}

    @property
    def is_no_build(self) -> bool:
        """No-build, defer, or research-first. At least one is required per brief."""
        return self in {
            OptionKind.NO_CHANGE,
            OptionKind.DEFER,
            OptionKind.FURTHER_RESEARCH,
        }


class ContradictionKind(StrEnum):
    """How two pieces of evidence disagree.

    DecisionLens surfaces contradictions; it does not resolve them. Naming the
    *shape* of a disagreement is what lets a PM resolve it quickly.
    """

    METRIC_CONFLICT = "metric_conflict"  # two numbers that cannot both be right
    CLAIM_CONFLICT = "claim_conflict"  # two assertions that cannot both hold
    TEMPORAL_CONFLICT = "temporal_conflict"  # both true, at different times
    SCOPE_CONFLICT = "scope_conflict"  # both true, of different populations


class GapImpact(StrEnum):
    """What the absence of a piece of evidence costs the decision."""

    WOULD_CHANGE_RECOMMENDATION = "would_change_recommendation"
    WOULD_CHANGE_SUPPORT_LEVEL = "would_change_support_level"
    WOULD_REFINE_SCOPE = "would_refine_scope"


class Dimension(StrEnum):
    """The nine dimensions opportunities are compared across.

    Reported independently. They are never combined into a composite score:
    collapsing nine partially-evidenced dimensions into one number manufactures
    precision the evidence does not support.
    """

    CUSTOMER_REACH = "customer_reach"
    FINANCIAL_IMPACT = "financial_impact"
    STRATEGIC_CUSTOMER_IMPORTANCE = "strategic_customer_importance"
    SPEND = "spend"  # current and potential
    PRODUCT_USAGE = "product_usage"
    STRATEGIC_ALIGNMENT = "strategic_alignment"
    DELIVERY_EFFORT = "delivery_effort"
    RISK = "risk"
    EVIDENCE_CONFIDENCE = "evidence_confidence"


class AssessmentState(StrEnum):
    """Whether a dimension could be assessed at all.

    `CANNOT_ASSESS` is a first-class outcome, not a blank. Treating absence of
    evidence as evidence of low value systematically defunds the innovation
    horizon, where the justifying evidence does not exist yet by definition.
    """

    ASSESSED = "assessed"
    CANNOT_ASSESS = "cannot_assess"


class PriorityExceptionKind(StrEnum):
    """Work that constrains the allocation rather than competing within it."""

    SECURITY = "security"
    COMPLIANCE = "compliance"
    CONTRACTUAL = "contractual"
    CRITICAL_RELIABILITY = "critical_reliability"


class MetricRole(StrEnum):
    """What a metric is for: proving success, or catching harm."""

    SUCCESS = "success"
    GUARDRAIL = "guardrail"


class ValidationSeverity(StrEnum):
    ERROR = "error"  # the brief must not be presented as-is
    WARNING = "warning"  # the reader should know, but the brief stands


# --------------------------------------------------------------------------- #
# 2. Request and context
# --------------------------------------------------------------------------- #


class UserContext(_Frozen):
    """Who is asking, and what they are permitted to see.

    `permissions` is a placeholder in the prototype. In an enterprise, retrieval
    runs under the requesting PM's own permissions — a PM must never see evidence
    through DecisionLens that they could not see in the source system.
    """

    user_id: str = Field(min_length=1)
    display_name: str = ""
    product_area: str = ""
    team: str = ""
    permissions: tuple[str, ...] = ()


class DimensionCriterion(_Frozen):
    """One comparison dimension, and whether it applies to this decision."""

    dimension: Dimension
    applies: bool = True
    note: str = ""


class DecisionCriteria(_Frozen):
    """What the decision should be judged on.

    Defaults to all nine dimensions. A PM may mark some inapplicable, but cannot
    supply weights: there is no composite score to weight.
    """

    dimensions: tuple[DimensionCriterion, ...] = Field(
        default_factory=lambda: tuple(DimensionCriterion(dimension=d) for d in Dimension)
    )
    require_non_ai_alternative: bool = True
    require_no_build_alternative: bool = True
    notes: str = ""

    @field_validator("dimensions")
    @classmethod
    def _at_least_one_dimension(
        cls, v: tuple[DimensionCriterion, ...]
    ) -> tuple[DimensionCriterion, ...]:
        if not v:
            raise ValueError(
                "DecisionCriteria needs at least one dimension; omit the field to get all nine"
            )
        return v

    @property
    def applicable(self) -> tuple[Dimension, ...]:
        return tuple(c.dimension for c in self.dimensions if c.applies)


class DecisionRequest(_Frozen):
    """The problem a PM brings, before any evidence is retrieved.

    `question` states a problem; it does not name a solution. A solution-first
    question can only be argued about, never answered — detecting that is a skill's
    job, but the empty and non-question cases are rejected here.
    """

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    desired_outcome: str = ""
    user: UserContext
    criteria: DecisionCriteria = DecisionCriteria()
    horizons: tuple[Horizon, ...] = ()
    time_period: str = ""
    segment: str = ""
    labels: tuple[str, ...] = ()

    @field_validator("question")
    @classmethod
    def _must_be_a_question(cls, v: str) -> str:
        if not v.endswith("?"):
            raise ValueError("DecisionRequest.question must be phrased as a question")
        return v


# --------------------------------------------------------------------------- #
# 3. Evidence
# --------------------------------------------------------------------------- #


class EvidenceRequest(_Frozen):
    """What a connector is asked to retrieve. Scope only — never a question to answer.

    An empty `query` means "no keyword narrowing", which is the normal case for a
    curated evidence directory: retrieve everything and let a relevance skill
    decide. Requiring a query would push relevance judgment into the connector,
    where it does not belong.
    """

    query: str = ""
    requested_by: UserContext
    source_systems: tuple[SourceSystem, ...] = ()
    product_area: str = ""
    time_period: str = ""
    labels: tuple[str, ...] = ()
    max_records: int = Field(default=200, gt=0)


class EvidenceExcerpt(_Frozen):
    """A verbatim span inside a record, with a locator pointing back into it."""

    text: str = Field(min_length=1)
    locator: str = ""


class EvidenceRecord(_Frozen):
    """One retrieved, citable unit of evidence.

    `id` is stable and human-readable (e.g. `EV-0007`) because it appears verbatim
    in the rendered brief. `locator` on an excerpt points *into* the source so a
    skeptical reader lands on the passage, not the document.

    A record states what the source says. It carries no judgment about quality —
    that is `EvidenceClassification`, produced separately by a skill.
    """

    id: str = Field(min_length=1)
    source_system: SourceSystem
    source_id: str = Field(min_length=1)
    source_reference: str = ""  # path, URL, or record key
    title: str = ""
    # No min_length: the validator below owns this so the error says why it matters.
    content: str
    evidence_type: EvidenceType
    created_at: date | None = None
    updated_at: date | None = None
    owner: str = ""
    retrieved_at: datetime | None = None
    product_area: str = ""
    permission_scope: str = ""  # placeholder; enforced by the connector, not here
    labels: tuple[str, ...] = ()
    excerpts: tuple[EvidenceExcerpt, ...] = ()

    @field_validator("content")
    @classmethod
    def _must_have_content(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("EvidenceRecord.content cannot be blank; there is nothing to cite")
        return v

    def contains(self, quote: str) -> bool:
        """Whether a quote actually appears in this record.

        The primitive behind programmatic citation checking: a fabricated citation
        fails here instead of reading as authoritative.
        """
        return quote.strip() in self.content

    def age_days(self, as_of: date) -> int | None:
        basis = self.updated_at or self.created_at
        return None if basis is None else (as_of - basis).days


class Citation(_Frozen):
    """A pointer from a statement to the exact text supporting it.

    `quote` is verbatim source text, not a paraphrase. Storing it is what makes
    citation-span existence checkable by string resolution rather than by trust.
    """

    evidence_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    locator: str = ""

    def __str__(self) -> str:
        return f"[{self.evidence_id}]"


# --------------------------------------------------------------------------- #
# 4. Analysis outputs
# --------------------------------------------------------------------------- #


class EvidenceClassification(_Frozen):
    """A skill's read on one record. Kept apart from the record on purpose.

    Retrieval states what a document *is*; interpretation states what it is
    *worth*. Merging them would let a judgment pass as a fact of the record.
    """

    evidence_id: str = Field(min_length=1)
    evidence_type: EvidenceType
    support_level: SupportLevel
    rationale: str = ""
    is_stale: bool = False
    age_days: int | None = None


class Claim(_Frozen):
    """One statement extracted from evidence, with how it should be read.

    A claim with no citations is representable — skills produce them — but will not
    survive provenance validation into a brief.
    """

    id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    claim_type: ClaimType
    citations: tuple[Citation, ...] = ()
    opposing_citations: tuple[Citation, ...] = ()
    support_level: SupportLevel = SupportLevel.LOW
    rationale: str = ""

    @property
    def is_grounded(self) -> bool:
        return bool(self.citations)

    @property
    def is_contested(self) -> bool:
        return bool(self.opposing_citations)

    def reclassified(self, new_type: ClaimType, rationale: str = "") -> Claim:
        """Return a copy under a different label.

        Used by the recommendation challenger when it catches stakeholder
        preference being carried as fact.
        """
        return self.model_copy(
            update={"claim_type": new_type, "rationale": rationale or self.rationale}
        )


class Contradiction(_Frozen):
    """Two pieces of evidence that disagree, presented unresolved.

    `how_to_resolve` tells the PM what would settle it. Silently discarding one
    half of a contradiction is the failure this product exists to prevent.
    """

    id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    kind: ContradictionKind
    side_a: Citation
    side_b: Citation
    summary: str = ""
    how_to_resolve: str = ""

    @model_validator(mode="after")
    def _sides_must_differ(self) -> Contradiction:
        if self.side_a == self.side_b:
            raise ValueError("A contradiction needs two distinct sides")
        return self


class MissingEvidence(_Frozen):
    """Something the decision needs that the evidence does not contain.

    `was_searched` separates "we looked and found nothing" from "no connector
    covers this" — very different signals about how far to trust a brief.
    """

    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    impact: GapImpact
    why_it_matters: str = ""
    how_to_obtain: str = ""
    was_searched: bool = True


class PriorityException(_Frozen):
    """A mandatory obligation that constrains the allocation.

    Security, compliance, contractual and critical reliability work are not
    weighted feature requests. They are never ranked against discretionary
    opportunities; validation asserts this rather than trusting it.
    """

    id: str = Field(min_length=1)
    kind: PriorityExceptionKind
    obligation: str = Field(min_length=1)
    citations: tuple[Citation, ...] = ()
    due_by: date | None = None
    note: str = ""


class DimensionAssessment(_Frozen):
    """What the evidence says about one option on one dimension."""

    dimension: Dimension
    state: AssessmentState
    summary: str = ""
    citations: tuple[Citation, ...] = ()
    support_level: SupportLevel | None = None

    @model_validator(mode="after")
    def _state_matches_content(self) -> DimensionAssessment:
        if self.state is AssessmentState.ASSESSED and not self.citations:
            raise ValueError(
                f"{self.dimension} is marked assessed but cites nothing; "
                "use CANNOT_ASSESS instead of an unsourced assessment"
            )
        if self.state is AssessmentState.CANNOT_ASSESS and not self.summary:
            raise ValueError(f"{self.dimension} cannot be assessed, so it must say what is missing")
        return self


class Tradeoff(_Frozen):
    """What choosing one option gives up."""

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    gains: tuple[str, ...] = ()
    gives_up: tuple[str, ...] = ()
    alternative_ids: tuple[str, ...] = ()


class Alternative(_Frozen):
    """An option the PM could choose, including the ones not recommended."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: OptionKind
    description: str = ""
    horizon: Horizon | None = None
    supporting: tuple[Citation, ...] = ()
    opposing: tuple[Citation, ...] = ()
    assessments: tuple[DimensionAssessment, ...] = ()
    why_not_selected: str = ""

    @property
    def unassessed_dimensions(self) -> tuple[Dimension, ...]:
        return tuple(
            a.dimension for a in self.assessments if a.state is AssessmentState.CANNOT_ASSESS
        )


# --------------------------------------------------------------------------- #
# 5. Recommendation
# --------------------------------------------------------------------------- #


class Metric(_Frozen):
    """A success or guardrail metric. The role is a field, not a separate type."""

    name: str = Field(min_length=1)
    role: MetricRole
    definition: str = ""
    target: str = ""
    rationale: str = ""


class ExperimentPlan(_Frozen):
    """What to test before committing further investment."""

    id: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    method: str = ""
    duration: str = ""
    metrics: tuple[Metric, ...] = ()

    @property
    def success_metrics(self) -> tuple[Metric, ...]:
        return tuple(m for m in self.metrics if m.role is MetricRole.SUCCESS)

    @property
    def guardrail_metrics(self) -> tuple[Metric, ...]:
        return tuple(m for m in self.metrics if m.role is MetricRole.GUARDRAIL)


class Recommendation(_Frozen):
    """The recommended option, its claims, and the conditions on it.

    `support_level` is qualitative. `what_would_change_it` is the operative field:
    a support level a reader cannot act on is decoration.
    """

    statement: str = Field(min_length=1)
    option_kind: OptionKind
    selected_alternative_id: str = ""
    claims: tuple[Claim, ...] = ()
    support_level: SupportLevel = SupportLevel.LOW
    support_basis: str = ""
    what_would_change_it: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    tradeoffs: tuple[Tradeoff, ...] = ()
    experiment: ExperimentPlan | None = None

    @property
    def ungrounded_claims(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if not c.is_grounded)


# --------------------------------------------------------------------------- #
# 6. Validation and trace
# --------------------------------------------------------------------------- #


class ValidationIssue(_Frozen):
    """One deterministic check that failed."""

    code: str = Field(min_length=1)
    severity: ValidationSeverity
    message: str = Field(min_length=1)
    location: str = ""

    @property
    def blocks_presentation(self) -> bool:
        return self.severity is ValidationSeverity.ERROR


class RunStage(_Frozen):
    """One stage of a run. Pinning provider, model and prompt version is what
    makes a brief reproducible after the fact."""

    name: str = Field(min_length=1)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error: str = ""
    #: Anything the provider wanted the reader to know about how this answer was
    #: obtained — replayed rather than called, or replayed from a recording whose
    #: prompt has since been edited. The cached provider emitted exactly that
    #: second warning for two stages and nobody saw it, because the trace had
    #: nowhere to put it and the report had nothing to print.
    warnings: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return not self.error


class RunTrace(_Frozen):
    """The audit record of one DecisionLens run."""

    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    stages: tuple[RunStage, ...] = ()
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @property
    def failed_stages(self) -> tuple[RunStage, ...]:
        return tuple(s for s in self.stages if not s.succeeded)

    @property
    def total_latency_ms(self) -> int:
        return sum(s.latency_ms or 0 for s in self.stages)


# --------------------------------------------------------------------------- #
# 7. The brief, and the PM's decision
# --------------------------------------------------------------------------- #


class DecisionBrief(_Frozen):
    """The complete output of one run.

    Field order mirrors the order a PM should read it: what was asked, what was
    found, how it was read, what conflicts, what is missing, what is mandatory,
    what else could be done, and only then what is recommended.
    """

    id: str = Field(min_length=1)
    request: DecisionRequest
    generated_at: datetime
    evidence: tuple[EvidenceRecord, ...] = ()
    classifications: tuple[EvidenceClassification, ...] = ()
    claims: tuple[Claim, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    missing_evidence: tuple[MissingEvidence, ...] = ()
    priority_exceptions: tuple[PriorityException, ...] = ()
    alternatives: tuple[Alternative, ...] = ()
    recommendation: Recommendation | None = None
    validation_issues: tuple[ValidationIssue, ...] = ()
    run_trace: RunTrace | None = None
    decision_owner_notice: str = DECISION_OWNER_NOTICE

    # -- lookups ----------------------------------------------------------- #

    def evidence_by_id(self) -> dict[str, EvidenceRecord]:
        return {e.id: e for e in self.evidence}

    def claims_of_type(self, claim_type: ClaimType) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.claim_type is claim_type)

    @property
    def constraints(self) -> tuple[Claim, ...]:
        return tuple(c for c in self.claims if c.claim_type.is_constraint)

    def all_citations(self) -> tuple[Citation, ...]:
        """Every citation anywhere in the brief. The input to provenance checking."""
        cites: list[Citation] = []
        for claim in self.claims:
            cites.extend(claim.citations)
            cites.extend(claim.opposing_citations)
        for contradiction in self.contradictions:
            cites.extend((contradiction.side_a, contradiction.side_b))
        for exception in self.priority_exceptions:
            cites.extend(exception.citations)
        for alternative in self.alternatives:
            cites.extend(alternative.supporting)
            cites.extend(alternative.opposing)
            for assessment in alternative.assessments:
                cites.extend(assessment.citations)
        if self.recommendation:
            for claim in self.recommendation.claims:
                cites.extend(claim.citations)
                cites.extend(claim.opposing_citations)
        return tuple(cites)

    def cited_evidence_ids(self) -> set[str]:
        return {c.evidence_id for c in self.all_citations()}

    def uncited_evidence(self) -> tuple[EvidenceRecord, ...]:
        """Evidence retrieved but never used — itself a signal worth showing."""
        cited = self.cited_evidence_ids()
        return tuple(e for e in self.evidence if e.id not in cited)

    # -- deterministic completeness rules ---------------------------------- #
    # Phase 8 validation turns each of these into a ValidationIssue. They live
    # here so the rule and the data stay in one place.

    @property
    def has_non_ai_alternative(self) -> bool:
        return any(not a.kind.is_ai for a in self.alternatives)

    @property
    def has_no_build_alternative(self) -> bool:
        return any(a.kind.is_no_build for a in self.alternatives)

    @property
    def unresolvable_citations(self) -> tuple[Citation, ...]:
        """Citations whose evidence is absent, or whose quote is not in the source."""
        by_id = self.evidence_by_id()
        bad: list[Citation] = []
        for citation in self.all_citations():
            record = by_id.get(citation.evidence_id)
            if record is None or not record.contains(citation.quote):
                bad.append(citation)
        return tuple(bad)

    @property
    def has_blocking_issues(self) -> bool:
        return any(i.blocks_presentation for i in self.validation_issues)


class PMDecision(_Frozen):
    """The PM's decision, recorded separately from the agent's recommendation.

    Kept apart on purpose. A disagreement between the two is one of the more
    valuable signals the system can produce about its own quality.
    """

    brief_id: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    decided_at: datetime
    decision: str = Field(min_length=1)
    rationale: str = ""
    agreed_with_recommendation: bool | None = None
    override_reason: str = ""

    @model_validator(mode="after")
    def _overrides_need_a_reason(self) -> PMDecision:
        if self.agreed_with_recommendation is False and not self.override_reason:
            raise ValueError(
                "Disagreeing with the recommendation requires an override_reason; "
                "the disagreement is the signal worth capturing"
            )
        return self

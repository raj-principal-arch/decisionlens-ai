# 03 — Architecture and Governance

> **STATUS: OUTLINE ONLY — Phase 1.**
> This document is a section plan, not finished content. It is completed in **Phase 11**.
> Nothing below describes an implemented integration. The prototype implements exactly one connector, over local synthetic files.

**Purpose.** Specify the prototype architecture, the future enterprise architecture, and the governance model that would be required to operate DecisionLens responsibly inside a large organization.

---

## Architectural invariants

These hold in every section below and are not up for negotiation during the build:

- **Connectors retrieve.** Authenticate → apply user permissions → search → retrieve → preserve metadata → normalize → return evidence. A connector never decides what the company should build.
- **Skills interpret.** Relevance, classification, contradiction detection, missing-evidence detection, alternative generation, recommendation analysis. A skill never reaches a data source.
- **DecisionLens orchestrates.** One controlled coordinator with inspectable stages. No autonomous loops, no agent-per-source, no multi-agent topology.
- **The PM decides.** The agent recommends; the human is accountable. The PM's final decision is recorded separately from the agent's recommendation.
- **Governance and verification are parallel, embedded capabilities — not sequential ones.** Governance defines which data, models, actions, and decisions are permitted; verification provides evidence that outputs comply with those expectations. Both are designed into the workflow from the beginning. Neither is a layer applied after the fact, and neither is downstream of the other.

---

## Planned sections

### 1. Prototype architecture
The Phase 8 pipeline as built: PM problem → structured local interface → orchestrator → `LocalFileEvidenceSource` → normalized evidence → evidence-analysis skills → decision-analysis skills → recommendation challenger → validation and guardrails → decision brief + run trace → PM final decision.

### 2. Enterprise architecture
The same spine with evidence planning and shared authorized connectors substituted for the local file source, plus policy and governance in the validation layer, and an audit trace alongside the brief.

### 3. Connector model
The retrieval-only contract. The `EvidenceSource` protocol. Why connectors are shared infrastructure and not autonomous agents.

### 4. Jira scaling example
One Jira connection maps to one Jira site. Project keys (LASTMILE, DRIVER, PAYMENTS, CHECKOUT, MARKETPLACE, SUPPLYCHAIN) are **configuration inside a shared connection**, not separate connectors. Multiple sites mean multiple centrally managed connections. PMs select scope; they never handle credentials.

### 5. Permissions and delegated identity
Retrieval executes under the requesting PM's own permissions. A PM must never see evidence through DecisionLens that they could not see directly in the source system.

### 6. Normalized evidence
The shared `EvidenceRecord` shape and the metadata every source must preserve: source system, record ID, title, content, evidence type, created and updated dates, owner, source reference, retrieval timestamp, product area, freshness, and permission metadata.

### 7. Analysis skills
The six approved skills, their typed boundaries, and their versioned prompts.

### 8. Orchestrator
Stage sequencing, partial-failure handling, timeouts, retry limits, and the deliberate absence of open-ended loops.

### 9. Recommendation challenger
The adversarial pass over the draft recommendation, and the specific questions it must ask.

### 10. Validation and guardrails
Deterministic checks: source exists, citation span exists, required sections present, assumptions separated from facts, contradictions visible, missing evidence surfaced, non-AI alternative present, no-build/defer/research alternative present, support level not overstated relative to evidence.

### 11. Audit trace
`RunTrace` contents: stages, inputs, prompt versions, model and provider identifiers, usage, latency, validation issues. What must be reconstructable after the fact.

### 12. Identity and access
Authentication, authorization, service versus delegated identity.

### 13. Data classification and PII
Handling rules by classification, PII in customer feedback and support tickets, redaction expectations.

### 14. Lineage, freshness, and retention
Where each claim came from, how old it is, how long briefs and traces are kept.

### 15. Prompt and model versioning
Why a brief is only reproducible if the prompt version and model version are pinned and recorded.

### 16. Human approval
The accountability boundary. What DecisionLens may never do autonomously.

### 17. Cost controls
Per-run and per-org budgets, caching, and the cost consequences of a multi-stage workflow versus a single call.

### 18. Observability
Metrics, logging (never secrets), connector health, and evaluation telemetry in production.

### 19. Incident handling
What happens when a connector leaks unauthorized evidence, a model degrades, or a brief is found to be materially wrong after a decision was made on it.

### 20. Red-team testing
Adversarial cases: prompt injection through retrieved evidence, stakeholder pressure framed as evidence, misleading denominators, and evidence crafted to produce a predetermined recommendation.

### 21. Override tracking
Recording when a PM disagrees with a recommendation and why — one of the more valuable signals the system can generate about its own quality.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)
- [04 — Evaluation](04-evaluation.md)
- [05 — Decision Log](05-decision-log.md)

# 02 — Ecosystem and Adoption

> **STATUS: OUTLINE ONLY — Phase 1.**
> This document is a section plan, not finished content. It is completed in **Phase 11**.
> Nothing below should be read as a described capability or a commitment.

**Purpose.** Describe how an organization moves product managers from little or no AI use to effective, responsible adoption — the tools, agents, reusable skills, data, knowledge, governance, training, and measurement that surround DecisionLens. DecisionLens is one component of that ecosystem, not the ecosystem itself.

---

## Planned sections

### 1. AI-native maturity stages
A stage model from no use → assisted drafting → structured analysis → evidence-grounded decision support → measured decision improvement. Each stage gets its observable behaviours, its blockers, and what moves a PM to the next stage.

### 2. Tooling layer
What PMs actually touch. Where DecisionLens sits relative to general assistants, and the deliberate decision not to build a general-purpose copilot.

### 3. Model gateway
Centralized model access: vendor neutrality, cost controls, rate limits, logging, model version pinning, and why individual teams should not hold their own provider credentials.

### 4. Reusable skills
Analysis skills as shared, versioned, independently testable organizational assets rather than prompts pasted between teams. How a skill is proposed, reviewed, versioned, and retired.

### 5. Shared connectors
Connectors are shared infrastructure across all PMs — never one connector per PM. Retrieval only; no reasoning. Cross-reference §03.

### 6. Data and knowledge
Which evidence sources matter for product decisions, their quality characteristics, freshness expectations, and known gaps.

### 7. Enterprise configuration
Centrally managed: system URLs, authentication, API setup, schema mapping, rate limits, security policy, audit logging, connector health.

### 8. Team / product-area configuration
Managed by platform admins, product leads, or enablement: relevant projects, dashboards, feedback sources, default metrics, labels, product terminology, governance requirements, default time windows.

### 9. PM runtime context
Provided or inferred at request time: identity, product area, decision question, desired outcome, time period, segment, optional scope filters, existing permissions. PMs never configure credentials or APIs.

### 10. Training
What PMs need to learn, and — more importantly — what they should *not* have to learn. Emphasis on evidence interrogation over prompt technique.

### 11. Office hours, champions, and communities of practice
The human scaffolding around rollout. How embedded champions differ from central enablement, and what each is accountable for.

### 12. Responsible-use guidance
Practical guidance on where AI is and is not appropriate for product decisions, including the explicit expectation that a recommendation is challenged rather than accepted.

### 13. Support model
Triage, escalation, connector-health incidents, and who owns what.

### 14. Adoption measurement
Leading indicators of adoption, and why raw usage volume is a poor primary metric.

### 15. Outcome measurement
Whether decisions actually improved, separated by horizon. **Leading indicators** measurable in a short study: groundedness, unsupported claims, verification time, alternative coverage, PM-rated actionability. **Lagging outcome measures** requiring a real-world pilot across multiple decision cycles: customer outcomes, revenue, cost avoidance, retention, portfolio return. The section must be explicit that the second group cannot be demonstrated within this take-home and is proposed as future measurement, not claimed.

### 16. Feedback loops
How PM feedback, override tracking, and evaluation results feed back into skills, prompts, connectors, and training.

### 17. Ownership model
Who owns the platform, the connectors, the skills, the governance, and the adoption outcome.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [03 — Architecture and Governance](03-architecture-and-governance.md)
- [04 — Evaluation](04-evaluation.md)
- [05 — Decision Log](05-decision-log.md)

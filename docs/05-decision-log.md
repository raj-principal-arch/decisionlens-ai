# 05 — Decision Log

**Status:** Phase 1 deliverable. Maintained continuously; new entries are appended as later phases make decisions.

This log records how DecisionLens was framed, which earlier framings were rejected and why, and how AI was actually used to produce this repository. It documents only what occurred. No tool, activity, research, or result is described here that did not happen.

---

## Part 1 — How the concept evolved

### D1. Initial concept: AI Product Workflow Coach — **rejected**

The first concept was a broad assistant that would coach product managers across their workflow.

**Rejected as too broad.** It had no falsifiable hypothesis, no clear boundary against a general-purpose assistant, and no way to demonstrate value in a take-home. A tool that helps with everything cannot be evaluated on anything. Scope was the problem, not the idea.

### D2. Second concept: Evidence-Based Product Decision Agent — **retained, then challenged**

The concept narrowed to an agent supporting evidence-based product decisions. This was retained as the right territory: consequential, PM-owned, evidence-dependent, and concretely demonstrable.

### D3. Challenge to the framing — **framing changed**

The framing was then challenged on a specific point: **weak evidence in product decisions is a perennial PM-craft problem, not an AI-adoption problem.** PMs have always reasoned under fragmented evidence. An assignment about AI enablement needs a problem that is specifically about AI adoption, not one that merely happens to involve AI in its solution.

This challenge was accepted. It is the single most consequential change in the project's framing.

### D4. Reframing to trust, traceability, and verification — **adopted**

The framing moved from *"PMs have weak evidence"* to *"PMs cannot cheaply verify consequential AI output, and that is what stops AI adoption at the boundary of consequence."*

This reframing is what makes the problem an AI-enablement problem. It explains the observed pattern — heavy AI use for drafting, summarizing, and brainstorming; light use for decisions that matter — as a consequence of verification cost rather than of tool access or skill.

The reasoning is developed in [01 — Product Strategy](01-product-strategy.md).

### D5. "Evidence-grounded" replaced "evidence-based" — **adopted**

A deliberate wording change, not cosmetic.

*Evidence-based* describes a posture: the recommendation was informed by evidence. It is unfalsifiable — anyone can claim it.

*Evidence-grounded* describes a mechanical property: each claim is anchored to a retrievable source span that can be checked. It is falsifiable, and the prototype checks it programmatically.

The product's central promise is in that distinction, so the language had to carry it.

### D6. Solution-first example question — **rejected**

An early sample case asked a question in the shape of *"should we build an AI assistant for delivery exceptions?"*

**Rejected.** The question presupposes both the solution and the technology. A system asked that question can only argue about how to build the thing already named. It cannot recommend a process change, a data-quality fix, or doing nothing — which are frequently the right answers.

Worse, a tool built to encourage AI adoption that is fed solution-first questions will reliably recommend AI, and PMs will correctly stop trusting it.

### D7. Problem-first example question — **adopted**

The bundled sample case became:

> **Which intervention should the team prioritize to reduce delivery exceptions?**

This admits the full range of answers: notifications, address validation, driver workflow simplification, training, rules-based automation, a limited AI capability, more research, deferral, or no change.

The constraint is enforced structurally rather than by intention. Every brief must contain at least one non-AI alternative and at least one no-build, defer, or further-research alternative, and validation checks for both deterministically. DecisionLens must be able to conclude that an AI solution is not justified.

### D8. Single orchestrator, not multi-agent — **adopted**

The architecture is one DecisionLens orchestrator with controlled, inspectable stages. Connectors retrieve; skills interpret; the orchestrator coordinates; the PM decides.

Rejected: one autonomous agent per data source, and any multi-agent topology.

The reasoning is that the property under test is *verifiability*. An architecture whose own behaviour is hard to trace cannot credibly demonstrate that traceability improves decision support. A multi-agent design would also have been more impressive to describe and less able to prove anything — the wrong trade for this work.

### D9. Enterprise connectors documented, not implemented — **adopted**

The prototype implements exactly one connector, `LocalFileEvidenceSource`, over synthetic files. Jira, Confluence, product metrics, customer feedback, support tickets, and the rest are specified in [03 — Architecture and Governance](03-architecture-and-governance.md) but not built.

A written connector contract is more honest than stub classes that raise `NotImplementedError`, and no claim of access to any real system appears anywhere in this repository.

### D10. Strong baseline, not a strawman — **adopted**

The evaluation baseline uses the same model and version, the same evidence, the same output schema, and a genuinely strong prompt. It differs from DecisionLens only in that it is one model call without the controlled stages.

If a strong single call performs comparably, the controlled workflow is unnecessary complexity and the evaluation should say so. That outcome is recorded as a finding, not suppressed.

### D11. No vector database — **adopted**

Not justified at the size of the prototype corpus, and it would make retrieval harder to inspect. Keyword and manifest-driven retrieval over explicitly identified files keeps every retrieval step auditable, which serves the product thesis rather than compromising it. Revisiting this would require explicit approval.

---

## Part 2 — How AI was used to build this

Recorded plainly, because the assignment evaluates AI-native working approach and an inaccurate account here would be self-defeating.

### ChatGPT

Used for assignment decomposition and initial concept exploration. It produced the first structural breakdown of the assignment and the early concept space, including the AI Product Workflow Coach concept that was subsequently rejected (D1).

### Claude

Used to pressure-test the work rather than to generate it. Specifically:

- **Problem selection** — challenging whether the selected problem was genuinely an AI-adoption problem rather than a PM-craft problem. This produced D3 and D4, the most important framing change in the project.
- **Evaluation rigor** — challenging baseline strength, the difference between deterministic and model-based metrics, and what would falsify the hypothesis.
- **Enterprise enablement** — pressure-testing the connector model, the configuration layers, and permission handling.

### Claude Code

Used to build the repository under an explicit **inspect → plan → approve → execute** process. Each phase is authorized individually. Approval of one phase is not approval of the next. Every phase ends with a report of what changed, validation results, `git status --short`, `git diff --stat`, and known issues, followed by a wait for human review.

### Human judgment

AI output is reviewed and revised rather than accepted. Final scope, framing, and architecture are human decisions. The strategy document distinguishes observation, product judgment, assumption, and hypothesis specifically so a reader can see where reasoning is doing the work.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)
- [03 — Architecture and Governance](03-architecture-and-governance.md)
- [04 — Evaluation](04-evaluation.md)

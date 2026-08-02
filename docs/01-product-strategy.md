# 01 — Product Strategy

**Status:** Phase 1 deliverable. No prototype results exist yet. None are claimed here.

**Labelling.** No primary user research yet. Claims are tagged: **[Observation]** verifiable · **[Product judgment]** my reasoning · **[Assumption]** unevidenced · **[Hypothesis]** to be tested. No numerical scores appear. Weighting criteria I have not measured would dress judgment up as analysis — the failure DecisionLens exists to expose.

---

## The argument in brief

| | |
|---|---|
| **Decision context** | PMs allocate limited budget and capacity across core-product improvements, adjacent growth, and longer-term innovation. Those horizons rarely have comparable evidence behind them. |
| **Problem selected** | Consequential AI output is expensive to verify. That cost — not tool access, training, or model quality — is what stops PMs using AI for decisions that matter. |
| **Why this one** | No known playbook exists for it. It sits exactly at the adoption boundary. It fails gracefully if wrong. It does not dissolve as models improve. |
| **Hypothesis** | Make output verifiable by construction — traceability, evidence classification, contradiction detection, missing-evidence identification, mandatory alternatives, transparent uncertainty — and PMs will use AI for higher-value decisions. |
| **How it is tested** | One orchestrator over synthetic evidence, against a strong single-call baseline, on deterministic metrics. A negative result is reported as a result. |
| **What it is not** | Not a portfolio-scoring tool. Not a copilot. Not a decision-maker. The PM decides. |

---

## Executive summary

PMs decide what to build. They also decide how to split limited budget and capacity across **core-product improvements, adjacent growth, and longer-term innovation**.

In a delivery organization those horizons might be: make existing deliveries more reliable; add new fulfilment options; bet on autonomous delivery. They compete for one budget. They are rarely comparable on the same evidence.

DecisionLens compares them across nine dimensions: customer reach, financial impact, strategic-customer importance, current and potential spend, product usage, strategic alignment, delivery effort, risk, and evidence confidence.

These are **comparison dimensions, not a scoring formula.** For each one, DecisionLens reports what the evidence says, where it came from, and how confident the read is — including when a dimension cannot be assessed at all. One composite number from nine partly-evidenced dimensions would be false precision. **[Product judgment]**

**Security, compliance, contractual, and critical reliability work are mandatory exceptions, not weighted feature requests.** They constrain the allocation before comparison begins. A compliance obligation that can lose a weighted comparison to a growth bet has been modelled wrong. **[Product judgment]**

That is the context. The selected problem is narrower.

Most PMs with AI access use it to draft, summarize, and brainstorm. Few use it for the decision above. The question is not *why don't PMs use AI* — many do. It is *why usage stops at the boundary of consequence*.

The bet: **for a consequential decision, verifying AI output can cost more than doing the work unaided.** A PM who cannot see where a claim came from, what rests on assumption, and what was ignored has not saved work. They have moved it from analysis to audit, and added the risk of missing something. **[Product judgment]**

So: **portfolio allocation is the context. Verification cost is the selected problem.** DecisionLens is not a portfolio-scoring tool. It tests whether output that is verifiable by construction moves AI use across that boundary. It does not decide. It makes a recommendation easier to challenge.

### What the public evidence says

| Finding | Source |
|---|---|
| Inaccuracy is the most commonly experienced negative consequence of gen AI (30% of organizations) and the most-cited risk (44%). | McKinsey, *State of AI*, 2025 |
| 86% of organizations are past pilots, but only 34% trust the actions of their AI agents. 74% rate inaccuracy a highly relevant risk. | McKinsey, *State of AI trust*, 2026 |
| Employees use AI more often, but verification remains common in high-stakes workflows. | McKinsey, *State of AI trust*, 2026 |
| 88% report AI adoption; 38% have scaled beyond experiments; 6% report transformative impact. | McKinsey, *State of AI*, 2025 |

**What it does not show.** None of this is PM-specific. None measures verification *cost*. It establishes that inaccuracy and trust are live enterprise barriers, and that verification persists in high-stakes work. It does not establish that verification effort is what stops PMs. That step is **[Assumption] #1**. **[Observation]**

Sources: [State of AI, McKinsey 2025](https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai) · [State of AI trust, McKinsey 2026](https://www.mckinsey.com/capabilities/tech-and-ai/our-insights/tech-forward/state-of-ai-trust-in-2026-shifting-to-the-agentic-era)

---

## What "AI-native PM" means

Not a PM who uses AI tools often. That definition fits anyone who has pasted a PRD into a chat window. It explains nothing about why outcomes differ.

An AI-native PM **redesigns discovery, prioritization, decision-making, execution, and learning around the complementary strengths of human judgment, data, and AI.**

*Complementary* is the operative word. AI brings breadth and recall across more evidence than a person can hold. Data brings what happened, not what was remembered. Human judgment brings context, accountability, and the decision. Using AI as a faster typewriter changes none of this. **[Product judgment]**

DecisionLens targets decision-making. It touches discovery and learning through retrieval and durable records. Three things should change. Each is a claim about what *should* change, not a measurement.

### 1. Product decisions

AI shifts the constraint from *how much evidence a PM can read* to *how well they can interrogate it*. **[Product judgment]**

- **Coverage widens.** Sources skipped for time — old tickets, an eighteen-month-old research deck, an unopened dashboard — enter the analysis.
- **Falsification gets cheaper.** "What would make this wrong?" becomes routine, not an act of unusual discipline.
- **Alternatives become mandatory.** A machine can be *made* to always produce the no-build option. A person under deadline will not.
- **Uncertainty becomes explicit.** Not a hedge in the last paragraph. A stated confidence, with a named basis and a named exit condition.

The failure to avoid: AI that speeds up documents and leaves decision quality untouched. Shipping the wrong thing more efficiently is not improvement. **[Product judgment]**

### 2. Team effectiveness

Decisions get re-litigated because their reasoning does not last. Six months on, the deck survives but the evidence behind it does not, so the team argues from memory and seniority. A traceable brief should mean:

- New joiners reconstruct a decision without an archaeology project.
- Disagreement shifts from "I think X" to "the brief cites Y — here is why Y is wrong."
- Reversals become legible. A decision that was right on the evidence then available is not the same event as one that was always poorly reasoned.

### 3. Business and customer outcomes

The intended outcome: fewer confidently wrong investments, and earlier detection of the wrong ones.

Business outcomes are measurable. They cannot be **demonstrated within this take-home** — a narrower claim. Execution, market timing, and luck sit between decision quality and business results, and the lag exceeds the exercise. **[Observation]**

Measurable here, as **leading indicators**: groundedness, unsupported claims, verification time, alternative coverage, PM-rated actionability.

Needs a real pilot, as **lagging outcomes**: customer impact, revenue, cost, retention, portfolio return. Proposed, not claimed.

---

## Target users

**Primary.** PMs making consequential calls — prioritization, build/buy/partner, investment, sunset — under fragmented evidence and time pressure.

**Secondary.** Engineering and design leads interrogating a PM's reasoning. PM leadership reviewing a portfolio. Enablement teams accountable for responsible adoption.

**Not the user.** Anyone wanting a general-purpose copilot or faster documents. That product exists elsewhere. **[Product judgment]**

---

## Problem statement

### Why cross-horizon comparison is hard

The nine dimensions are **not evidenced equally, and not evidenced in the same places.** Usage and financials are quantitative and sit in systems of record. Strategic importance and alignment are qualitative and sit in people's heads and ageing documents. Effort is an estimate with its own uncertainty. Risk usually carries the least evidence and the most consequence. **[Product judgment]**

Take the delivery example. Reducing delivery exceptions has years of tickets, metrics, and complaints behind it. An autonomous-delivery bet has almost none — not because it is weaker, but because it has not happened yet.

Innovation loses for that reason. It competes on dimensions where core work always looks stronger: known usage, measurable revenue, named customers. The evidence that would justify the bet does not exist yet. That is what makes it a bet. **A method that reads absence of evidence as evidence of low value will systematically defund innovation.** So missing-evidence detection is first-class, not a nicety. Naming the unknown keeps an unevidenced option in the conversation on honest terms. **[Product judgment]**

### Two nested problems

**The PM-craft problem** — perennial, not AI-specific. Consequential decisions rest on evidence that is fragmented, uneven in quality, partly qualitative, sometimes contradictory, and missing where it matters most. PMs have always worked this way.

**The AI-enablement problem** — the one selected. AI could help with the craft problem, but adoption stalls before consequential work. For a decision carrying real cost, a PM must establish: which claims are supported, where each came from, which rest on assumptions, which are stakeholder preference, what constraints apply, what is missing, where sources conflict, whether the confidence is warranted, which alternatives were skipped, and what to test next.

General-purpose AI output does not make those cheap. It is fluent, undifferentiated, and confident. Together those three make verification *harder* than reading the sources, because fluency hides the seams. **[Product judgment]**

---

## Alternatives considered

Each is a real barrier. The question is which one is *binding* at the move from low-risk to consequential use. **[Product judgment]** throughout.

**Tool access.** A procurement and rollout problem with known solutions. It also does not fit the pattern: the PMs who stop at summarizing mostly have access.

**Training and prompt literacy.** Useful, and part of any serious ecosystem (§02). But better prompting produces better-*sounding* output, not more checkable output. It can worsen the problem by raising fluency faster than reliability.

**Workflow integration.** Important, and why this design assumes connectors over copy-paste. But integrating unverifiable output only increases its volume.

**Data and knowledge access.** The closest competitor, and a **necessary platform dependency rather than a competing alternative.** Retrieval surfaces information. It cannot say which of it is solid. Perfect retrieval still leaves an undifferentiated wall of text. Access is a precondition for verification, not a substitute.

**Governance and policy clarity.** A real blocker in regulated contexts — and **not downstream of verification.** The two are **parallel, embedded capabilities.** Governance defines what is permitted; verification evidences compliance. Both are designed in from the start. Not selected because it is an organizational capability rather than a product problem — but it is a co-requisite, and §03 treats it as one.

**Model quality.** Improving without any input from a PM enablement function, so a poor foundation for strategy. And better models do not dissolve this problem — see below.

**Use-case discovery.** PMs know what they want help with. The gap is between wanting help and trusting it.

---

## Why not an existing tool

| Option | Why it does not close the gap |
|---|---|
| A frontier assistant plus a strong prompt | Fluent output, no enforced traceability. Prompting raises quality; it cannot make a claim checkable. This is the **§04 baseline**. If it wins, that is reported. |
| Enterprise search (Glean and similar) | Solves retrieval, not interpretation. Returns documents. Does not classify evidence, surface contradictions, or name what is missing. |
| Copilot in the document tools | Optimizes drafting speed — the low-verification tasks PMs already use AI for. |
| Prioritization tools (Productboard, Jira Product Discovery) | Structure the decision but do not ground it. Inputs stay hand-entered assertions with no source. |

None produces the thing in question: **a recommendation whose every claim resolves to a source span you can check.** **[Product judgment]**

---

## Selection criteria

Applied qualitatively. No weights, no scores.

1. **Is it hard?** The assignment asks for the hardest problem, not only the most valuable. A problem with a known playbook is not it.
2. **Is it the binding constraint?** If solved and nothing else changed, would behavior move?
3. **Does it unlock the high-value work specifically?** Not general convenience — the consequential decisions.
4. **Is it PM-shaped?** A problem better owned by IT, security, or the model vendor is the wrong choice.
5. **Is it testable here?** A hypothesis I cannot experiment against produces an essay, not a product.
6. **Does it fail gracefully?** If the hypothesis is wrong, does the work leave something useful behind?
7. **Is it durable?** Does it survive two more model generations?

---

## Why verification was selected

**Hardest of the seven.** Tool access, training, integration, and use-case discovery are execution problems with playbooks: provision, teach, integrate, catalogue. Data access is hard but has a definition of done. Model quality is a vendor's roadmap. Verification has no established answer. Nobody yet knows how to make a consequential AI recommendation cheap to check. **[Product judgment]**

**Binding at the boundary in question.** Drafting, summarizing, and brainstorming are *low-verification* tasks: the author knows the domain, errors are cheap and visible, and a human reviews anyway. Consequential decisions invert all three. The adoption boundary and the verification-cost boundary sit in the same place. That is a strong hint. **[Product judgment]**

**Fails gracefully.** If PMs turn out to be blocked by access or training instead, a source-grounded brief still beats an untraceable one. The connector and classification work survives any competing theory. Few alternatives have that property.

**Durable under model improvement** — the criterion I weigh most. Verification matters more as the likelihood and consequence of a wrong recommendation rise. Consequential, hard-to-reverse decisions need more traceability than drafting does.

This is a **heuristic, not a formula.** Verification need also turns on **reversibility**, **detectability**, **evidence quality**, and **regulatory risk**. As models improve, error likelihood falls — but delegated decisions get more consequential and less reversible, and several of those factors do not move at all. Verification infrastructure is not a stopgap for weak models. It is what lets strong models be used for work that matters. **[Product judgment]**

**Honestly uncertain.** A hypothesis, not a finding. §04 and the proposed PM study are built to find out, not to confirm.

---

## Why product decisions are the proving ground

Product decisions concentrate everything that makes verification hard: high consequence, fragmented evidence, mixed qualitative and quantitative sources, real contradictions, politically loaded stakeholder input, and one accountable human at the end. **[Product judgment]**

They are where getting it right is worth most and accountability is clearest. If evidence-grounding does not help here, the case elsewhere is weak.

The bundled case is one of these. Reducing delivery exceptions draws on customer feedback, operational metrics, support tickets, engineering constraints, governance requirements, prior experiments, and executive preference — seven kinds of evidence that routinely disagree, one of which is not evidence at all. All synthetic. §04 describes the corpus and its planted conditions.

---

## Problem-first decision framing

DecisionLens starts from a customer, product, business, or operational problem. It must never assume AI is the answer, that a feature must be built, or that the loudest stakeholder is right.

A tool built to drive AI adoption that reflexively recommends AI is not decision support. It is a sales instrument, and PMs will correctly stop trusting it. **[Product judgment]** It must be able to recommend process change, training, documentation, rules-based automation, data-quality work, UX change, build/buy/partner, further research, deferral, or no change — and to conclude that AI is not justified.

Enforced structurally, not by intention. Every brief needs at least one non-AI alternative and at least one no-build, defer, or research alternative. Both are checked deterministically.

The bundled case asks:

> **Which intervention should the team prioritize to reduce delivery exceptions?**

Not *"should we build an AI assistant for delivery exceptions?"* The first admits every answer. The second has already decided. **[Observation]**

---

## Enterprise knowledge dependency

**DecisionLens is only as good as the evidence it can reach.** Traceability over an incomplete corpus yields confident, well-cited, badly scoped conclusions — worse than obvious ignorance, because it is harder to spot. **[Product judgment]**

Enterprise data access is a **necessary platform dependency**. What DecisionLens adds on top is the interpretation layer: evidence classification, contradiction detection, missing-evidence analysis, tradeoff comparison, traceable recommendations.

In an enterprise that needs authorized, permission-respecting connectors across customer feedback, product metrics, Jira, Confluence, support tickets, OKRs, experiment results, governance policy, and prior decisions. Shared infrastructure, centrally configured, running under the requesting PM's own permissions. §03 specifies the model.

The prototype implements one connector, `LocalFileEvidenceSource`, over synthetic files. Enterprise connectors are **documented, not implemented.** No access to any real system is claimed anywhere in this repository. **[Observation]**

This is also why missing-evidence detection matters more than it looks. Reporting what could *not* be found turns a silent gap into a visible one.

---

## Hypothesis and falsifiability

**[Hypothesis]**

> If consequential AI output becomes faster and easier to verify — through source traceability, evidence classification, contradiction detection, missing-evidence identification, explicit alternatives, and transparent uncertainty — then PMs will use AI more responsibly and effectively for higher-value product decisions.

### What would falsify it

- Research shows the dominant barriers are tool access, training, workflow integration, policy, data access, model quality, management support, or absence of use cases — and verification ranks low.
- Evidence-grounded output does not reduce verification time against a strong baseline.
- It reduces verification time but does not improve decision quality, actionability, or willingness to use AI for consequential work.
- PMs treat the added structure as noise they skip rather than signal they use.
- Verification burden merely moves: PMs audit citations instead of claims, at equal or greater cost.
- A strong single-call baseline performs comparably, making the controlled workflow unnecessary complexity.

That last one is why the §04 baseline is deliberately strong: same model, same evidence, same schema, a genuinely good prompt. A strawman would let me claim a win I had not earned. **[Observation]**

---

## Prototype scope

**In scope:**

- One orchestrator running a controlled, inspectable sequence of stages
- One connector, `LocalFileEvidenceSource` (Markdown, text, CSV, JSON)
- Six analysis skills: relevance, classification, contradiction detection, missing-evidence detection, alternative generation, recommendation analysis
- A recommendation challenger that attacks the draft before a human sees it
- Deterministic validation: citation spans resolve, required sections present, non-AI alternative present, no-build/defer alternative present, support level justified
- A synthetic case with planted contradictions, gaps, constraints, and misleading evidence
- A strong single-call baseline
- A vendor-neutral provider boundary with a deterministic cached provider needing no API key
- Structured `DecisionBrief` and `RunTrace`, with the PM's final decision recorded separately

**Out of scope:** everything in *Non-goals*.

---

## Non-goals

- One autonomous agent per data source
- A multi-agent system or agent swarm
- A general-purpose PM copilot or chat interface
- A complete enterprise knowledge platform
- Real Jira, Confluence, Slack, analytics, or Walmart integrations
- Any use of real Walmart data
- A vector database (not justified at this corpus size; would require explicit approval)
- An agent framework
- Automated decision-making of any kind

The most likely way this project fails is over-building. A four-agent architecture with a vector store would be more impressive to describe and less able to demonstrate the one property under test. **[Product judgment]**

---

## Proposed metrics

**Proposed, not measured.** No results exist yet. Fabricating them would violate the premise of the product. The first three groups are **leading indicators**, measurable here or in a short study. The fourth contains **lagging outcome measures** needing a real pilot.

**Deterministic, computable in the harness:** unsupported-claim rate · citation validity and citation-span existence (programmatic resolution against source text) · required-section completion · non-AI alternative present · no-build/defer/research alternative present · contradiction precision and recall · missing-evidence recall · appropriate restraint under insufficient evidence · run-to-run consistency, cost, latency.

**Model-based, labelled as such wherever reported:** citation-support accuracy · evidence-classification quality. An LLM judge is not objective truth and will not be presented as one. **[Observation]**

**Proposed for the real-PM study** (not conducted): verification time · total completion time · decision-quality rating · trust · willingness to use · actionability · unsupported claims found · assumptions surfaced · alternatives considered · whether the PM changed the decision · continued use over time.

**Proposed longer-horizon outcome measures**, needing a real pilot and **not demonstrable within this take-home**: customer outcomes · revenue impact · cost avoidance from investments not made · retention · portfolio return.

---

## Assumptions requiring validation

Each is unvalidated. Each would change the strategy if false.

1. PMs want to verify consequential AI output and find it expensive — rather than not verifying at all, or avoiding AI for unrelated reasons.
2. Structured traceability reduces verification effort rather than adding a second review surface.
3. Surfacing contradictions is valued rather than experienced as the tool passing back the hard part.
4. Named missing evidence changes behavior — PMs act on it rather than noting it and proceeding.
5. Mandatory alternatives are read seriously rather than skimmed as boilerplate.
6. Support labels are read as qualitative judgments, not silently as probabilities.
7. The controlled workflow beats a strong single call by a margin justifying its complexity. **§04 tests this directly; a negative result is a finding, not a failure to report.**
8. Enterprise connectors can be built with permission fidelity such that a PM never sees unauthorized evidence.
9. Findings from synthetic evidence transfer to real enterprise evidence, which is messier and more political.
10. Verification value persists as models improve, for the reason argued above.

---

## Related documents

- [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)
- [03 — Architecture and Governance](03-architecture-and-governance.md)
- [04 — Evaluation](04-evaluation.md)
- [05 — Decision Log](05-decision-log.md)

# decisionlens-ai

An evidence-grounded AI agent for verifiable product decision-making.

Product managers must determine what to build and how to allocate limited budget and capacity across **core-product improvements, adjacent growth opportunities, and longer-term innovation**. DecisionLens helps them compare opportunities using customer reach, financial impact, strategic-customer importance, current and potential spend, product usage, strategic alignment, delivery effort, risk, and evidence confidence.

These are comparison dimensions, not a scoring formula. DecisionLens reports what the evidence says on each dimension, where that evidence came from, and how confident the assessment is — including when a dimension cannot be assessed at all. It does not collapse them into a composite number.

**Security, compliance, contractual, and critical reliability work are treated as mandatory priority exceptions**, not ordinary weighted feature requests. They constrain the allocation rather than competing within it.

To support those decisions, DecisionLens turns fragmented evidence into a traceable, challengeable, and testable recommendation. Every claim carries a source you can check. Contradictions are surfaced rather than smoothed over. Missing evidence is named. Alternatives — including non-AI and no-build options — are mandatory. Confidence is stated with its basis and with the condition that would change it.

**DecisionLens does not decide. It makes a recommendation easier to challenge.**

---

## Current status

> **Phase 1 of 12 — product foundation and scaffolding.**
> **The prototype is not runnable yet.** There is no working agent, no evidence connector, and no evaluation results in this repository today.
>
> No performance claim, evaluation result, or user finding appears anywhere in these documents. Where results will eventually go, the section is explicitly marked empty.

| Phase | Deliverable | State |
|---|---|---|
| 0 | Repository audit | Complete |
| 1 | Product strategy, decision log, scaffolding | Complete |
| 2 | Domain models and evidence-source contract | Not started |
| 3 | Local file evidence connector | Not started |
| 4 | Synthetic sample case and ground truth | Not started |
| 5 | Model-provider abstraction, cached demo provider | Not started |
| 6 | Strong baseline | Not started |
| 7 | Analysis skills | Not started |
| 8 | Orchestrator, challenger, validation, provenance | Not started |
| 9 | Rendering, CLI, structured Streamlit UI | Not started |
| 10 | Evaluation harness and results | Not started |
| 11 | Enterprise ecosystem and governance docs | Not started |
| 12 | Final quality review | Not started |

---

## Assignment context

This repository is a take-home submission for a **Staff Product Manager, AI Enablement** role. The assignment asks the candidate to define what it means to be an AI-native PM, design an ecosystem that moves PMs toward effective and responsible AI adoption, identify the hardest and highest-value problem in that journey, build a runnable agent addressing it, and evaluate that agent against a credible baseline.

DecisionLens is the response to the final three parts. [01 — Product Strategy](docs/01-product-strategy.md) is the response to the first two.

---

## The selected problem

The decisions in question are the allocation decisions above, and they are hard to compare because the dimensions that matter are not evidenced equally well or in the same places. Usage and financial data are quantitative and live in systems of record. Strategic importance, strategic alignment, and risk are qualitative and scattered across documents of varying age. Innovation bets suffer most: they compete against core-product work on dimensions where core work will always look stronger — known usage, measurable revenue, named customers — while the evidence that would justify the bet does not exist yet, because that is what makes it a bet. A comparison method that treats *absence of evidence* as *evidence of low value* will systematically defund the innovation horizon.

Most PMs with AI access use it for drafting, summarizing, rewriting, and brainstorming. Far fewer use it for the decisions that determine what actually gets built.

The bet this repository makes is that the boundary is **verification cost**. For a consequential decision, checking AI output can cost more than doing the work unaided. A PM who cannot tell where a claim came from, which conclusions rest on assumption, or what the model quietly left out has not saved any work — they have moved it from analysis into audit, and added the risk of missing something along the way.

This was not the original framing. An earlier version treated weak evidence as the problem, and was challenged on the grounds that weak evidence is a perennial PM-craft issue rather than an AI-adoption issue. [05 — Decision Log](docs/05-decision-log.md) records that change and the others.

## Hypothesis

> **[Hypothesis]** If consequential AI output becomes faster and easier to verify — through source traceability, evidence classification, contradiction detection, missing-evidence identification, explicit alternatives, and transparent uncertainty — then PMs will use AI more responsibly and effectively for higher-value product decisions.

This is a hypothesis, not a finding. It would be challenged if research showed the dominant barriers were tool access, training, workflow integration, policy, data access, model quality, management support, or a lack of relevant use cases — or if evidence-grounded output failed to reduce review effort, improve decision quality, or increase willingness to use AI for consequential work. Falsification conditions are set out in [01 — Product Strategy](docs/01-product-strategy.md).

---

## Problem-first behaviour

DecisionLens starts with a customer, product, business, or operational problem. **It must not assume that AI is the right solution**, that a feature must be built, or that the loudest stakeholder is correct.

It must be able to recommend product or UX change, process change, operational change, training or documentation, rules-based automation, data-quality work, an AI-based solution, build/buy/partner, further research, deferral, or no change at all — and to conclude that an AI solution is not justified.

This is enforced structurally rather than by good intentions: every brief must contain at least one non-AI alternative and at least one no-build, defer, or further-research alternative, and validation checks for both deterministically.

The bundled sample case asks:

> **Which intervention should the team prioritize to reduce delivery exceptions?**

Not *"should we build an AI assistant for delivery exceptions?"* — a question that has already decided the answer.

---

## Planned capabilities

Planned, not yet built:

- One DecisionLens orchestrator running controlled, inspectable stages
- `LocalFileEvidenceSource` over Markdown, text, CSV, and JSON
- Six analysis skills: relevance, classification, contradiction detection, missing-evidence detection, alternative generation, recommendation analysis
- Comparison of opportunities across the decision dimensions above, each carrying its own evidence, confidence, and explicit "cannot be assessed" state
- A recommendation challenger that attacks the draft before a human sees it
- Deterministic validation of citation spans, required sections, and mandatory alternatives
- A synthetic sample case with planted contradictions, gaps, constraints, and misleading evidence
- A strong single-call baseline for comparison
- A vendor-neutral provider boundary with a deterministic cached provider requiring **no API key**
- Structured `DecisionBrief` and `RunTrace` output, with the PM's final decision recorded separately

**Deliberately not built:** one agent per data source, a multi-agent system, a general-purpose PM copilot, a chat interface, a complete enterprise knowledge platform, real Jira/Confluence/Slack/analytics integrations, or a vector database.

---

## Architecture

```
PM problem and desired outcome
        ↓
Structured local interface
        ↓
DecisionLens orchestrator
        ↓
LocalFileEvidenceSource
        ↓
Normalized evidence
        ↓
Evidence-analysis skills
        ↓
Decision-analysis skills
        ↓
Recommendation challenger
        ↓
Validation and guardrails
        ↓
Decision brief + run trace
        ↓
PM final decision
```

**Connectors retrieve. Skills interpret. DecisionLens orchestrates. The PM decides.**

Enterprise connectors — Jira, Confluence, product metrics, customer feedback, support tickets, OKRs, experiment results, governance policy, prior decisions — are **documented, not implemented**. See [03 — Architecture and Governance](docs/03-architecture-and-governance.md).

---

## Setup

Requires Python 3.11 or newer.

```bash
make setup     # create .venv and install with dev dependencies
make lint      # ruff check + format check
make typecheck # mypy
make test      # pytest
```

Or without make:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

No API key is required. Copy `.env.example` to `.env` only if you intend to run live model comparisons in a later phase; the demo path is deterministic and offline.

---

## Repository map

```
decisionlens-ai/
├── app/          Streamlit interface            (Phase 9)
├── data/         synthetic evidence corpus      (Phase 4)
├── docs/         product strategy and reasoning (01 and 05 complete)
├── evals/        cases, ground truth, results   (Phases 4, 10)
├── src/
│   └── decision_lens/
│       ├── connectors/   evidence retrieval     (Phases 2-3)
│       ├── skills/       evidence analysis      (Phase 7)
│       ├── llm/          provider boundary      (Phases 5-6)
│       └── prompts/      versioned prompts      (Phases 6-8)
└── tests/                                       (Phase 2 onward)
```

## Documentation

| Document | Contents | State |
|---|---|---|
| [01 — Product Strategy](docs/01-product-strategy.md) | AI-native PM definition, problem selection, alternatives considered, hypothesis and falsifiability, scope, metrics, assumptions | Complete |
| [02 — Ecosystem and Adoption](docs/02-ecosystem-and-adoption.md) | Maturity stages, tooling, skills, connectors, configuration layers, training, measurement | Outline (Phase 11) |
| [03 — Architecture and Governance](docs/03-architecture-and-governance.md) | Prototype and enterprise architecture, connector model, permissions, governance, observability | Outline (Phase 11) |
| [04 — Evaluation](docs/04-evaluation.md) | Baseline, test cases, ground truth, metrics, results, failures, real-PM study | Outline (Phase 10) |
| [05 — Decision Log](docs/05-decision-log.md) | How the framing evolved, what was rejected, how AI was used to build this | Complete |

---

## Limitations

- The prototype is not yet runnable. See *Current status*.
- All evidence is synthetic and authored by one person, who also authored the ground truth used to evaluate against it.
- No research with real product managers has been conducted. The study design in [04](docs/04-evaluation.md) is a proposal.
- Traceability over an incomplete corpus still yields confident, well-cited, badly scoped conclusions. The missing-evidence skill partially compensates by making gaps visible, but it does not solve this.
- Support labels ("low / moderate / strong") are qualitative judgments. They are **not** calibrated probabilities and must not be read as such.

---

## Synthetic data and accountability

> **All sample evidence in this repository is synthetic and fictional. No real Walmart data is used.**
>
> This repository claims no access to Walmart internal systems, and no such access was used at any point. Enterprise connectors are described as future work only.

> **DecisionLens supports the decision process. The product manager remains accountable for the final decision.**
>
> DecisionLens does not own decisions, approve investments, make roadmap commitments, replace PM judgment, or guarantee that its source material is true. The PM's final decision and rationale are recorded separately from the agent's recommendation.

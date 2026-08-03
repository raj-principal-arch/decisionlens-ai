# DecisionLens — submission summary

**Staff Product Manager, AI Enablement.** This document answers the five questions in the
brief directly. Everything asserted here is expanded in the linked documents, and every
number comes from `make eval` over recorded runs in `evals/recordings/`.

> All evidence in this repository is synthetic and fictional. No real Walmart data is used
> and no access to any Walmart system is claimed.

**Run it:** `make setup && make demo` — no API key, no network.

---

## The one-paragraph version

Most PMs use AI heavily for drafting and barely for decisions. The bet this submission
makes is that the boundary is **verification cost**: for a consequential decision, checking
AI output can cost more than doing the work unaided. DecisionLens is an evidence-grounded
decision agent built to make that check cheap — every claim anchored to a retrievable span,
contradictions surfaced rather than smoothed, missing evidence named, non-AI and no-build
alternatives mandatory, and a challenger that attacks the draft before a human sees it.
Measured against a strong single-call baseline across eleven cases, it never overclaims
confidence, grounds half again as many claims at equal accuracy, and surfaces 70% more
options — while under-claiming confidence more often than the baseline, which is a real
weakness reported here rather than buried.

---

## The five questions, answered

**1. What does it mean to be an AI-native PM?** A PM who designs the work for AI first and
keeps only the part that needs a human. Most do the reverse — they work the way they always
have, then look for a step to speed up, which produces the same decision in less time. The
AI-native version gives each part to whatever does it best: AI reads more than a person can
hold and recalls all of it, data records what happened rather than what people remember, and
the human supplies context, judgment and accountability. That makes AI a partner you brief
and hold to account, not a tool you invoke. Three things change. The limit on a decision
stops being how much evidence you can read and becomes how well you can question it. The
reasoning outlives the deck, so teams stop re-litigating decisions from memory. And you make
fewer confidently wrong bets, and catch the wrong ones sooner. What blocks all of it is that
checking AI's work currently costs more than doing the work yourself.

**2. What ecosystem moves PMs from little AI use to responsible adoption?** Five decisions,
and only the first is built here. Give PMs one good tool for one high-consequence job rather
than a general assistant that does everything adequately. Centralise the plumbing — the
company connects to each data source once, and PMs never hold credentials or configure APIs.
Treat analysis skills as shared, versioned assets with content fingerprints, so an
improvement reaches everyone instead of living in one person's notes. Teach evidence
interrogation rather than prompt technique, because prompt skill belongs to a tool
generation and evidence skill does not. And measure whether decisions improved, not how many
people used the tool: usage rises when a tool is used badly, and cannot distinguish a PM who
checked the output from one who pasted it into a deck.

**3. What is the hardest and highest-value problem?** Verification cost. A PM reading an
AI-written recommendation has to establish where each number came from, which conclusions
rest on assumption, and what was left out — and answering that takes longer than the AI
saved. The work moves from thinking to auditing, so PMs use AI for drafts and avoid it for
decisions, which is the pattern actually observed. Alternatives were considered and
rejected: a broad AI workflow coach has no falsifiable hypothesis and no boundary against a
general assistant; prompt libraries treat the barrier as skill, and if the barrier is
verification cost then better prompts simply produce more unverifiable output; faster
document generation is what the brief explicitly excludes. The original framing — that PMs
have weak evidence — was itself rejected, because weak evidence is a perennial PM-craft
problem rather than an AI-adoption one.

**4. What was built?** DecisionLens, a runnable agent — `make demo`, no API key, no network.
It takes a folder of evidence and a problem-first question, and returns a recommendation in
which every claim carries a quote you can find in the source, contradictions are surfaced
with what would settle them rather than silently resolved, and missing evidence is named
because absence is decision-relevant. Every brief must contain a non-AI option and a
no-build option, enforced in code rather than requested in a prompt. A challenger puts fixed
questions to the draft before a human sees it and can only lower confidence, never raise it.
It is deliberately one orchestrator running seven inspectable stages rather than a
multi-agent system, because a PM who cannot follow what the tool did cannot verify it, and
verification is the entire thesis.

**5. Does it work?** Measured across eleven synthetic cases against a strong single-call
baseline given the same model, the same evidence and the same briefing. It never overstated
its confidence — zero cases of eleven against one for the baseline, and that one failure
came on the case built so a thick corpus contains almost no real evidence, which is exactly
the trap the product exists to catch. It grounded half again as many claims at equal
accuracy and surfaced 134 options against 79. Against that: it under-claims confidence on
six of eleven cases, so it is systematically cautious rather than well-calibrated; it costs
3.2 times more to run; and citation accuracy, expected to be the central advantage, was 100%
against 99.8% and is therefore not a differentiator. The recall margin is four graded items
out of fifty from a single run per case, so the honest claim is that DecisionLens did not
lose rather than that it reliably wins. No research with real product managers was
conducted; that study is designed, not run.

---

## 1. What it means to be an AI-native PM

An AI-native PM designs the work for AI first, then keeps what only a human can do.

Most PMs do the reverse. They finish a task the way they always have, then look for a step
AI can speed up. That produces a faster document and the same decision.

Start from the strengths instead. AI reads more than a person can hold and recalls all of
it. Data records what happened, not what people remember. The PM supplies context, judgment
and accountability. Assign each the part it is best at. **[Product judgment]**

This makes AI a partner rather than a tool. A tool is invoked. A partner is briefed,
delegated to, argued with, and held to account. A PM who pastes a question into a chat
window has used a tool. A PM who states the decision, the constraints, and what would make
the answer wrong has briefed a partner.

Three things change.

**Product decisions.** The binding constraint moves from how much evidence a PM can read to
how well they can interrogate it. An eighteen-month-old research deck now costs nothing to
include. "What would make this wrong?" becomes routine rather than unusual discipline. The
no-build option gets argued every time, because a system can be required to produce it and
a person under deadline will not.

**Team effectiveness.** Reasoning outlives the deck. A new joiner reconstructs a decision
from its evidence instead of asking who was in the room. Disagreement moves from "I think
X" to "the brief cites Y, and Y is wrong because Z." A reversal becomes legible: a decision
that was right on the evidence then available is a different event from one that was always
poorly reasoned.

**Business outcomes.** Fewer confidently wrong investments, and the wrong ones found
earlier. These are measurable. They are **not measured here** — execution, market timing
and luck sit between a decision and a result, and the lag exceeds this exercise.
**[Observation]**

One condition decides whether any of it happens. Checking AI output must cost less than
doing the work unaided. Today it does not, which is why PMs use AI for drafts and not for
decisions. That is the problem this submission takes on, and question 3 explains why it was
chosen over the alternatives.

→ [01 — Product Strategy](01-product-strategy.md)

---

## 2. The ecosystem

Moving PMs from little AI use to effective, responsible adoption. **Only DecisionLens is
built; everything else here is a design and is labelled as such.**

| Layer | The decision |
|---|---|
| **Maturity model** | Five stages with observable behaviours, not adjectives. What you would actually see a PM doing at each one. |
| **Tooling** | Deliberately *not* a general-purpose copilot. A narrow, inspectable tool for one high-consequence job. |
| **Model gateway** | Centralised access: vendor neutrality, cost control, version pinning, logging. Individual teams do not hold provider credentials. |
| **Reusable skills** | Analysis skills as versioned, independently testable organisational assets with content fingerprints — not prompts pasted between teams. |
| **Connectors** | One per source, shared, retrieval-only. Never one connector per PM. Connectors retrieve; skills interpret. |
| **Configuration** | Three layers: enterprise (credentials, security), team (sources, terminology, governance), PM runtime (question, scope). PMs never configure credentials. |
| **Training** | PMs should **not** have to learn prompt technique. They learn evidence interrogation. |
| **Governance** | Security, compliance and contractual work are priority exceptions that *constrain* the decision — never options ranked against growth work. |
| **Measurement** | Leading indicators measured here; lagging outcomes (revenue, retention) stated as **not demonstrable in a take-home**. |

**Why raw usage volume is the wrong headline metric:** it rises when a tool is used badly,
it rises when a tool is used for low-stakes work it was not built for, and it cannot
distinguish a PM who checked the output from one who pasted it into a deck.

→ [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)

---

## 3. The hardest, highest-value problem

**Verification cost at the boundary of consequence.**

A PM who cannot tell where a claim came from, which conclusions rest on assumption, or what
the model quietly left out has not saved any work. They have moved it from analysis into
audit, and added the risk of missing something on the way.

### Alternatives considered, and why they lost

| Considered | Rejected because |
|---|---|
| Broad AI workflow coach | No falsifiable hypothesis, no boundary against a general assistant. A tool that helps with everything can be evaluated on nothing. |
| Prompt libraries and training | Treats the barrier as skill. If the barrier is verification cost, better prompts produce more output nobody can check. |
| Faster document generation | The thing the brief explicitly excludes, and the thing PMs already do. |
| "PMs have weak evidence" | **The original framing, and it was wrong.** Weak evidence is a perennial PM-craft problem, not an AI-adoption problem. An AI-enablement assignment needs a problem that is specifically about AI adoption. Changing this was the single most consequential decision in the project — recorded as D3/D4. |

### Why this one

It explains the observed pattern (heavy AI use for drafting, light use for decisions) as a
consequence of verification cost rather than of tool access or skill. It is falsifiable. And
it is demonstrable in a prototype, which most enablement problems are not.

→ [01 — Product Strategy](01-product-strategy.md) · [05 — Decision Log](05-decision-log.md)

---

## 4. The agent

```bash
make setup && make demo     # no API key, no network
```

One orchestrator running seven inspectable stages. **Not** a multi-agent system, not a
chatbot — deliberately, because a PM who cannot follow what the tool did cannot verify it,
and verification is the entire product thesis.

| | |
|---|---|
| **Retrieval** | `LocalFileEvidenceSource` over Markdown, CSV, JSON. Connectors retrieve; they never interpret. |
| **Seven stages** | relevance → classification → contradictions → missing evidence → alternatives → recommendation → challenger |
| **The challenger** | Puts eight fixed questions to the draft before a human sees it. **Can only lower confidence, never raise it.** |
| **Deterministic validation** | Citation spans checked programmatically against source text. Required sections, non-AI and no-build options enforced in code — not by asking the model nicely. |
| **Audit trace** | Provider, model, prompt version **and content fingerprint** per stage, so a brief can be checked against the text that produced it. |
| **Provider boundary** | Vendor-neutral. The demo replays recorded responses; no key required. |

**What it looks like when it works.** `make demo` currently produces a brief that **blocks
itself**: the challenger caught the recommendation claiming "multiple comments describe
entering the unit number at checkout" when exactly one of the three cited rows mentions
checkout. Verified by hand — the challenger is right.

That error is left standing. Removing it would mean weakening the check or re-running until
the output flattered us, which is the habit this product argues against.

→ [03 — Architecture and Governance](03-architecture-and-governance.md)

---

## 5. The evaluation

**Eleven cases, both arms, one live run each against `claude-opus-5`.** 88 recorded stages.
The baseline is a strong single call — same model, same evidence, same output schema, and
briefed from the *same shared heuristics module*, so the comparison is about workflow rather
than about who was told more.

| Metric | DecisionLens | Baseline |
|---|---|---|
| Contradiction recall | **36/50 (72.0%)** | 32/50 (64.0%) |
| — held out from prompt design | **32/46 (69.6%)** | 28/46 (60.9%) |
| Citation validity | 1451/1451 (100%) | 967/969 (99.8%) |
| Options generated | **134** | 79 |
| **Overstates support** | **0/11** | 1/11 |
| Understates support | 6/11 | 1/11 |
| Cost | **3.2× the baseline** | — |

### What holds

**It never overclaims.** Zero of eleven. The baseline's single failure is the most
diagnostic result in the set: it occurred on `returns_fraud_signals`, a case built so that a
thick corpus contains almost no load-bearing evidence — a finance estimate with no method,
two self-selected anecdotes, a vendor deck, and a field that was added and never populated.
The defensible ceiling is `low`. The baseline read the volume and said `moderate`.
DecisionLens said `low`. **That is the failure this product exists to prevent, reproduced
under measurement.**

**It grounds more without grounding worse** — 1,451 citations against 969, at equal validity.

### What does not

**Caution is not calibration.** DecisionLens under-claims on 6 of 11 cases; the baseline on
1. On `checkout_error_rate` — built so `strong` support is genuinely earned by a
pre-registered randomised experiment with n=412,905 — **both arms said `moderate`**. This is
a system biased low, not one that judges confidence well. It happens to be the safer
direction.

**Citation validity is not a differentiator.** 100% against 99.8% is not a distinction. A
well-prompted single call grounds its claims essentially as reliably. This was expected to
be a central advantage and the measurement says it is not one.

**The margin is small.** Eight points on contradiction recall is four items out of fifty,
from one run per case with no variance measurement. The honest statement is that
DecisionLens **did not lose**, and led on a small sample by a margin not shown to be
reproducible. The restraint result is stronger because it is a mechanism on a case designed
to induce the failure, not an average.

**It costs 3.2× more.** On this evidence, that is not yet justified by recall alone.

### Testing with real PMs

**Not conducted.** [04](04-evaluation.md) §11 proposes the design: decision-quality rating,
verification time, unsupported claims found, alternatives considered, whether the PM changed
the decision, and continued use over time — with leading indicators measurable in a short
study and lagging outcomes requiring a real pilot across multiple decision cycles.

→ [04 — Evaluation](04-evaluation.md) · raw results in `evals/results/`

---

## What this submission does not claim

Stated here rather than left to be discovered:

- **No real PM research was conducted.** The study is a design.
- **All evidence is synthetic**, authored by one person who also authored the answer keys.
- **One of eleven cases is in-sample** — the prompts were written after it. The other ten
  were written after the prompts were frozen at a recorded commit, which is checkable but
  weaker than a genuine held-out set.
- **One run per case.** No variance measurement, so no margin here has an error bar.
- **Enterprise connectors are documented, not implemented.** There is no identity model, no
  permission delegation, no cost control, and no red-teaming in the prototype.
- **Lagging business outcomes cannot be demonstrated** in a take-home and are not claimed.

---

## Repository

| Path | |
|---|---|
| `make demo` | Produce a brief from the bundled case, offline |
| `make ui` | The same thing in a browser |
| `make check` | Lint, typecheck, 988 tests, 100% coverage |
| `make eval` | Re-score every case from the recordings |
| `data/` | Eleven synthetic cases |
| `evals/` | Answer keys, recordings, results, audit record |
| `docs/` | The five documents linked above |

**Engineering:** Python 3.11+, Pydantic v2, `mypy --strict`, 988 tests at 100% line
coverage. Every recorded response carries the model and date it came from; nothing in the
cache is hand-written.

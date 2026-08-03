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

## 1. What it means to be an AI-native PM

**Not someone who uses AI to produce documents faster.** Someone who can *verify*
consequential AI output cheaply enough to rely on it.

The distinction that carries the work is between two words:

| | |
|---|---|
| *Evidence-based* | A posture. Anyone can claim it. Unfalsifiable. |
| **Evidence-grounded** | A mechanical property. Every claim anchored to a retrievable source span that can be checked — programmatically. |

An AI-native PM works in the second mode. Concretely, they:

- Ask what the evidence **does not** say, and treat absence as decision-relevant rather than as a reason to proceed
- Distinguish a measurement from a stakeholder's recollection of a measurement
- Expect contradictions to be surfaced, not resolved on their behalf
- Read a confidence level as a claim that must itself be supported
- Own the decision. The tool recommends; the PM decides, and the two are recorded separately

**How this improves outcomes, beyond speed.** Faster document creation compounds nothing —
a wrong decision written quickly is still wrong. Verifiable output changes three things:
*decision quality*, because unsupported claims and missing evidence become visible before
the decision rather than after it; *team effectiveness*, because a brief whose provenance
anyone can check removes the review bottleneck of "how do you know that?"; and *business
outcomes*, because the failure this addresses — confidently defunding an option on evidence
that does not support the confidence — is expensive and invisible.

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

# DecisionLens — submission summary

**Staff Product Manager, AI Enablement.** This document answers the five questions in the
brief directly. Everything asserted here is expanded in the linked documents, and every
number comes from `make eval` over recorded runs in `evals/recordings/`.

> All evidence in this repository is synthetic and fictional. No real Walmart data is used
> and no access to any Walmart system is claimed.

**Run it:** `make setup && make demo` — no API key, no network.

---

## 1. What does it mean to be an AI-native PM?

An AI-native PM designs the work for AI first and keeps only the part that genuinely needs a human. Most do the reverse: they work as they always have, then hunt for a step to accelerate — which just produces the same decision faster. Being AI-native is an act of allocation, not automation. You assign each part of the job to whatever does it best: AI reads more than any person can hold and recalls all of it; data captures what actually happened, not what people remember; and the human contributes context, judgment, and accountability. That reframes AI from a tool you invoke into a thought partner you brief and hold to account — the same shift now reshaping how software gets built and how orgs make decisions.

Three things change:

* **The binding constraint moves.** A decision is no longer limited by how much evidence you can read, but by how sharply you can interrogate it. The scarce skill becomes asking the right questions, not gathering the inputs.
* **The reasoning outlives the artifact.** Decisions no longer live and die with a deck; the rationale persists, so teams stop re-litigating settled calls from memory.
* **The error curve improves.** You make fewer confidently wrong bets — and you catch the wrong ones sooner.

> **In this repository.** The third point is the only one measured: DecisionLens overclaims
> its confidence on **0 of 11** cases against the baseline's 1. Business outcomes are **not**
> measured — execution, market timing and luck sit between a decision and a result, and the
> lag exceeds this exercise.
>
> → [01 — Product Strategy](01-product-strategy.md)

---

## 2. What ecosystem moves PMs from little AI use to responsible adoption?

Adoption doesn't fail on enthusiasm — it fails on the absence of scaffolding. Left alone, most PMs land in the same place: a few personal prompts that save minutes but change nothing about how decisions get made. Moving an organization from novelty to responsible adoption isn't a tool rollout; it's an ecosystem — eight pieces that have to reinforce each other.

* **Tools that meet PMs in the work.** AI has to live inside the docs, tickets, and reviews PMs already run — not in a separate tab they have to remember to visit. Adoption tracks convenience; the winning pattern is embedded assistance, not a destination app.
* **Agents that own recurring jobs.** The leap past prompting is delegation: agents that run standing tasks — triaging feedback, drafting narratives, monitoring launches — and report back. The PM shifts from operator to orchestrator, briefing agents and holding them to account.
* **Reusable skills, not one-off prompts.** Value only compounds when good prompting is captured as shared, versioned skills the whole org can invoke. This is the difference between 500 PMs re-inventing the same prompt and one proven pattern propagating instantly — the Learn → Build → Certify muscle applied to artifacts, not just people.
* **Data and knowledge as shared ground truth.** Agents are only as good as what they can reach. Grounding AI in the org's own data and decisions — retrieval-backed, not memory-primed — is what makes output trustworthy and institutional rather than private. This is the real payoff of the shift toward grounded, agentic systems: context becomes a shared asset.
* **Governance that enables rather than gates.** Responsible adoption needs guardrails PMs can move within — clear rules on data boundaries, human-in-the-loop decisions, and accountability for AI-assisted calls. Done well, governance is what gives PMs the confidence to use AI on real decisions, not a brake on it.
* **Training as a progression, not an event.** Access alone produces dabblers. A Learn → Build → Certify path turns curiosity into demonstrated capability — people learn the primitives, ship something real, and get recognized against a standard, not for attendance.
* **Measurement that proves trust, not just usage.** The metric that matters isn't seat activation; it's whether AI-assisted decisions hold up. Evals — not vibes — are what let a PM defend an AI-assisted call to a room, and what separate scale from risk. Pair adoption metrics with quality evals or you're measuring motion, not progress.
* **Proof and peer pull that make it social.** Champions, visible wins, and a living playbook create permission. People adopt what credible peers already trust — recognition and a reusable pattern travel faster than any mandate.

The through-line: you don't move PMs by giving them AI. You build the surround — embedded tools and agents to do the work, reusable skills and shared data so it compounds, governance and evals so it's trusted, training and proof so it spreads — and let capability, not compliance, carry the rest.

> **In this repository.** Only DecisionLens is built; everything above is a design and is
> labelled as such. [02](02-ecosystem-and-adoption.md) adds two operating positions: a team
> may **fork a shared skill and upstream it** if their variant beats the incumbent on the eval
> harness — without that route back you are asking teams to accept a worse answer for the sake
> of consistency, and they will not. And **raw usage volume is a vanity metric**: it rises when
> a tool is misused, and cannot distinguish a PM who verified the output from one who pasted
> it into a deck.
>
> → [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)

---

## 3. What is the hardest and highest-value problem?

Every element in the ecosystem matters, but they are not equally hard, and they do not gate each other equally. The sharp question isn't "what's missing?" — it's which problem, left unsolved, makes every other investment fail to compound?

The candidates I weighed:

* **Access and tooling.** The most visible gap — and the easiest to solve, least differentiating. Give everyone tools and you get dabblers. Necessary, not sufficient.
* **Training and certification.** Real capability, but it scales individuals. Certify 500 PMs and you still have 500 people re-inventing the same prompts in private.
* **Governance.** Genuinely hard, severe failure mode — but it's a constraint function. Solve it perfectly and you've made AI safe to use, not worth using.
* **Shared context** — grounding AI in the org's own data, knowledge, and reusable skills. Powerful, because it's the one element with compounding returns: every decision captured and skill published raises the baseline for everyone at once. This was my first instinct.
* **Redesigning the PM's core decision** — "what to build" — and the trust that decision carries. This is the one I chose.

**Why "what to build" beats even shared context:**

Shared context is the highest-value enabler — but it's still infrastructure in service of a decision. The decision it serves is the PM's actual job: what to build, for whom, and why now. Every other element — tools, agents, skills, data, governance, training — exists to make that judgment better. So the hardest, highest-value problem isn't feeding the decision; it's transforming the decision itself, and earning trust in it.

This is the problem because it strikes at the fundamental role function, not the workflow around it. Automating a PM's tasks produces the same "what to build" call, faster. The AI-native move is different: AI can now hold more evidence, surface more options, and pressure-test a bet than any PM could alone — which means the constraint on "what to build" shifts from how much can I analyze to how well can I decide under a machine that argues back. That is a redefinition of the role, not an acceleration of it.

And it's the hardest because the blocker is trust, not capability. A PM can get an AI-generated recommendation today; what they can't easily get is the confidence to stake a roadmap on it in front of leadership. Trust is the true bottleneck — and it's why this problem requires the rest of the ecosystem to exist: grounding makes the reasoning inspectable, evals make quality provable, governance makes accountability clear. Those elements aren't parallel alternatives to this problem; they are the machinery that makes a redesigned decision trustworthy. That's the tell that this is the root problem — everything else is a precondition for solving it.

The reasoning behind the choice: Access, training, and governance change the level of capability. Shared context changes the slope — it compounds. But redesigning "what to build" changes the thing being decided — and improving a decision the whole org bets on dominates improving any input to it. Solve the plumbing and decisions get better inputs; solve the decision and the entire role — and everything the org builds — moves.

> **In this repository.** Trust has a concrete price, and it is what the prototype attacks:
> **verification cost at the boundary of consequence.** A PM who cannot tell where a claim came
> from, which conclusions rest on assumption, or what the model left out has not saved work —
> they have moved it from analysis into audit. That explains the observed pattern: heavy AI use
> for drafting, light use for decisions.
>
> **One framing I rejected was my own.** This project began as *"PMs have weak evidence."* That
> was wrong — weak evidence is a perennial PM-craft problem, not an AI-adoption one. Changing
> it was the most consequential decision in the project, recorded as **D3/D4**.
>
> → [01 — Product Strategy](01-product-strategy.md) · [05 — Decision Log](05-decision-log.md)

---

## 4. The agent I'd build — and why it's the one that solves the problem

If the problem is transforming the "what to build" decision and earning trust in it, then the agent can't be a research assistant that produces a better memo. A better memo still leaves the PM staking a roadmap on a black box. The agent has to attack trust directly — which means it must argue, show its work, and be pressure-tested, not just be right.

I'd build an adversarial decision partner for "what to build" — a Bet Examiner. Not a tool that recommends what to build, but an agent that interrogates the bet you're about to make and produces an inspectable, defensible decision record.

What it does — the loop that builds trust:

* **Frames the bet.** You state the call ("build X for segment Y because Z"). The agent structures it into an explicit hypothesis: the customer, the problem, the assumed value, and the evidence you're leaning on.
* **Grounds it.** It pulls from the org's own context — tickets, research, usage data, prior decisions — and separates what's evidenced from what you're assuming. This is where shared context earns its keep: the agent is only trustworthy because it's grounded, not memory-primed.
* **Argues back.** It runs the steel-manned counter-case: the strongest reason this is the wrong bet, the segment you're overweighting, the disconfirming data you skipped. This is the AI-native move made concrete — a machine that argues back, so the constraint becomes how well you answer, not how much you read.
* **Scores its own confidence — with evals.** Every claim carries a graded confidence and a source. The agent runs evals on its own reasoning so its output isn't vibes — it's a quality signal a PM can defend in a room.
* **Emits a decision record.** The durable artifact: the bet, the evidence, the counter-case, the open risks, and the rationale — so the reasoning outlives the deck and the team stops re-litigating from memory.

Why this shape, and why it's runnable:

* **Interface:** a chat-first agent that produces a structured decision doc — meets PMs in the work (docs and reviews), not a separate destination.
* **Models:** a strong reasoning model for the argue-back and synthesis; a cheaper model for retrieval and extraction — the confidence scoring and adversarial critique are where reasoning quality actually pays off.
* **Tools:** retrieval over the org's corpus, a structured "decision record" writer, and an eval harness that grades the agent's own claims against sources.
* **Data:** the org's tickets, research notes, usage metrics, and past decision records — grounding is the whole point.

The prototype is deliberately small: it doesn't need hosting to prove the thesis. A local, runnable version — retrieval over a seed corpus, a reasoning model doing frame → ground → argue → score, emitting a decision record — is enough to demonstrate the one thing that matters: a PM leaves the loop trusting the decision more, with the reasoning to defend it. That's the whole bet.

### What runs today

```bash
make setup && make demo     # no API key, no network, 0.15 seconds
```

DecisionLens implements that loop as **one orchestrator running seven inspectable stages** —
relevance → classification → contradictions → missing evidence → alternatives →
recommendation → challenger. Not a multi-agent system, deliberately: a PM who cannot follow
what the tool did cannot verify it (**D8**).

| The loop | What runs |
|---|---|
| Frames the bet | A decision question, desired outcome and criteria over a defined evidence scope |
| Grounds it | ~57 addressable evidence records per case. Connectors **retrieve; never interpret.** Every statement classified fact, assumption, opinion or constraint |
| Argues back | Contradictions surfaced *with what would settle them*; missing evidence named; then a **challenger** runs eight fixed attacks and **can only lower confidence, never raise it** |
| Scores its confidence | Citations checked programmatically against source text; confidence compared against what the evidence carries; eval harness in [04](04-evaluation.md) |
| Emits a decision record | Markdown brief and JSON artifact, plus a run trace pinning provider, model, prompt version **and content fingerprint** per stage. The PM's decision is recorded **separately** from the recommendation |

**The guarantees are code, not prompting.** Citation spans are matched against source text; a
non-AI option and a no-build option are *enforced*, not requested. Asking a model nicely for a
no-build option is a hope; rejecting the brief when it is missing is a guarantee.

**Two deviations from the design above, both deliberate:**

- **The interface is a structured form today, with chat on the roadmap.** The brief has to be
  scanned by a sceptic — checks before the answer, a stable place for evidence, a visible
  record of what was left out. Chat is the wrong shape for *verification*; it is the right
  shape for framing and follow-up, which is where it lands next over the same validated
  pipeline.
- **One model, not two tiers.** `claude-opus-5` throughout, behind a vendor-neutral
  `ModelProvider` boundary with two interchangeable implementations — cached replay and a live
  Anthropic adapter — that the orchestrator cannot tell apart. Splitting tiers is a cost
  optimisation worth measuring, not assuming.

**What it looks like when it works.** `make demo` produces a brief that **blocks itself**: the
challenger caught the recommendation claiming *"multiple comments describe entering the unit
number at checkout"* when exactly one of three cited rows mentions checkout. Verified by
hand — the challenger is right. That error is left standing. Removing it would mean weakening
the check or re-running until the output flattered us, which is the habit this product argues
against.

→ [03 — Architecture and Governance](03-architecture-and-governance.md)

---

## 5. Does it work?

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

**It never overclaims.** Zero of eleven. The baseline's single failure is the most diagnostic
result in the set: it occurred on `returns_fraud_signals`, a case built so that a thick corpus
contains almost no load-bearing evidence — a finance estimate with no method, two
self-selected anecdotes, a vendor deck, and a field that was added and never populated. The
defensible ceiling is `low`. The baseline read the volume and said `moderate`. DecisionLens
said `low`. **That is the failure this product exists to prevent, reproduced under
measurement.**

**It grounds more without grounding worse** — 1,451 citations against 969, at equal validity.

### What does not

**Caution is not calibration.** DecisionLens under-claims on 6 of 11 cases; the baseline on 1.
On `checkout_error_rate` — built so `strong` support is genuinely earned by a pre-registered
randomised experiment with n=412,905 — **both arms said `moderate`**. This is a system biased
low, not one that judges confidence well. It happens to be the safer direction.

**Citation validity is not a differentiator.** 100% against 99.8% is not a distinction. A
well-prompted single call grounds its claims essentially as reliably. This was expected to be
a central advantage and the measurement says it is not one.

**The margin is small.** Eight points on contradiction recall is four items out of fifty, from
one run per case with no variance measurement. The honest statement is that DecisionLens **did
not lose**, and led on a small sample by a margin not shown to be reproducible. The restraint
result is stronger because it is a mechanism on a case designed to induce the failure, not an
average.

**It costs 3.2× more.** On this evidence, that is not yet justified by recall alone.

**And the baseline won twice**, including 2/4 against 4/4 on `checkout_error_rate`.

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
- **One run per case.** No variance measurement, so no margin here has an error bar. One case
  was recorded twice by accident, and the two runs differ by four contradictions — the same
  size as the headline margin. Reported in [04](04-evaluation.md) §6.
- **Enterprise connectors are documented, not implemented.** There is no identity model, no
  permission delegation, no cost control, and no red-teaming in the prototype.
- **Lagging business outcomes cannot be demonstrated** in a take-home and are not claimed.

---

## Repository

| Path | |
|---|---|
| `make demo` | Produce a brief from the bundled case, offline |
| `make ui` | The same thing in a browser |
| `make check` | Lint, typecheck, the full suite at 100% line coverage |
| `make eval` | Re-score every case from the recordings |
| `data/` | Eleven synthetic cases |
| `evals/` | Answer keys, recordings, results, audit record |
| `docs/` | The five documents linked above |

**Engineering:** Python 3.11+, Pydantic v2, `mypy --strict`, 1,010 tests at 100% line
coverage — the coverage gate is what is enforced; the count is whatever it is on the day.
Every recorded response carries the model and date it came from; nothing in the cache is
hand-written.

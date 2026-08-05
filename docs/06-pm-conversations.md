# 06 — PM Conversations

> **STATUS: ONE OF THREE RESPONDED.**
>
> Three product managers were contacted. One replied; two had not by the submission date.
> **n=1 is an anecdote, not research**, and nothing here is presented as a finding about
> product managers generally. What it is: one real practitioner's answers, recorded verbatim,
> including the parts that cut against this submission's thesis.
>
> The single response **supports the verification behaviour and undercuts the verification
> barrier** — and names a barrier this study did not anticipate. See the analysis under
> PM 1 and the synthesis below. [Assumption #1](01-product-strategy.md) is qualified as a
> result, not confirmed.

**Method.** Informal conversations with **3 product managers**, conducted over text. This is **not research** — n=3, self-selected, no controls, conducted by the person whose hypothesis it tests. It is reported as what it is: a sanity check on [Assumption #1](01-product-strategy.md) in the product strategy.

**Purpose.** [docs/01](01-product-strategy.md) currently rests on an unvalidated claim: that PMs find consequential AI output expensive to verify, and that this is what stops them using AI for decisions that matter. Public survey data supports the general shape but says nothing about PMs specifically. These conversations test whether the claim survives contact with three real ones.

---

## Rules

1. **Never use the word "verification" until they do.** If it comes up unprompted in Q1–Q3, that is the signal. If you introduce it, the answer is contaminated.
2. **Never ask "would citations help you trust AI more?"** Everyone says yes. The answer is worthless.
3. **Record their words, not your summary.** A verbatim quote is evidence; a paraphrase is interpretation.
4. **A disconfirming answer is a good outcome.** If verification does not come up, that is reported and Assumption #1 is weakened — not quietly rephrased.

---

## Opening message

Copy-paste as-is:

> Hey — doing a product exercise on how PMs actually use AI at work. Could I ask you 3–4 quick questions over text? No right answers, and honestly the unhelpful answers are the useful ones. Should take 10 minutes, whenever suits.

---

## The questions

Send **one at a time** and wait for the reply. Texting all five at once gets you five one-line answers and no follow-up.

**Q1.** Last time you used AI for something that actually mattered at work — what was it, and what did you do with what it gave you?

**Q2.** Has there been a time you decided *not* to use AI for something? What was that about?

**Q3.** When AI gives you an answer you'd act on, what do you do before you act on it?

**Q4.** What would have to change for you to use it on a prioritization or investment call?

**Q5.** Anything about using it at work that worries you that we haven't covered?

**Follow-ups.** On Q2 and Q3, "why?" once or twice. That is where the real barrier lives. Over text, a good follow-up is: *"Interesting — what made you land there?"*

---

## What to listen for

| Response pattern | Reading |
|---|---|
| "I'd have to check all of it anyway" | Supports Assumption #1 |
| "I don't know where it got that from" | Supports Assumption #1 |
| "My director would ask how I know" | Accountability risk, not cognitive cost — would need a framing change in §01 |
| "I can't put that data into it" | Policy / data barrier — competing diagnosis |
| "I just don't think to use it for that" | Use-case discovery — competing diagnosis |
| "It's not good enough yet" | Model quality — competing diagnosis |

The bottom four would each weaken the selected problem. Record them plainly if they occur.

---

## Findings

**One of three responded. Answers below are verbatim.** PM 2 and PM 3 remain empty and are
not filled with anything.

### PM 1

- **Role / context:** Product leader, enterprise software. Heavy daily AI user. Known to the
  author, so self-selected in the direction of AI enthusiasm — the least likely respondent to
  report AI as unusable.

- **Q1 — last time you used AI for something that mattered:**
  > "Every day: product strategy, market research, design, prototyping and mockups"

- **Q2 — a time you decided *not* to use AI:**
  > "Only in cases where I am looking to engage with human to collect feedback. Voice of the
  > customer is key for me as PM, analyst feedback is also a good example where engage with
  > people and not agents"

- **Q3 — what you do before acting on an answer you'd act on:**
  > "I validate, I inspect and I criticise. I'm not taking anything for granted and I also
  > coach my teams to do the same when they generate code, docs, presentations and anything
  > else"

- **Q4 — what would have to change to use it on a prioritization or investment call:**
  > "Having the right reasoning in a fast and effective way (mimic the way I prioritize
  > today)."

- **Q5 — anything that worries you:**
  > "Always focus on outcomes. You can't use AI for the sake of using AI — there must be a
  > merit/benefit. Speed, cost, efficiency, risk reduction. If one of those is not realized —
  > then we're missing the entire point of using AI and replace one problem with another."

- **Did verification come up unprompted?** **Yes, at Q3** — "validate, inspect and criticise",
  and coaching the team to do the same. The word "verification" was never used by either side.
  Note the qualification below: Q3 asks what you do before acting, so it invites a
  pre-action answer. What is *not* prompted is that this is a coached team norm rather than a
  personal habit.

- **Verbatim quote worth keeping:**
  > "I validate, I inspect and I criticise. I'm not taking anything for granted and I also
  > coach my teams to do the same."

#### What this response does to Assumption #1

**It supports the behaviour and undercuts the barrier.**

Verification is real, universal in this respondent's practice, and important enough to coach.
That is the half of Assumption #1 about what PMs *do*.

But Assumption #1 also claims verification cost is what **stops** PMs using AI for
consequential decisions. This respondent uses AI daily for product strategy and market
research — decisions that matter — and verifies as a matter of course. **Verification cost has
not stopped them.** It is a practice they have absorbed, not a barrier they have hit.

Their Q2 answer names a different boundary entirely, and one the strategy does not currently
account for: **some work is inherently human.** Voice of the customer and analyst conversations
are excluded not because checking the output would be expensive, but because the point is
engaging with a person. That is not on the *What to listen for* table above — it is a barrier
this study did not anticipate.

Q4 is the closest support: what is missing for a prioritisation call is *"the right reasoning
in a fast and effective way."* Reasoning that can be followed — which is inspectability — but
**fast**. DecisionLens delivers the first and, at 3.2× the cost of a single call, is
explicitly worse on the second.

#### The sharpest thing said, and it lands on this product

> "You can't use AI for the sake of using AI — there must be a merit/benefit. Speed, cost,
> efficiency, risk reduction. If one of those is not realized — then we're missing the entire
> point of using AI and replace one problem with another."

Held against the measured results in [04](04-evaluation.md), DecisionLens is **slower** and
**3.2× more expensive** than the baseline, and its recall margin is four graded items out of
fifty from a single run. On this respondent's test it would have to justify itself on **risk
reduction** alone — which is exactly the one dimension where the evidence is strongest
(0 of 11 overclaims against 1 of 11) and also the hardest to price.

That is a fair challenge to the product, arrived at independently, and it is recorded here
rather than argued with.

### PM 2

- **Role / context:**
- **Q1:**
- **Q2:**
- **Q3:**
- **Q4:**
- **Q5:**
- **Did verification come up unprompted?**
- **Verbatim quote worth keeping:**

### PM 3

- **Role / context:**
- **Q1:**
- **Q2:**
- **Q3:**
- **Q4:**
- **Q5:**
- **Did verification come up unprompted?**
- **Verbatim quote worth keeping:**

---

## Synthesis

*Empty until all three are complete.*

- **Verification raised unprompted:** _ of 3
- **Most common barrier named:**
- **Barriers named that the strategy does not currently account for:**
- **Anything that contradicts Assumption #1:**

---

## What this changes in docs/01

*Empty until synthesis is complete.* Three places will need updating, whatever the result:

1. The **labelling note** — currently states the document contains no primary user research.
2. **Assumption #1** — currently listed as entirely unvalidated.
3. **What the public evidence says** — currently concedes it has nothing PM-specific.

If the conversations do not support Assumption #1, these sections are updated to say so and the selected problem is re-examined. That outcome is recorded, not avoided.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [04 — Evaluation](04-evaluation.md) — the proposed real-PM study, which this is not
- [05 — Decision Log](05-decision-log.md)

# 04 — Evaluation

> **STATUS: results measured.** Eleven cases, both arms, one live run each against
> `claude-opus-5`. Recordings are in `evals/recordings/`; the generated tables are in
> `evals/results/summary.md`.
>
> **Every number in this document is produced by `make eval`, not typed.** Re-running that
> command regenerates them from the recordings. Sections 9 and 11 remain what they always
> were: a limitations list, and a real-PM study that is **designed and not conducted**.

**Purpose.** Establish whether the controlled DecisionLens workflow produces more verifiable, more useful decision support than a strong single-call baseline — and report honestly if it does not.

---

## Commitments this evaluation makes in advance

Stated now, before results exist, so they cannot be quietly relaxed later:

- **The baseline will not be a strawman.** Same model and version, same decision question, same evidence, same output schema, and a genuinely strong product-decision prompt including citations, assumptions, alternatives, risks, and experiment planning. The only difference is the controlled workflow.
- **Deterministic metrics are preferred over model-based ones.** Citation-span existence is checked programmatically against source text, not judged.
- **Model-based evaluation is labelled as model-based, every time.** An LLM judge is not objective truth.
- **A negative result is reported as a result.** If the controlled workflow does not beat a strong single call by a margin that justifies its complexity, that finding goes in this document. It is the single most useful thing the evaluation could discover.
- **Cached output is never presented as a live finding.** If no API key is available, live evaluation is reported as not executed.

---

## Known before any result exists

Two facts about how this evaluation was built. Both were established during construction, not discovered in the results, and both are recorded here so no reported margin can be read without them.

### The bundled case is in-sample

The prompts contain reading heuristics — check the denominator, prefer the dated measurement over the prose that quotes it, an executive's preference is not a finding. These are generic PM craft and none of them names anything in the corpus. But they were **written after the bundled case was designed**, by the same author, and they map onto hazards deliberately planted in it.

So a strong score on `sample_delivery_exceptions` measures two things at once and cannot separate them: whether the workflow finds hazards, and whether the prompts were written knowing which hazards were there.

This is not repaired by anything in this repository. Sharing the heuristics between the arms (below) makes the comparison fair, and fairness is not the same as generalisation — it equalises the advantage rather than removing it. **The only honest measure is a case authored after the prompts are frozen, by someone who has not read them.** Until that exists, results on the bundled case are reported as in-sample and no claim of generalisation is made from them.

### Both arms are briefed from one source

The commitment above — *the baseline will not be a strawman* — was violated in an early version and the violation was mechanical rather than deliberate. The guidance had been written separately in each arm and the two drifted. Eight reading cues carried by the DecisionLens prompts were absent from the baseline: stakeholder recall treated as measurement; seniority converting a preference into a fact; a stale figure quoted in prose; an older document overtaken by a dated measurement; a 'largest cause' claim true only of one segment; support that holds for one segment being asserted of all; a pilot that could not measure its own effect; and a blank field read as zero. The baseline was left to notice those unaided while the other arm was told to look.

A margin measured under that asymmetry would have been partly a difference in briefing rather than in workflow, which is the strawman this document promised not to build.

The heuristics now live in one module that both arms read from (`src/decision_lens/prompts/heuristics.py`), and a test asserts every block reaches both. The remaining difference between the arms is the intended one: DecisionLens runs the work as separately validated stages with a challenger and deterministic provenance checking; the baseline does all of it in one call with nothing checking the answer afterwards.

One deliberate exception, in the safe direction: the baseline keeps a standalone `WATCH FOR MISLEADING NUMBERS` heading that DecisionLens has no equivalent of. It adds no hazard knowledge the shared blocks do not already carry — it is emphasis, retained because an earlier baseline had it and removing it would have made this arm quietly weaker than the one it is compared against.

---

## Planned sections

### 1. Baseline definition

`src/decision_lens/prompts/baseline.py` · `BASELINE_V2` · `src/decision_lens/baseline.py`

| | |
|---|---|
| **Model** | `claude-opus-5` — identical to the DecisionLens arm |
| **Calls** | One, plus one repair attempt if the response fails schema validation (`BASELINE_REPAIR_V1`). The repair is a re-ask of the same question, never a hint |
| **Output schema** | The same `DecisionBrief` Pydantic model the other arm produces. Neither arm can win on format |
| **Evidence** | The same records from the same connector, in the same order |
| **Validation** | The same deterministic checks: citation spans matched against source text, required sections, mandatory option kinds |

**What makes it strong rather than convenient.** The system prompt opens by telling the model
its reader will check the work. It then requires: citations by evidence id with no invented
ids; every statement classified as fact, assumption, opinion or one of three constraint kinds;
both sides of a conflict cited with what would settle it; gaps named with what they would
change; at least one non-AI option and one no-change/defer/research option, argued as
seriously as the others; support levels stated as judgments with what would change them; every
number qualified by denominator, sample size, date and population; and falsification metrics.

**The decisive fairness property: both arms read the same heuristics.** Every judgment cue
lives in `prompts/heuristics.py` — `READING_EVIDENCE`, `SPOTTING_CONFLICTS`, `FINDING_GAPS`,
`CITING`, `ASSESSMENT_STATES`, `STATING_SUPPORT` — and both prompts compose from it. A test
asserts each block reaches both. This was not true in an earlier version, and the gap is
documented above under *Both arms are briefed from one source*.

The only intended difference is structural: DecisionLens runs the work as separately validated
stages with a challenger; the baseline does all of it in one call with nothing checking the
answer afterwards. Section 7 shows that this single difference is where the margin comes from.

### 2. Test cases

**Eleven cases · 108 evidence files · 674 evidence records · 50 graded contradictions.**
Markdown, CSV and JSON, all synthetic. Ten were authored *after* the prompts were frozen at
commit `1d6ddaf`.

Each case plants a hazard that is **not** named in the shared heuristics, so finding it cannot
be a matter of pattern-matching the briefing:

| Case | Planted hazard | Ceiling |
|---|---|---|
| `checkout_error_rate` | Metric redefined mid-series; no history restated | `strong` |
| `identity_verification` | Date range starts after an outage that distorted the series | `moderate` |
| `loyalty_programme_refresh` | Denominator changed by a dormant-account purge | `moderate` |
| `payment_retry_reliability` | Volume-weighted mean hides one method at 71.6% | `moderate` |
| `pricing_tool_selection` | Seasonally confounded pilot comparison | `moderate` |
| `returns_fraud_signals` | Proxy metric: return *rate* designated the measure of *abuse* | **`low`** |
| `sample_delivery_exceptions` | Survivorship — feedback only from affected customers | `moderate` |
| `search_relevance_mandate` | Citation laundering — a memo's assertion later cited as evidence | `moderate` |
| `subscription_churn` | Survivorship in the exit survey's collection channel | `moderate` |
| `support_ticket_routing` | Double counting — reopened tickets stored as new records | `moderate` |
| `warehouse_picking_errors` | Average hides a bimodal split across aisles | `moderate` |

**Coverage of the categories this section committed to:**

| Required | Case |
|---|---|
| Strong supporting evidence | `checkout_error_rate` — pre-registered randomised experiment, n=412,905, ceiling `strong` |
| Conflicting qualitative and quantitative evidence | `sample_delivery_exceptions`, `subscription_churn` |
| Insufficient evidence | `returns_fraud_signals` — thick corpus, ceiling `low` |
| Governance-sensitive | `payment_retry_reliability` (contractual security), `warehouse_picking_errors` (works-council agreement), `identity_verification` |
| Executive pressure presented as evidence | `search_relevance_mandate` — a memo asserts a root cause with no analysis, and a roadmap draft cites it |
| Misleading or irrelevant evidence | All eleven, by construction; irrelevant records are marked in the answer keys so setting them aside is scored as correct |
| Non-AI / no-build / defer / research is the best next step | `returns_fraud_signals` — the defensible action is to fund an audit before choosing any intervention |

### 3. Ground-truth construction

`src/decision_lens/evaluation/ground_truth.py` defines the schema; one JSON answer key per
case lives in `evals/ground_truth/`.

**What a key asserts:** known facts, assumptions, opinions and constraints with their source
spans; expected contradictions with both sides quoted and how to resolve them; expected gaps
with impact; governance issues; planted evidence hazards; irrelevant records; forbidden
claims; credible alternatives; and a recommendation-restraint block.

**`must_detect` separates graded from noted.** Recall is measured only over entries flagged
`must_detect`. Everything else is recorded because it is true, not because an arm is penalised
for missing it. Of the planted material, 50 contradictions are graded; `EvidenceHazard`
defaults to `must_detect = False`, so a hazard is context for the adjudicator rather than a
score.

**Where it deliberately refuses to name one right answer.** `RecommendationRestraint` carries
`single_correct_answer: bool = False`, and the docstring states why:

> Most real decisions have several defensible next steps, and an answer key that insists on
> one would score restraint as error.

So the keys grade a **ceiling**, not a choice: `max_defensible_support_level` with a written
reason, a set of `defensible_next_steps` any of which scores as correct, and
`must_not_recommend_without_conditions` for options that are only defensible with a stated
guard. Ten of the eleven ceilings are `moderate`; `checkout_error_rate` is `strong` because
the experiment earns it, and `returns_fraud_signals` is `low` because nothing in the corpus
sizes the problem.

**Spans are matched against evidence records, not raw file bytes.** A quote from a CSV row is
checked against the record that row became, so a citation that names the right file but the
wrong row does not silently pass.

**The keys were audited, and the audit found defects in the keys themselves.** They are
recorded in `evals/audit/adjudication.md` rather than quietly corrected — entries that would
have manufactured a false failure against either arm.

### 4. Metrics

**Deterministic:** unsupported-claim rate; citation validity; citation-span existence; required-section completion; non-AI alternative inclusion; no-build/defer inclusion; contradiction precision; contradiction recall; missing-evidence recall; appropriate recommendation restraint; cost; latency; run-to-run consistency.

**Model-based (labelled as such):** citation-support accuracy; evidence-classification quality.

### 5. Results

**Eleven cases, both arms, one live run each against `claude-opus-5`.** Every figure below
is produced by `make eval` from the recordings in `evals/recordings/`; the generated tables
live in `evals/results/summary.md` and nothing here is typed by hand. Re-scoring is free and
offline, so a correction to an answer key never requires re-recording.

#### 5.1 Deterministic metrics — all eleven cases

| Metric | DecisionLens | Baseline |
|---|---|---|
| Contradiction recall | **36/50 (72.0%)** | 32/50 (64.0%) |
| Citation validity | **1451/1451 (100%)** | 967/969 (99.8%) |
| Uncited claims | 0/534 | 0/236 |
| Options generated | 134 | 79 |
| **Overstates support** | **0/11** | 1/11 |
| At the ceiling | 5/11 | 9/11 |
| Understates support | 6/11 | 1/11 |
| Actionable brief | 11/11 | 11/11 |
| Non-AI and no-build option present | 11/11 | 11/11 |

#### 5.2 Held out from prompt design

Ten of the eleven cases were written after the prompts were frozen at commit `1d6ddaf`
(`evals/frozen/prompts_at_case_design.json`). Excluding the one in-sample case:

| Metric | DecisionLens | Baseline |
|---|---|---|
| Contradiction recall | **32/46 (69.6%)** | 28/46 (60.9%) |
| Citation validity | 1317/1317 (100%) | 892/894 (99.8%) |
| Overstates support | 0/10 | 1/10 |

The margin does not depend on the in-sample case. It is slightly larger without it.

#### 5.3 Case by case

Contradiction recall, the only metric where the arms separate materially:

| Outcome | Cases |
|---|---|
| DecisionLens ahead (5) | `identity_verification` 5/6 v 4/6 · `payment_retry_reliability` 4/5 v 3/5 · `pricing_tool_selection` 5/5 v 3/5 · `returns_fraud_signals` 3/4 v 2/4 · `subscription_churn` 2/4 v **0/4** |
| Baseline ahead (2) | `checkout_error_rate` 2/4 v **4/4** · `warehouse_picking_errors` 4/5 v 5/5 |
| Tied (4) | `loyalty_programme_refresh` · `sample_delivery_exceptions` · `search_relevance_mandate` · `support_ticket_routing` |

#### 5.4 What the results actually support

**Three findings hold.**

*It does not overclaim.* Zero cases out of eleven, against one for the baseline — and the
baseline's single failure is the most diagnostic result in the set. It occurred on
`returns_fraud_signals`, a case built specifically so that a thick corpus contains almost
no load-bearing evidence: a finance estimate with no method, two self-selected store
anecdotes, one vendor deck, and a `confirmed_abuse_cases` field that was added and never
populated. The defensible ceiling is `low`. The baseline read the volume and said
`moderate`. DecisionLens said `low`. That is the failure mode this product was built to
prevent, reproduced under measurement.

**Section 7 traces which stage produced that difference, and it is not the obvious one.**
DecisionLens's `recommendation` stage also said `moderate`. The challenger overturned it.
The margin comes from one component, not from seven stages reasoning better.

*It grounds more, without grounding worse.* 1,451 citations against 969 — half again as
many claims anchored — at 100% validity against 99.8%.

*It surfaces more options.* 134 against 79, in every case, and both arms always included
the mandatory non-AI and no-build alternatives.

**Two findings cut the other way, and one of them is serious.**

*Caution is not calibration.* DecisionLens understates support on 6 of 11 cases; the
baseline on 1. Read beside the zero overclaims, this is not a system that judges
confidence well — it is a system biased low, which happens to be the safer direction. The
clearest evidence is `checkout_error_rate`, built so that `strong` support is genuinely
earned: a pre-registered randomised experiment, n=412,905, corroborated by an independent
metrics series. **Both arms said `moderate`.** Neither commits when the evidence deserves
it, and a decision-support tool that always hedges transfers the judgment straight back to
the reader.

*Citation validity is not a differentiator.* 100% against 99.8% is not a distinction.
A well-prompted single call grounds its claims essentially as reliably as a seven-stage
workflow with deterministic provenance checking. This was expected to be a central
advantage and the measurement says it is not one. What DecisionLens does differently is
cite *more*, not cite *better*.

**And the baseline won twice**, including 2/4 against 4/4 on `checkout_error_rate`.

#### 5.5 Whether the margin means anything

Probably less than it looks.

Eight percentage points on contradiction recall is four graded items out of fifty. There
is one run per case and therefore no variance measurement, so no error bar exists and a
difference this size cannot be distinguished from run-to-run noise. The honest statement
is that DecisionLens **did not lose**, and led on a small sample by a margin that has not
been shown to be reproducible.

The restraint result is stronger, because 0/11 against 1/11 is not a rate — it is a
specific failure on the specific case designed to induce it. That is a mechanism, not an
average, and mechanisms survive small samples better than percentages do.

---

### 6. Variance
Repeated runs where credentials, cost, and time allow. Non-determinism is a finding, not noise to be averaged away silently.

**Not measured by design.** Every result reported here comes from a single live run per case,
replayed deterministically thereafter. That is a real limitation and it bounds what any
margin can mean: a difference smaller than the run-to-run variation of either arm is not
a difference. No claim is made that any observed gap would survive a repeat.

**One case was nevertheless recorded twice, and the two runs disagree.** Not planned —
`sample_delivery_exceptions` was recorded once for the bundled demo and again fifteen hours
later when every case was recorded for scoring, and the copies were never reconciled. Same
model, same prompt versions, same evidence, temperature 0.0. Found while walking the pipeline
stage by stage, and reported here rather than quietly reconciled, because a second run is the
measurement this section says is missing.

| | demo recording | scored recording |
|---|---|---|
| Claims extracted | 37 | 47 |
| Contradictions found | 9 | 13 |
| Gaps reported | 18 | 15 |
| Options generated | 11 | 12 |
| Recommendation | `data_quality` | `further_research` |
| Blocking errors | 1 — brief blocked | 0 — brief clean |

Read the volume figures against the headline margin before reading anything else into them.
Contradiction recall leads the baseline by **four items out of fifty**; the run-to-run
difference on this one case is **four contradictions**. The margin is not shown to be
reproducible, and this is the direct evidence for that statement rather than an inference
from sample size.

Two things the same table does *not* undermine. Recall against the answer key was **4 of 4 on
the scored run** — the planted contradictions were all found despite the volume difference, so
what varies is how much surrounding material is reported, not whether the graded items are
caught. And **both runs were restrained**: one blocked itself, the other claimed `low` against
a `moderate` ceiling. Neither overclaimed. Volume varied; the restraint result did not, which
is consistent with it being a mechanism rather than an average.

Both recordings ship. `make demo` replays the first, `make eval` scores the second, and they
are different runs of the same case — stated here so a reviewer who counts nine contradictions
in the demo and thirteen in the results has read the explanation before finding the
discrepancy. What this is not is a variance study: n=2 on one case, and no attempt is made to
put an error bar on anything.

### 7. Side-by-side example

One case, both arms, identical evidence: **`returns_fraud_signals`**. It is the case that
separates the two arms most sharply, and the reason is not the one this project expected.

The corpus is thick and almost entirely load-free: a finance estimate with no method, two
self-selected store anecdotes, a vendor deck, and a `confirmed_abuse_cases` field that was
added and never populated. Nothing in it sizes returns abuse. **The defensible support
ceiling is `low`.**

| | DecisionLens | Baseline |
|---|---|---|
| Recommended action | Fund the $60,000 inspection audit, and gate everything else on it | Fund the $60,000 inspection audit, plus instrument abuse capture |
| **Support claimed** | **`low`** — at the ceiling | **`moderate`** — over it |
| Contradictions found | 3/4 | 2/4 |
| Options generated | 10 | 6 |
| Citations resolved | 113/113 | 77/**79** |

Both arms picked the same action. A PM would act the same way on either brief. **The
difference is entirely in how much confidence each one claimed**, and that is the difference
this product exists to produce.

#### The finding that matters: the reasoning stage was no better

The result above is easy to misread as DecisionLens reasoning more carefully. It did not.

Its `recommendation` stage returned **`moderate`** — the identical overclaim the baseline
made. The recorded evidence is in `evals/recordings/returns_fraud_signals.json` under
`returns_fraud_signals::recommendation::v1`.

The `challenger` stage then returned `concern` on **all eight** of its fixed questions and
set `recommended_support: low`. Because the challenger may lower confidence but never raise
it, `low` is what reached the brief.

The most specific catch, quoted from the recorded challenger output:

> C2 says the audit's *"scope and price are known rather than estimated"* … The memo says
> the opposite: it was an **"Estimated cost"** for a request submitted in March 2026 and
> never scheduled — no vendor quote, no labour line … Calling an estimate "known" is the
> single most consequential misread in the pack, **because the whole case is that this
> option is cheap and bounded.**

It also caught the draft asserting that a post-refund condition audit is *"the one form of
scrutiny governance clearly permits"*, when the policy clause cited says only that inspection
must be triggered by a property of the item or transaction — an inference presented as a
governance finding, and one that contradicts the draft's own description of another option.

#### What this changes about the claim

The honest reading of the headline restraint result — 0/11 against 1/11 — is **not** that
seven stages reason better than one. On this case they reasoned identically and made the same
error.

What the seven-stage arm has is **a stage whose only job is to attack the draft, and a rule
that it can only lower confidence.** That is the mechanism, it is the one component the
baseline lacks, and it is the component that produced the difference. A single call has
nowhere to put an adversarial pass over its own output.

That is a narrower claim than "the workflow is better," and it is the one the evidence
supports. It also implies the cheapest useful version of this product may not be seven
stages: it may be **one call plus a challenger**, which is a specific, testable next
experiment rather than a general belief that more stages help.

### 8. Failures
Where DecisionLens performed worse, produced a wrong classification, missed a planted contradiction, or over-claimed. Reported in detail.

This section is expected to be long, and a short one should be read as a warning that
the evaluation was not looking hard enough. Three classes are recorded separately:

- **Cases where the baseline beat DecisionLens**, named individually with the margin.
- **Stages that failed outright** during recording, with the reason. A brief assembled
  from a run where a stage failed is a degraded brief, and it is scored as one.
- **Defects found in the evaluation apparatus itself** — answer-key entries that would
  have manufactured a false failure, and the harness bugs found while building it.
  `evals/audit/adjudication.md` holds the audit record.

### 9. Limitations
Synthetic evidence; small case count; single author writing both the corpus and the ground truth; no real PM users.

**What the support-level result does and does not certify.** The overclaim metric reads
`Recommendation.support_level` — the one support level that is defined in a prompt, capped by the
challenger, validated and rendered. Three other `SupportLevel` fields are set by the model against
no stated definition and read by nothing, so no metric here touches them, and at least one of them
is demonstrably wrong on the bundled case. Recorded as **D16**. "0 of 11 overclaims" is a claim
about the brief's headline confidence, not about every confidence value in the artifact.

Leading the list: the bundled case is in-sample, as recorded above. Not the weaker claim that a system evaluated against planted conditions *may* be advantaged by knowing such conditions exist — the specific and confirmed one, that the prompts were written after the corpus by its author and encode heuristics matching its planted hazards. Any Phase 10 result on this case is reported under that constraint.

### 10. Model-based evaluation risks

**No number in this document depends on a model judging anything.** Every reported figure —
contradiction recall, citation validity, option counts, support-level calibration — is
produced by deterministic code in `src/decision_lens/evaluation/metrics.py`: string matching
against source text and set comparison against the answer keys. `make eval` makes zero model
calls and completes in under a second.

An LLM judge exists (`src/decision_lens/evaluation/judge.py`, `JUDGE_V1`) and is tested, but
**it is not wired into the scoring path.** That is deliberate, and the reasons are the risks
this section was meant to name:

| Risk | Why it bites here |
|---|---|
| **Generator–judge correlation** | The judge would be `claude-opus-5` grading `claude-opus-5`. A model is not a neutral referee of its own output, and the failure is invisible: it looks like agreement. |
| **Verbosity bias** | Judges reward longer, more structured answers. DecisionLens produces ~5× the words of the baseline. A judged comparison would hand it a win for length. This is the single most disqualifying risk in this evaluation, because the arms differ in verbosity by construction. |
| **Structure bias** | Both arms emit the same schema, so structure is controlled — but a judge shown two briefs would still favour the one with more populated sections, which is again the seven-stage arm. |
| **Unfalsifiability** | A deterministic check fails loudly and reproducibly. A judge's verdict cannot be re-derived by a reader, which defeats the point of a document arguing for verifiability. |

**What the judge was built for, and would be used for.** Claims that no string match can
settle — whether a citation actually *supports* the sentence it is attached to, as opposed to
merely existing. `JUDGE_V1` is deliberately **not** in the product `REGISTRY`, reads only the
rendered markdown, is never told which arm produced it, resolves uncertainty to "not made",
and discards any positive verdict unaccompanied by a verbatim quote. Those are mitigations,
not solutions, and they are why the results above are carried entirely by deterministic
checks.

If a model-based figure is ever reported here, it will be labelled model-based on every
occurrence.

### 11. Proposed real-PM study
Design only — **not conducted, and not to be described as conducted.** Measures: decision-quality rating, verification time, total completion time, trust, willingness to use, actionability, unsupported claims found, assumptions surfaced, alternatives considered, whether the PM changed the decision, and continued usage over time.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)
- [03 — Architecture and Governance](03-architecture-and-governance.md)
- [05 — Decision Log](05-decision-log.md)

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
Exact prompt, model, version, parameters, and what makes it strong rather than convenient.

### 2. Test cases
At least seven, covering: strong supporting evidence; conflicting qualitative and quantitative evidence; insufficient evidence; a governance-sensitive scenario; executive pressure presented as evidence; misleading or irrelevant evidence; and a case where non-AI, no-build, defer, or further research is the best next step.

### 3. Ground-truth construction
How ground truth was authored for the synthetic corpus, what it asserts, and — importantly — where it deliberately does not force a single correct recommendation when several cautious next steps are defensible.

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
| Contradiction recall | **36/50 (72%)** | 32/50 (64%) |
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

**Not yet measured.** Every result reported here comes from a single live run per case,
replayed deterministically thereafter. That is a real limitation and it bounds what any
margin can mean: a difference smaller than the run-to-run variation of either arm is not
a difference. Until a second live run exists, no claim is made that any observed gap
would survive one.

### 7. Side-by-side example
One vivid case shown in full: baseline output next to DecisionLens output on identical evidence, with the specific differences a PM would care about called out.

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

Leading the list: the bundled case is in-sample, as recorded above. Not the weaker claim that a system evaluated against planted conditions *may* be advantaged by knowing such conditions exist — the specific and confirmed one, that the prompts were written after the corpus by its author and encode heuristics matching its planted hazards. Any Phase 10 result on this case is reported under that constraint.

### 10. Model-based evaluation risks
Judge bias toward verbose or structured output, correlation between generator and judge, and why deterministic checks carry the weight of the argument.

### 11. Proposed real-PM study
Design only — **not conducted, and not to be described as conducted.** Measures: decision-quality rating, verification time, total completion time, trust, willingness to use, actionability, unsupported claims found, assumptions surfaced, alternatives considered, whether the PM changed the decision, and continued usage over time.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)
- [03 — Architecture and Governance](03-architecture-and-governance.md)
- [05 — Decision Log](05-decision-log.md)

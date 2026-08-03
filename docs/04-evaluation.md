# 04 — Evaluation

> **STATUS: OUTLINE ONLY — Phase 1.**
> This document is a section plan, not finished content. It is completed in **Phase 10**, after the harness has actually been run.
>
> **No results exist yet. No results are reported here.** Any number appearing in this file in a later phase will have been produced by a command recorded alongside it.

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
Actual measured output. Empty until Phase 10.

### 6. Variance
Repeated runs where credentials, cost, and time allow. Non-determinism is a finding, not noise to be averaged away silently.

### 7. Side-by-side example
One vivid case shown in full: baseline output next to DecisionLens output on identical evidence, with the specific differences a PM would care about called out.

### 8. Failures
Where DecisionLens performed worse, produced a wrong classification, missed a planted contradiction, or over-claimed. Reported in detail.

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

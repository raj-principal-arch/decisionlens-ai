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
Synthetic evidence; small case count; single author writing both the corpus and the ground truth; no real PM users; the fact that a system evaluated against planted conditions may be advantaged by knowing such conditions exist.

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

# 05 — Decision Log

**Status:** Phase 1 deliverable. Maintained continuously; new entries are appended as later phases make decisions.

This log records how DecisionLens was framed, which earlier framings were rejected and why, and how AI was actually used to produce this repository. It documents only what occurred. No tool, activity, research, or result is described here that did not happen.

---

## Part 1 — How the concept evolved

### D1. Initial concept: AI Product Workflow Coach — **rejected**

The first concept was a broad assistant that would coach product managers across their workflow.

**Rejected as too broad.** It had no falsifiable hypothesis, no clear boundary against a general-purpose assistant, and no way to demonstrate value in a take-home. A tool that helps with everything cannot be evaluated on anything. Scope was the problem, not the idea.

### D2. Second concept: Evidence-Based Product Decision Agent — **retained, then challenged**

The concept narrowed to an agent supporting evidence-based product decisions. This was retained as the right territory: consequential, PM-owned, evidence-dependent, and concretely demonstrable.

### D3. Challenge to the framing — **framing changed**

The framing was then challenged on a specific point: **weak evidence in product decisions is a perennial PM-craft problem, not an AI-adoption problem.** PMs have always reasoned under fragmented evidence. An assignment about AI enablement needs a problem that is specifically about AI adoption, not one that merely happens to involve AI in its solution.

This challenge was accepted. It is the single most consequential change in the project's framing.

### D4. Reframing to trust, traceability, and verification — **adopted**

The framing moved from *"PMs have weak evidence"* to *"PMs cannot cheaply verify consequential AI output, and that is what stops AI adoption at the boundary of consequence."*

This reframing is what makes the problem an AI-enablement problem. It explains the observed pattern — heavy AI use for drafting, summarizing, and brainstorming; light use for decisions that matter — as a consequence of verification cost rather than of tool access or skill.

The reasoning is developed in [01 — Product Strategy](01-product-strategy.md).

### D5. "Evidence-grounded" replaced "evidence-based" — **adopted**

A deliberate wording change, not cosmetic.

*Evidence-based* describes a posture: the recommendation was informed by evidence. It is unfalsifiable — anyone can claim it.

*Evidence-grounded* describes a mechanical property: each claim is anchored to a retrievable source span that can be checked. It is falsifiable, and the prototype checks it programmatically.

The product's central promise is in that distinction, so the language had to carry it.

### D6. Solution-first example question — **rejected**

An early sample case asked a question in the shape of *"should we build an AI assistant for delivery exceptions?"*

**Rejected.** The question presupposes both the solution and the technology. A system asked that question can only argue about how to build the thing already named. It cannot recommend a process change, a data-quality fix, or doing nothing — which are frequently the right answers.

Worse, a tool built to encourage AI adoption that is fed solution-first questions will reliably recommend AI, and PMs will correctly stop trusting it.

### D7. Problem-first example question — **adopted**

The bundled sample case became:

> **Which intervention should the team prioritize to reduce delivery exceptions?**

This admits the full range of answers: notifications, address validation, driver workflow simplification, training, rules-based automation, a limited AI capability, more research, deferral, or no change.

The constraint is enforced structurally rather than by intention. Every brief must contain at least one non-AI alternative and at least one no-build, defer, or further-research alternative, and validation checks for both deterministically. DecisionLens must be able to conclude that an AI solution is not justified.

### D8. Single orchestrator, not multi-agent — **adopted**

The architecture is one DecisionLens orchestrator with controlled, inspectable stages. Connectors retrieve; skills interpret; the orchestrator coordinates; the PM decides.

Rejected: one autonomous agent per data source, and any multi-agent topology.

The reasoning is that the property under test is *verifiability*. An architecture whose own behaviour is hard to trace cannot credibly demonstrate that traceability improves decision support. A multi-agent design would also have been more impressive to describe and less able to prove anything — the wrong trade for this work.

### D9. Enterprise connectors documented, not implemented — **adopted**

The prototype implements exactly one connector, `LocalFileEvidenceSource`, over synthetic files. Jira, Confluence, product metrics, customer feedback, support tickets, and the rest are specified in [03 — Architecture and Governance](03-architecture-and-governance.md) but not built.

A written connector contract is more honest than stub classes that raise `NotImplementedError`, and no claim of access to any real system appears anywhere in this repository.

### D10. Strong baseline, not a strawman — **adopted**

The evaluation baseline uses the same model and version, the same evidence, the same output schema, and a genuinely strong prompt. It differs from DecisionLens only in that it is one model call without the controlled stages.

If a strong single call performs comparably, the controlled workflow is unnecessary complexity and the evaluation should say so. That outcome is recorded as a finding, not suppressed.

### D11. No vector database — **adopted**

Not justified at the size of the prototype corpus, and it would make retrieval harder to inspect. Keyword and manifest-driven retrieval over explicitly identified files keeps every retrieval step auditable, which serves the product thesis rather than compromising it. Revisiting this would require explicit approval.

### D12. Shared heuristics between the arms — **adopted**

D10 committed to a baseline that is not a strawman. That commitment was being broken.

The judgment guidance had been written separately in each arm and the two drifted. Eight reading cues carried by the DecisionLens prompts were absent from the baseline: stakeholder recall treated as measurement; seniority converting a preference into a fact; a stale figure quoted in prose; an older document overtaken by a dated measurement; a 'largest cause' claim true only of one segment; support that holds for one segment being asserted of all; a pilot that could not measure its own effect; and a blank field read as zero. The baseline was left to notice those unaided while the other arm was told to look.

Nobody decided this. It is what happens to duplicated text, which is why the fix is structural rather than a correction: both arms now compose from one module, and a test asserts every block reaches both. The baseline prompt version moved to v2 and its cached response was re-recorded, because replaying an answer to a question no longer being asked is the same defect in another form.

The difference now under test is the intended one — staged and validated versus one call — and nothing else.

### D13. The bundled case is in-sample and stays that way — **accepted, not fixed**

The prompts' reading heuristics were written after the bundled case was designed, by the same author, and map onto hazards planted in it. Results on that case cannot separate "the workflow finds hazards" from "the prompts knew which hazards to expect."

D12 does not fix this; it equalises it. Writing a second case now would not fix it either, since the same author knows the same prompts. The honest remedy is a case authored after the prompts are frozen by someone who has not read them, which is out of scope here.

Recorded rather than repaired, and stated in [04 — Evaluation](04-evaluation.md) ahead of any result, so no margin can be quoted without it.

### D14. Reuse is decided on prompt text, not on a version label — **adopted**

Two prompts, `classification` and `contradictions`, were edited after being recorded and their versions were left alone. Resumed runs match on version, so every later run replayed answers to wording that no longer existed. Two of the eight shipped stages were stale and the demo gave no sign of it.

Three things were wrong, and only fixing all three closes it:

- **The label lied.** Both prompts are now v2, and the responses were re-recorded. A version is a declaration a human makes and forgets to make.
- **Resume trusted the label.** It now compares the prompt's content fingerprint and re-records on a mismatch. The fingerprint is derived from the text, so it cannot be forgotten. An absent fingerprint on an older recording is treated as "unknown", not "mismatched", so adding the check did not invalidate the existing cache.
- **The warning existed and went nowhere.** The cached provider was already emitting *"the prompt has changed since this response was recorded"* on every affected call. `RunStage` had no field to hold it and the report had no line to print it, so it was constructed and discarded on every run. Provider warnings now reach the run trace and the rendered brief.

The third is the one worth remembering. The detection was never missing; the path from detection to a human reading it was. A check whose output nobody receives is indistinguishable from no check, and this repository's argument is that a person must be able to see what a system did.

Tests cover each layer, and a test compares every shipped recording's fingerprint against the live prompt, so this class of drift now fails the build rather than surviving in a cache.

### D15. The audit trail records which prompt text ran, not only its label — **adopted**

D14 established that a prompt version is a claim a human makes and forgets, and that a content fingerprint cannot be forgotten because it is derived from the text. The fix at the time made *resume* compare fingerprints. It did not change what the brief itself records.

So `RunStage` went on pinning `prompt_version` alone. The fingerprint was computed, compared at record and replay time, and then discarded before reaching the artifact a reader actually holds. Reconstructing a run from its trace still rested on the label being honest — the exact assumption D14 had disproved.

Found while writing [03 — Architecture and Governance](03-architecture-and-governance.md), which had listed it as a known gap. `RunStage.prompt_fingerprint` now carries the hash from request through response into the trace, the rendered brief and the JSON artifact, and a test fails if it is dropped at any boundary.

Third instance of one pattern in this repository, and the reason it is worth naming: a check whose output nobody receives is indistinguishable from no check. The provider's staleness warning was built and thrown away (D14). The fingerprint was compared and thrown away (here). The connector's retrieval diagnostics are recorded and still thrown away — documented in §1.11 of 03 as an open limitation rather than quietly left. Detection is the easy half; the path from detection to a human reading it is where these keep failing.

### D16. Three `support_level` fields the model fills in unguided — **recorded, not fixed**

Found late, while walking the pipeline stage by stage to explain it. Not caught by the evaluation, and the reason it was not caught is the more useful half.

`SupportLevel` appears on four models. One is defined and used. Three are neither.

| Field | Set by | Guidance given | Read by anything |
|---|---|---|---|
| `Recommendation.support_level` | model | `STATING_SUPPORT`, in the prompt | yes — the headline figure, and the only one the challenger can lower |
| `EvidenceClassification.support_level` | code, from type and age | n/a — it is a rule | **no** |
| `Claim.support_level` | model | **none** | **no** |
| `DimensionAssessment.support_level` | model | **none** | **no** — until the interface read it |

Two distinct defects, and they compound.

**The vocabulary has no stated meaning on three of the four.** `STATING_SUPPORT` — *"if the strongest support is a single small or non-randomised study, that is not strong support"* — reaches the recommendation prompt and the baseline, and nothing else. So classification and alternatives emit `low`/`moderate`/`strong` against no definition. The model supplied one of its own, and it is not the same one: on the bundled case, `DimensionAssessment.support_level` reads `strong` for options whose own summary calls the evidence *"effectively nil"* and *"no internal evidence at all"*. Read as "the evidence is strong" that is flatly wrong; read as "I am confident in this assessment" it is defensible. Nothing in the repository says which was meant, so both readings are available and one of them is a lie.

**Nothing consumed them, so nothing exposed the divergence.** Two are written and never read — not by the report, the interface, validation, or the challenger. They reach the JSON artifact and stop. An unread field cannot disagree with anything visible, so it drifts silently and indefinitely.

Then the interface read one. Building the option table, `DimensionAssessment.support_level` was surfaced as a column headed *Evidence confidence* on the reasonable assumption that a field of that type meant what its name suggested. The column showed `strong` against the worst-evidenced option in the set — the vendor AI product whose single supporting artefact is an uncontrolled marketing claim. A latent defect became a visible false statement the moment something rendered it, and it took a reader asking *"why did you recommend that one?"* to catch it. The column now reports counted citations for and against, which cannot drift from its label because it is arithmetic over already-resolved citations.

**What is not being done.** Defining the vocabulary for all three and re-recording would cost a full evaluation re-run, and the fix is not obviously one line: `evidence_confidence` as a *criterion* carrying a support level is arguably confused at the model layer rather than the prompt layer, and that is a design question, not a wording one. Deleting the two unread fields is the cheaper honest option and is the likely resolution. Neither is being done inside this submission, because both change recorded output and the evaluation numbers are already reported.

The eval could not have caught this. No answer key scores `Claim.support_level`, and no metric reads it. The harness measures what the brief says; these fields are not in the brief. That is a real limit on what "0 of 11 overclaims" certifies — it certifies the one support level that is defined, prompted, validated and rendered, and says nothing about the three that are not.

Fourth instance of the pattern D14 and D15 name. There it was detection with no path to a reader — a staleness warning discarded, a fingerprint discarded, retrieval diagnostics discarded. Here it is the mirror image: **a value written with no reader, and therefore no one to notice it was wrong.** Unread output and unheard warnings fail the same way. Something has to consume a field for anyone to find out it is false.

---

## Part 2 — How AI was used to build this

Recorded plainly, because the assignment evaluates AI-native working approach and an inaccurate account here would be self-defeating.

### ChatGPT

Used for assignment decomposition and initial concept exploration. It produced the first structural breakdown of the assignment and the early concept space, including the AI Product Workflow Coach concept that was subsequently rejected (D1).

### Claude

Used to pressure-test the work rather than to generate it. Specifically:

- **Problem selection** — challenging whether the selected problem was genuinely an AI-adoption problem rather than a PM-craft problem. This produced D3 and D4, the most important framing change in the project.
- **Evaluation rigor** — challenging baseline strength, the difference between deterministic and model-based metrics, and what would falsify the hypothesis.
- **Enterprise enablement** — pressure-testing the connector model, the configuration layers, and permission handling.

### Claude Code

Used to build the repository under an explicit **inspect → plan → approve → execute** process. Each phase is authorized individually. Approval of one phase is not approval of the next. Every phase ends with a report of what changed, validation results, `git status --short`, `git diff --stat`, and known issues, followed by a wait for human review.

### Human judgment

AI output is reviewed and revised rather than accepted. Final scope, framing, and architecture are human decisions. The strategy document distinguishes observation, product judgment, assumption, and hypothesis specifically so a reader can see where reasoning is doing the work.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)
- [03 — Architecture and Governance](03-architecture-and-governance.md)
- [04 — Evaluation](04-evaluation.md)

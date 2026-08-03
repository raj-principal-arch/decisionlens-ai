# 03 — Architecture and Governance

**Purpose.** Specify the prototype architecture as built, the enterprise architecture it would grow into, and the governance model required to operate DecisionLens responsibly inside a large organization.

---

## How to read this document

Two kinds of statement appear here and they must not be confused.

| Marker | Meaning |
|---|---|
| **[Built]** | Implemented in this repository. Every such claim names the module that implements it and can be checked against the source. |
| **[Design]** | Specified, not implemented. Nothing marked this way exists, runs, or has been tested. |

**Section 1 is [Built] throughout.** Sections 2–21 are predominantly **[Design]**, with the built parts marked individually where they exist, because most governance sections have a small implemented core and a large unimplemented remainder, and collapsing the two would be the exact misrepresentation this document is supposed to prevent.

Three constraints hold everywhere:

- **The prototype implements exactly one connector**, `LocalFileEvidenceSource`, over a local directory of synthetic files. Jira, Confluence, product metrics, customer feedback, support tickets, OKRs, experiment results, governance policy, technical docs and prior decisions are **documented, not implemented** (D9).
- **No access to any real Walmart system is claimed or was used.** All evidence in this repository is synthetic and fictional. No enterprise observation, pilot result, or user finding is reported anywhere in this document, because none exists.
- **Where the prototype falls short of the enterprise design, this document says so in the section where the gap lives**, rather than describing the design as though it were present.

---

## Architectural invariants

These hold in every section below and are not up for negotiation during the build:

- **Connectors retrieve.** Authenticate → apply user permissions → search → retrieve → preserve metadata → normalize → return evidence. A connector never decides what the company should build.
- **Skills interpret.** Relevance, classification, contradiction detection, missing-evidence detection, alternative generation, recommendation analysis. A skill never reaches a data source.
- **DecisionLens orchestrates.** One controlled coordinator with inspectable stages. No autonomous loops, no agent-per-source, no multi-agent topology.
- **The PM decides.** The agent recommends; the human is accountable. The PM's final decision is recorded separately from the agent's recommendation.
- **Governance and verification are parallel, embedded capabilities — not sequential ones.** Governance defines which data, models, actions, and decisions are permitted; verification provides evidence that outputs comply with those expectations. Both are designed into the workflow from the beginning. Neither is a layer applied after the fact, and neither is downstream of the other.

The invariants are load-bearing in the type system, not just in prose. `EvidenceSource.retrieve` takes an `EvidenceRequest` (scope) and returns `EvidenceRecord`s (source material): there is no channel through which a connector can return a conclusion. `SkillContext` carries a request and evidence and holds no provider and no fetch method: there is no channel through which a skill can retrieve. `DecisionLens.run` returns a `DecisionBrief`; `record_pm_decision` is a separate function producing a separate `PMDecision`.

---

# 1. Prototype architecture

**[Built]** — `src/decision_lens/orchestrator.py`

```
DecisionRequest  (question, desired outcome, criteria, user context)
      │
      ▼
check request ......... no evidence source configured → DecisionLensError
      │
      ▼
retrieve .............. each source independently; a dead one is a note
      │
      ▼
normalize ............. drop repeated ids and duplicate passages
      │
      ├── no evidence → a brief that says so; no skill is run
      ▼
relevance ............. which records bear on the decision
classification ........ claims, and how each should be read
contradictions ........ conflicts, surfaced and left unresolved
missing evidence ...... what the decision needs and does not have
alternatives .......... options, including non-AI and no-build
recommendation ........ a draft, never an approval
challenger ............ the eight fixed questions
      │
      ▼
provenance ............ resolve every citation against real text
support ceiling ....... lower confidence once, with its reason
validate .............. deterministic checks → ValidationIssue
      │
      ▼
DecisionBrief + RunTrace
      │
      ▼  a separate call, made by a person
record_pm_decision → PMDecision
```

## 1.1 What "controlled" means concretely

The sequence is written out literally in `DecisionLens.run`. It does not vary by input. There is no planner, no agent choosing its next move, and no loop that continues until something decides it has finished. That is the property under test: a wrong answer is attributable to a named stage rather than to a system (D8).

Four behaviours follow from it, and they are the reason the design is worth the extra tokens:

| Property | Mechanism |
|---|---|
| Partial failure degrades, never aborts | `_attempt` catches `SkillError`, records the failed stage in the trace, and continues. The absent section is then reported as *absent because it failed* — not as nothing to report. |
| The model never supplies evidence | Skills receive records the connectors retrieved. The brief is assembled around those records, so a citation either resolves against retrieved text or is reported. There is no path by which analysis introduces its own sources. |
| Confidence is reduced in exactly one place | `enforce_support_ceiling` in `validation.py`. The challenger's request and the evidence-derived ceiling are combined there, the weakest wins, and the reason is written into `Recommendation.support_basis` so the reduction appears in the brief rather than only in a log. |
| The PM's decision is not produced here | `run` returns a recommendation. `record_pm_decision` is a separate call a person makes afterwards. |

Only one condition raises: no evidence source configured. Everything downstream degrades, because a brief that reports its own holes is worth more than an exception.

## 1.2 Retrieval and normalization

Retrieval is an independent pass per source, written that way so it can be parallelised later without restructuring. It is sequential today because the only connector reads local files, and concurrency that buys nothing costs clarity. A source that raises `EvidenceSourceError` contributes no evidence, appends a note naming the failure, and the run continues.

Normalization applies two rules, both about citations staying unambiguous:

- **Repeated evidence id → dropped.** A citation to a repeated id would point at two different records.
- **Identical `(source_reference, content)` → dropped.** Counting one passage twice would let a single opinion read as independent corroboration.

Both counts are reported as notes, which reach the brief as `analysis_note` warnings.

If normalization leaves nothing, no skill runs at all and the brief says so. Running the skills against an empty evidence set would produce confident text with nothing behind it.

## 1.3 The seven stages

Six analysis skills plus the challenger. Every skill is *hybrid*: it computes what is computable and asks the model only for judgment. An instruction can be ignored; a check cannot.

| Stage | Prompt | Model judges | Code decides |
|---|---|---|---|
| `relevance` | v1 | which records bear on the decision | every id must exist; anything the model did not mention is **kept**, not dropped — silence is not an exclusion decision |
| `classification` | v2 | claim extraction, and fact / assumption / opinion / constraint | every citation must resolve; at least one claim required; staleness is date arithmetic against `as_of` (365 days); per-record support is derived from evidence type and age and **never returns `strong`** |
| `contradictions` | v2 | which evidence conflicts, and how | both sides must resolve; `how_to_resolve` is mandatory; two sides from the same record are allowed, because a document can contradict itself |
| `missing_evidence` | v1 | what the decision needs and lacks | at least one gap required; `why_it_matters` mandatory; a scan finds metric fields present with no value and adds them — a blank is not a zero |
| `alternatives` | v1 | the options, their tradeoffs, dimension assessments | at least one non-AI option and at least one no-change/defer/further-research option, enforced by enum check; citations must resolve; ids must be unique |
| `recommendation` | v1 | which option, how firmly, on what basis | the selected id must exist among the alternatives; citations must resolve; `strong` requires `what_would_change_it`; `strong` is capped to `moderate` if any supporting claim is ungrounded |
| `challenger` | v1 | the eight questions | all eight answered exactly once; citations resolve; claim ids resolve; a `fails` verdict requires `what_would_change_it`; the non-AI and no-build verdicts are **counted, not judged**; any request to raise confidence is discarded |

Data flow between stages is explicit and narrow. `relevance` may narrow the evidence set (and only narrows it — if it selects nothing usable, the full set stands). `alternatives` receives the constraint-typed claims. `recommendation` receives alternatives, contradictions and gaps. `challenger` receives all of those plus the draft.

**Retry policy.** When a skill's `violations()` returns anything, the skill re-prompts **once**, naming the broken rule verbatim, then fails. It never fills the gap itself — DecisionLens authoring content and presenting it as analysis is the fabrication the product exists to prevent. The retry appears in the trace as a second stage named `<stage>-retry`, and validation groups the two so one lost analysis is reported once rather than twice.

**Timeouts.** 90 seconds per skill by default (`SKILL_TIMEOUT_SECONDS`); 1,900 seconds when recording against a live model, sized against the output ceiling rather than guessed. `BaseModelProvider` enforces the deadline after the fact — Python cannot interrupt a synchronous call in flight — so the live adapter *also* passes the timeout to its HTTP transport. The base-class check exists to guarantee an overrunning response is never *used*, and to catch a provider that quietly ignores its deadline.

## 1.4 The challenger

`skills/challenger.py`. Eight fixed questions, put to the draft before a person sees it:

`claims_supported` · `contradictions_considered` · `preference_as_evidence` · `non_ai_considered` · `no_build_considered` · `overconfident` · `what_could_make_it_wrong` · `what_to_test`

Three rules are enforced in code rather than requested in the prompt:

1. **All eight, exactly once each.** A set comparison, not a judgment. A challenger that skips the awkward question is worse than none, because silence reads as approval of something never examined.
2. **Confidence can only go down.** If the challenger asks for a support level higher than the draft's, the request is discarded and the attempt is reported as a warning. A reviewer that can talk itself into more certainty has stopped being a reviewer.
3. **Two answers are arithmetic.** Whether a non-AI option and a no-build option *exist* is counted from the alternatives. The model judges only whether they were argued seriously. If the option is absent the verdict is forced to `fails` whatever the model said, and the model's own text is preserved underneath the override.

The challenger does not rewrite the recommendation. It may relabel a claim (`fact` → `stakeholder_opinion` is the useful case), append to `what_would_change_it`, and add `Test before investing: …` conditions. Its findings get no field of their own on `DecisionBrief`; they surface as validation issues, which is where a reader already looks for reasons to distrust a brief. A `fails` verdict is an error; a `concern` is a warning.

Reclassification runs *before* validation, deliberately: a claim the challenger demotes from fact to opinion must be relabelled before the unsupported-fact check runs, or the brief reports a defect the challenger already fixed.

## 1.5 Provenance: deterministic, and separate from the model

`provenance.py` resolves every citation in the brief by string containment against the retrieved record text. Nothing here asks a model anything. Whether a quote appears in a document is not a matter of opinion, and a check that can be argued with is not a check.

Two failure kinds are kept apart because they have different causes and different fixes:

- `unknown_evidence` — the citation names a record that was never retrieved. The analysis wandered outside its own evidence set.
- `quote_not_found` — the record is real, the text is not in it. The quote was paraphrased or invented.

Each citation carries a `CitationRef` naming where it was found (`claim CL-003`, `contradiction CN-001 side_a`, `alternative ALT-04 / delivery_effort`), so a failure report says what to look at rather than "3 citations do not resolve". `ProvenanceReport.validity` returns `None` rather than 1.0 when a brief cites nothing — a brief that never risked anything does not get a perfect score.

An *unresolvable* citation and an *ungrounded* claim are also reported separately. A claim with a broken citation tried to show its work and failed; a claim with no citation never tried.

## 1.6 Citation repair — a correction, not a relaxation

`quoting.py`, applied by `skills/base.py:repair_citations`.

The verbatim rule is the product's central promise. It also survives contact with a language model badly, and always in the same direction. A live run was discarded because a quote read `First attempt success in the pilot group was 88.1%` where the source says `First-attempt success…`. The record was right, the sentence was right, the figure was right, and one hyphen was missing.

There were two ways to respond and only one of them is honest:

- **Relaxing the check** — accepting a quote that merely *resembles* the source — would leave text in the brief that appears nowhere in the evidence. A reader who went looking for it would not find it. The promise would be gone while the label stayed.
- **Locating the source span** and rewriting the citation to the source's own characters leaves the invariant exactly where it was. The brief still contains only text that is in the evidence. What changed is that a near miss became a reported correction instead of a discarded stage.

The second is what is implemented. Two properties keep it a correction rather than a guess:

- **Only typography is forgiven.** Case, whitespace runs, the dash family, and curly quote marks. Never a word, never a digit, never a negation. `88.1%` cannot become `87.6%`, because those differ by characters the normaliser does not fold.
- **Only when unambiguous.** One match, in one record. A phrase occurring in two places has no single correct source, so nothing is repaired and the citation is rejected exactly as it was before.

The same principle covers a mis-attributed quote: text found verbatim in exactly one *other* record has its `evidence_id` re-pointed there. Added after a live run failed twice in a row on this and nothing else — the model quoted a delivery comment correctly and attributed it to the neighbouring record. Telling it not to did not work, and an instruction that has been ignored is not a control.

Every repair appends a line to the run's warnings and reaches the brief. Nothing is changed silently. The same reasoning governs two neighbouring repairs in `llm/base.py`: a JSON field name that folds onto exactly one declared field is snapped to it, and an enum value is snapped only when one candidate scores strictly highest *and* the match includes a word unique to that candidate — so `would_change_scope` resolves to `would_refine_scope`, while `would_change_everything` is refused because nobody can say which was meant.

## 1.7 Validation and guardrails

`validation.py`. Everything is arithmetic or set membership. The module is split in two halves that stay strictly separate: `validate` **reports and never mutates**; `enforce_support_ceiling` is **the only thing that lowers a support level**, and the orchestrator calls it explicitly. Burying confidence reduction inside a checking function would make it a side effect nobody reads.

| Code | Severity | What it asserts |
|---|---|---|
| `source_missing` | error | Every citation names a retrieved record |
| `citation_span_missing` | error | Every quoted span exists in that record |
| `section_missing` | error | Evidence, claims, alternatives and a recommendation are all present |
| `ungrounded_fact` | error | Nothing labelled `fact` cites nothing — the checkable form of "separate assumptions from facts" |
| `ungrounded_claim` | error | No recommendation claim cites nothing |
| `dangling_alternative` | error | The recommended option is one of the options |
| `non_ai_alternative_missing` | error | At least one non-AI option exists |
| `no_build_alternative_missing` | error | At least one no-change / defer / further-research option exists |
| `support_too_high` | error | Stated support does not exceed what the evidence can carry |
| `challenge_failed` | error | No challenger question returned `fails` |
| `stage_failed` | error / warning | Error for `contradictions`, `recommendation`, `challenger`; warning otherwise |
| `contested_support` | warning | A recommendation resting on one side of a reported contradiction says so |
| `support_reduced` | warning | Records that confidence was lowered, and why |
| `no_missing_evidence` | warning | An empty gaps section usually means the search was shallow |
| `uncited_evidence` | warning | Retrieved-but-never-cited records, named |
| `challenge_concern` | warning | A challenger question returned `concern` |
| `analysis_note` | warning | Stage notes — staleness counts, records set aside, repairs made |

An **error** means the brief must not be presented as it stands. A **warning** means the reader should know, but the brief holds. The CLI exits 2 when the brief carries blocking errors, so a run yielding an unusable brief cannot look clean to a script.

Two of these deserve emphasis because they encode product commitments rather than hygiene. The non-AI and no-build requirements (D7) are checked in code precisely because a tool built to encourage AI adoption cannot be trusted to remember them. And `contested_support` catches the failure a reader is least likely to spot on their own: every claim cited, every citation resolving, and the contradiction sitting two sections away where nobody rereads it while weighing the answer.

**The support ceiling.** `support_ceiling` returns the highest level a brief's evidence can carry:

| Condition | Ceiling |
|---|---|
| An unresolved citation *inside the recommendation* | `low` |
| A recommendation claim citing nothing | `low` |
| Any unresolved citation anywhere | `moderate` |
| Missing mandatory non-AI option | `moderate` |
| Missing mandatory no-build option | `moderate` |

The weakest applies. The challenger's requested ceiling is combined with it in the same call, so a reduction is one act with one explanation rather than two competing ones. The rank ordering (`low` < `moderate` < `strong`) exists only to answer "which of these two is weaker". It is never averaged, summed, or shown to a reader, and support levels are **qualitative judgments, not calibrated probabilities**.

## 1.8 The provider boundary

`llm/`. Vendor-neutral by design: DecisionLens must be able to swap Anthropic for another vendor for a deterministic offline stub without any skill noticing, because the thing under test is the workflow, not the model.

- `ModelProvider` is a Protocol — `provider_id`, `model_id`, `complete(ModelRequest) -> ModelResponse`. An adapter around an existing enterprise client need not inherit from DecisionLens.
- `ModelResponse` always says where it came from: provider, model, prompt version, skill, latency, usage, `is_cached`, and any warnings. `is_cached` has no default that could hide it.
- `parse_structured` raises on malformed output rather than returning a half-populated object.
- `ProviderChoice` offers `cached` and `anthropic`. `openai` is deliberately absent: the abstraction is vendor-neutral and an adapter would slot in, but none exists, and offering a choice that resolves to nothing is worse than not offering it.

**The demo replays recorded responses and needs no API key.** `CachedDemoProvider` reports `provider_id = "cached-demo"` and `model_id = "recorded-replay"` — it does not claim a model name, because that would let a trace read as though the model had been called. The model and date each response was recorded from travel per-response into the trace and are printed under the run-trace table in the rendered brief. A cache miss is an **error**, never a placeholder: emitting a plausible stub would put unverifiable content into a decision brief.

Going live is an explicit act, enforced in one place (`config.py`, `llm/factory.py`):

- `MODEL_PROVIDER=anthropic` is required. An `ANTHROPIC_API_KEY` sitting in the environment is not consent to spend money.
- No silent fallback in either direction. A missing or malformed key fails with instructions rather than quietly serving recorded output while a reviewer believes they watched a live run.
- The key is excluded from `repr` and `model_dump`, so it cannot reach a log line, a trace, or a brief by accident. `masked_key` shows four characters.
- The live adapter disables SDK-level retries, checks `stop_reason` before reading content (a refusal or truncation is a failure, not text), and passes the deadline to the transport.

## 1.9 Prompt versioning and content fingerprints

Every `Prompt` carries a human-declared `version` and a derived `fingerprint` (SHA-256 of system text plus user template). The version appears in the run trace. The fingerprint catches the case a human forgets: prompt edited, version left alone.

`ModelRequest.cache_key` is `case::skill::prompt_version` and deliberately **excludes** the prompt text. Keying on the rendered prompt would invalidate every recorded response on a typo fix and silently break the offline demo. The fingerprint travels separately, so drift stays visible without being fatal.

This is not theoretical. Two prompts — `classification` and `contradictions` — were edited after being recorded and their versions were left alone, so every later run replayed answers to wording that no longer existed. Two of the eight shipped stages were stale and the demo gave no sign of it. Recorded as **D14**. Three things were wrong and all three had to be fixed: the label lied (both are now v2 and were re-recorded); resume trusted the label (it now compares fingerprints and re-records on a mismatch, treating an absent fingerprint as *unknown* rather than *mismatched* so the existing cache stayed valid); and **the warning existed and went nowhere**.

That third one is the part worth carrying into the governance sections. The cached provider was already emitting *"the prompt has changed since this response was recorded"* on every affected call. `RunStage` had no field to hold it and the report had no line to print it, so it was constructed and discarded on every run. **A check whose output nobody receives is indistinguishable from no check.** `RunStage.warnings` and the rendered "Notes on how these answers were obtained" block exist because of it, and a test now compares every shipped recording's fingerprint against the live prompt, so this class of drift fails the build rather than surviving in a cache.

**Closed, and worth recording how.** This document originally reported a gap here: the trace pinned the prompt *version* and not the fingerprint, so reconstructing a run from the trace alone still relied on a human-declared label being honest — precisely the assumption D14 had already disproved. The gap was found while writing this section and fixed on the strength of it. `RunStage.prompt_fingerprint` now carries the content hash from the request through the response into the trace and the rendered brief, and a test fails if it is dropped at any boundary.

The episode is the reason the section is worth reading twice. D14's lesson was that a check whose output nobody receives is indistinguishable from no check. The fingerprint was being *computed*, *compared* at record and replay time, and then discarded before the artifact a reader actually holds — the same shape of defect, one layer further out.

## 1.10 The audit record

`RunTrace` holds `run_id`, `request_id`, start and end times, and an ordered tuple of `RunStage`. Each stage pins:

`name` · `started_at` / `ended_at` · `provider` · `model` · `prompt_version` · `input_tokens` · `output_tokens` · `latency_ms` · `error` · `warnings`

Retrieval stages appear as `retrieve:<source_system>`. Skill stages carry the provider fields; a retry appears as `<stage>-retry`. `failed_stages` and `total_latency_ms` are derived. The trace is embedded in the `DecisionBrief` and rendered as a table in the Markdown output, with provider warnings printed beneath it as sentences rather than squeezed into a cell.

Note precisely what is and is not pinned: provider, model and prompt version are **per stage**, not per run, which is correct — a run may in principle mix providers, and a stage that failed before reaching the provider legitimately has none.

## 1.11 What the prototype does not have

Stated here rather than left to be inferred:

- **No authentication, no authorization, no identity.** `UserContext.permissions` is an unused tuple and `EvidenceRecord.permission_scope` is a string read from the manifest that nothing ever checks. Any file under the evidence root is retrievable by anyone who can run the process. See §5 and §12.
- **Connector diagnostics do not reach the brief.** `LocalFileEvidenceSource` records `files_seen`, `files_read`, `records_built`, `records_filtered_out` and every skipped file with its reason — and the orchestrator never reads them. "We found 56 records" means something different when six files failed to parse, and today the brief cannot tell you which case you are in. A real defect of the same shape as D14, and named here rather than papered over.
- **Latency is not measurable in demo mode.** Replay is sub-millisecond, so `total_latency_ms` reads 0 on a cached run. Only a live run produces meaningful timing.
- **No persistence.** Briefs are written to `out/`. There is no store, no run history, no retention policy, no way to query past decisions. See §14 and §21.
- **No cost control.** Nothing caps spend per run or per user. See §17.
- **No PII handling, no classification, no redaction.** See §13.
- **No red-team testing has been conducted.** See §20.

---

# 2. Enterprise architecture

**[Design]** — nothing in this section is implemented.

The spine is unchanged. What is substituted is the left-hand edge, and what is added is a policy surface and a durable audit record.

```
PM request (identity, product area, question, desired outcome, scope)
      │
      ▼
Evidence planning ......... which sources this question needs, and why      [Design]
      │
      ▼
Shared authorized connectors ...... executing under the PM's own identity   [Design]
   Jira · Confluence · product metrics · customer feedback · support
   tickets · OKRs · experiments · governance policy · prior decisions
      │
      ▼
Normalized evidence (EvidenceRecord + classification + permission metadata)
      │
      ▼
─────────── the seven stages, unchanged from §1 ───────────
      │
      ▼
Validation ─┬─ deterministic checks (as built)                              [Built]
            └─ policy checks: classification, retention, jurisdiction       [Design]
      │
      ▼
DecisionBrief ────────► PM
      │
      ▼
Durable audit record: run trace + evidence manifest + brief + PM decision   [Design]
```

**Evidence planning** is the one genuinely new stage. In the prototype the connector reads a curated directory and a relevance skill filters it. At enterprise scale that inverts: retrieving everything is not possible, so the system must decide which sources a question needs *before* retrieving, and record that decision. The plan is itself auditable output — "this brief did not consult support tickets" is a fact a reviewer needs, and it is different from "support tickets contained nothing".

**Policy checks join the validation layer rather than sitting in front of it.** A brief citing a document the requester may see but may not export, or resting on data whose retention window has closed, is a governance failure of exactly the same shape as an unresolvable citation: a deterministic property of the finished artifact. Putting it in `validate()` means it produces a `ValidationIssue` with a severity, appears in the same list, and blocks presentation by the same rule.

Three things deliberately do **not** change at enterprise scale: the fixed stage sequence, the single orchestrator, and the separation of the PM's decision from the recommendation.

---

# 3. Connector model

**[Built]** — the contract and one connector. **[Design]** — every enterprise source.

## 3.1 The retrieval-only contract

```python
class EvidenceSource(Protocol):
    @property
    def source_system(self) -> SourceSystem: ...
    def retrieve(self, request: EvidenceRequest) -> Sequence[EvidenceRecord]: ...
```

The boundary is enforced by the signature. `EvidenceRequest` carries scope — requester, product area, time period, labels, optional query, `max_records` — and never a question to answer. `EvidenceRecord` carries source material. There is no return channel for a conclusion, a ranking, or a quality judgment.

An empty query means "no keyword narrowing", which is the normal case for a curated corpus: retrieve everything and let the relevance skill decide. Requiring a query would push relevance judgment into the connector, where it does not belong.

Finding nothing must return an empty sequence, not raise. A silent gap becomes a visible one only if the caller can distinguish "none" from "failed".

`BaseEvidenceSource` owns the invariants no connector may forget: ids unique within a response, every record stamped with the source's own `source_system`, `max_records` respected, and the `source_systems` filter honoured.

**One caveat, stated because it is easy to over-read:** `EvidenceSource` is `runtime_checkable`, and `isinstance` therefore checks only that the named attributes *exist*. A class whose `retrieve` takes the wrong arguments still passes. Signature conformance is `mypy --strict`'s job. Treat an isinstance check as a smoke test, never as a guarantee that a source honours the contract.

## 3.2 The implemented connector

`LocalFileEvidenceSource` reads a directory recursively. Markdown, plain text, CSV and JSON; PDF is deliberately out of scope.

- **Ids are stable across runs.** `EV-<sha256(rel_path::locator::content)[:8]>`. The same file always produces the same id, so a citation in an older brief still resolves. Editing a file changes its id, which correctly signals that the cited text may no longer exist.
- **A CSV row is a record.** A 200-row ticket export becomes 200 citable records, not one. A PM verifying a claim should land on the exact ticket, not on a spreadsheet. JSON array elements are treated the same way.
- **Markdown is split on headings into excerpts**, with the full heading path as the locator (`§Constraints > Driver app`), suffixed when a path repeats. A bare leaf name is ambiguous the moment a document reuses it, and an ambiguous locator sends a reader to the wrong passage — worse than no locator.
- **A `case_manifest.json` supplies per-file metadata** (title, evidence type, owner, dates, product area, labels, permission scope). It is metadata *about* evidence and is never returned as evidence.
- **Failures degrade and are recorded.** An unreadable, empty, or unsupported file is skipped into `diagnostics.skipped` with a reason. As noted in §1.11, those diagnostics do not currently reach the brief.
- **Search is coarse** — keyword matching of the kind a Jira query does, plus product-area and label filters. Judging what is actually relevant is the relevance skill's job, and the number of records the query removed is counted so the filtering is not invisible.

**No vector database** (D11). Not justified at prototype corpus size, and it would make retrieval harder to inspect. Keyword and manifest-driven retrieval over explicitly identified files keeps every retrieval step auditable, which serves the product thesis rather than compromising it.

## 3.3 Why connectors are shared infrastructure, not agents

**[Design]** for everything below.

A connector is a piece of platform, owned centrally, used by every PM. It is not an agent, and the distinction is not stylistic:

| | Shared connector | Agent-per-source |
|---|---|---|
| Behaviour | Fixed, testable, same for every caller | Varies by prompt, model, and run |
| Credentials | Held once, centrally, rotated centrally | Multiplied across teams |
| Permission enforcement | One code path to audit | One per agent, each capable of being wrong differently |
| Failure mode | A named source returned nothing | Unclear which component decided what |
| Cost | A query | A query plus inference, per source, per run |

The decisive argument is the product's own: the property under test is verifiability. An architecture whose retrieval layer reasons cannot demonstrate that its reasoning layer is traceable, because a reader cannot tell which layer produced a given judgment (D8).

Consequences worth stating explicitly. **PMs never handle credentials.** A PM selects *scope* — which projects, which spaces, which dashboards — from what they are already entitled to see. **A connector is versioned and reviewed like any other shared library**, and a change to its normalization is a change to every brief produced afterwards, which is why `EvidenceRecord` ids incorporate content: a re-normalized record is a new record, and old citations correctly stop resolving rather than silently pointing at different text.

---

# 4. Jira scaling example

**[Design]** — no Jira integration exists.

Jira is the clearest illustration of why "how many connectors do we need?" is usually the wrong question.

**One Jira connection maps to one Jira site.** Project keys — say `LASTMILE`, `DRIVER`, `PAYMENTS`, `CHECKOUT`, `MARKETPLACE`, `SUPPLYCHAIN` — are **configuration inside that shared connection**, not separate connectors. Six product areas do not mean six integrations; they mean one integration and six scope configurations.

| Layer | Owned by | Holds |
|---|---|---|
| Connection | Platform / enterprise admin | Site URL, auth configuration, rate limits, retry policy, audit logging, health monitoring |
| Scope configuration | Product-area lead or enablement | Project keys, issue types, JQL scoping, field mapping to `EvidenceRecord`, default time windows, labels, terminology |
| Runtime context | The PM, per request | Product area, time period, optional filters, and their own identity |

Multiple Jira sites — a company with a legacy instance, or an acquisition — mean multiple centrally managed connections of the same connector type, not a new connector. This is what makes the model scale: adding the seventh product area is a configuration change, and adding the second site is an operations change, and neither is engineering work.

Two failure modes this structure is designed against. **Scope sprawl:** if a PM can point a connector at anything, briefs stop being comparable across teams and evidence coverage becomes unauditable. **Credential sprawl:** if scope configuration and credentials live at the same layer, every scope change becomes a security review.

Field mapping deserves specific care because it is where retrieval quietly becomes interpretation. Mapping a Jira issue's summary and description into `content`, its key into `source_id`, its browse URL into `source_reference`, and its `updated` into `updated_at` is normalization. Mapping story points into a "delivery effort" assessment is *not* — that is a `DimensionAssessment`, and it belongs to a skill, with a citation.

---

# 5. Permissions and delegated identity

**[Design]** — none of this exists in the prototype.

**The prototype has no permission model at all.** It is a local-file connector. `UserContext.permissions` is declared and never read. `EvidenceRecord.permission_scope` is populated from the manifest and never checked by anything. There is no authentication, no authorization, and no notion of a caller. Every file under the evidence root is retrievable by any process that can read the directory. This is acceptable only because the corpus is synthetic and the deployment is a single local process, and it must not be read as a simplified version of the design below — it is the absence of one.

## 5.1 The rule

**Retrieval executes under the requesting PM's own permissions. A PM must never see evidence through DecisionLens that they could not see directly in the source system.**

This is the single most consequential governance requirement in the product, because DecisionLens is an aggregator. A tool that reads ten systems and synthesises them is a tool that can leak from ten systems at once, and can do so in a form — a fluent, cited paragraph — that gives the reader no signal that anything was over-shared.

## 5.2 Delegated identity, not service identity

| Model | Behaviour | Verdict |
|---|---|---|
| Service identity (one privileged account reads everything, filtering applied afterwards) | Retrieval sees more than the user; correctness depends on a post-filter being right every time | **Rejected.** The failure is silent, and the blast radius is every user. |
| Delegated identity (on-behalf-of token; the source system enforces its own access control) | The source returns only what the user may see; DecisionLens never holds more than the user does | **Required.** |

Delegated identity means DecisionLens is not the enforcement point. Jira decides what a PM may read in Jira. That is correct: the source system is where the permission model actually lives, where it is maintained, and where it is audited. Any attempt to mirror it in the agent creates a second copy that will drift.

## 5.3 What this forces on the rest of the design

- **Two PMs asking the same question may legitimately get different briefs.** Support levels can differ, contradictions can be invisible to one and not the other. The brief must therefore record *whose* permissions it was built under, and the missing-evidence section must be able to say *"a source was consulted and returned nothing for you"* — distinct from *"no source covers this"*. `MissingEvidence.was_searched` already carries that distinction in the model.
- **Caching becomes permission-sensitive.** A cached response is keyed by case and skill today; any enterprise cache of *retrieved evidence* must be keyed by identity as well, or it becomes a permission-bypass channel. This is the sharpest interaction between §5 and §17, and cost pressure is exactly what makes it tempting to get wrong.
- **A brief is a derived artifact carrying the union of its sources' sensitivity.** Sharing a brief must be governed at least as tightly as sharing the most restricted document it quotes. Verbatim citation — the mechanism that makes the brief verifiable — is also the mechanism that makes it a copy.

---

# 6. Normalized evidence

**[Built]** — the shape. **[Design]** — the permission and classification metadata it will need.

`EvidenceRecord` is the shared shape every connector produces:

| Field | Required | Purpose |
|---|---|---|
| `id` | yes | Stable, human-readable (`EV-92455949`); appears verbatim in the brief |
| `source_system` | yes | Which system; stamped by the connector, verified by the base class |
| `source_id` | yes | The record's identity in that system |
| `source_reference` | — | Path, URL or record key — where a skeptical reader goes to check |
| `title` | — | What it is |
| `content` | yes, non-blank | The citable text. Blank is rejected: there is nothing to cite |
| `evidence_type` | yes | Metric, research, operational record, strategy doc, governance policy, experiment result, stakeholder input, prior decision |
| `created_at` / `updated_at` | — | Freshness inputs; staleness is arithmetic, not judgment |
| `owner` | — | Who is accountable for the source |
| `retrieved_at` | — | When this copy was taken |
| `product_area` | — | Scope |
| `permission_scope` | — | **Placeholder.** Populated but never enforced — see §5 |
| `labels` | — | Scope and filtering |
| `excerpts` | — | Verbatim spans with locators pointing *into* the record |

Two behaviours live on the record itself because they are primitives the rest of the system depends on: `contains(quote)` (the basis of programmatic citation checking) and `age_days(as_of)` (the basis of staleness).

**A record states what the source says. It carries no judgment about quality.** That is `EvidenceClassification`, produced separately by a skill and stored separately in the brief. Merging them would let an interpretation pass as a fact of the record — and given that a connector is trusted infrastructure while a skill is model output, that conflation would launder judgment into fact.

**[Design]** Enterprise records need three fields the prototype does not have: a **data classification** (§13), a **retention class** (§14), and a **permission descriptor** that is actually enforced rather than recorded (§5). All three are properties of the source, so all three belong to the connector, not the skills.

---

# 7. Analysis skills

**[Built]**

The approved set is closed: `relevance`, `classification`, `contradictions`, `missing_evidence`, `alternatives`, `recommendation`, `challenger`. Nothing else is a skill. `SKILL_NAMES` states the set in code.

Each skill declares five things — a name, a versioned prompt, a typed output model, the values rendered into the prompt, and its own hard requirements — and inherits everything else: calling, parsing, repairing, retrying, tracing. No skill can forget to record which model answered.

**The typed boundary.** A skill receives a `SkillContext` holding exactly a `DecisionRequest` and a tuple of `EvidenceRecord`. There is no provider on it and no method that fetches anything. A skill cannot call another skill; the orchestrator sequences them. That constraint is what keeps each step separately runnable and separately testable, which is what makes the reasoning auditable rather than merely fluent.

**Versioned prompts.** Every prompt is registered by name and version into a process-wide registry that refuses to overwrite — two prompts claiming the same name and version would make a trace ambiguous about which one ran. Rendering raises on a missing placeholder rather than emitting a prompt containing a literal `{evidence}`, which a model would answer anyway and nobody would notice until the output was wrong.

**Shared heuristics (D12).** The reading cues both arms rely on — stakeholder recall treated as measurement, seniority converting preference into fact, a stale figure quoted in prose, a "largest cause" claim true only of one segment, a blank field read as zero — live in one module (`prompts/heuristics.py`) that both DecisionLens and the baseline compose from, with a test asserting every block reaches both. They had drifted apart, which quietly made the baseline weaker than the arm it was measured against. Nobody decided that; it is what happens to duplicated text, which is why the fix is structural.

**[Design]** In an enterprise, skills are shared, versioned organizational assets with a proposal, review, and retirement path — the subject of §02 rather than this document. The governance-relevant point here is that a skill's *hard requirements* are code, so a skill change that weakens a guarantee is visible in a diff and catchable by a test, in a way that a prompt-only change never is.

---

# 8. Orchestrator

**[Built]**

Stage sequencing is covered in §1.1. The governance-relevant properties:

**Partial failure.** Any stage from `relevance` to `challenger` may fail without stopping the run. The failure is recorded in the trace with its message and produces a `stage_failed` issue whose text says the section is *absent because it failed*. Without that, a stage that crashed and a stage that found nothing produce identical-looking briefs, and the difference decides how far the brief can be trusted. Failure of `contradictions`, `recommendation` or `challenger` is an **error** rather than a warning, because a recommendation that was never challenged has not been through the process this product describes.

**Retry limits.** One re-prompt per skill, naming the broken requirement. `allow_retry=False` disables it entirely. There is no retry at the provider level and no retry of the run. Bounded by construction: at most fourteen model calls for a seven-stage run, and that ceiling is a property of the code rather than of a budget check.

**Timeouts.** Per-skill, injected, enforced in the provider base class and passed to the live transport. A skill that times out is a failed stage, not a failed run.

**The deliberate absence of open-ended loops.** There is no condition under which the orchestrator runs a stage a third time, no planner deciding what to do next, and no mechanism for the system to keep working until it is satisfied. A system that retries until the output looks good is a system that will eventually produce output that looks good for the wrong reason — and the bundled demo, which currently ships blocked by its own challenger, is the standing demonstration that this is not done here.

**Reproducibility hooks.** `as_of` (the date staleness is measured against) and `clock` (the run timestamp) are injected. A run is reproducible only if the things that vary with wall-clock time are inputs, not ambient state.

---

# 9. Recommendation challenger

**[Built]** — see §1.4 for the mechanism. This section states why the questions are the ones they are.

The challenger exists because the failure this product targets is not fabrication — modern models cite fairly well, and the evaluation measured 100% citation validity against a baseline's 99.8%, which is not a distinction. The failure is a *well-cited, internally consistent, confidently-stated recommendation that quietly rests on a preference, a contested figure, or an option nobody generated.* That is invisible to citation checking, because every individual citation is fine.

| Question | The failure it targets |
|---|---|
| `claims_supported` | Support asserted beyond what the cited span actually says |
| `contradictions_considered` | A side chosen silently from a live disagreement |
| `preference_as_evidence` | A senior stakeholder's view carried through the workflow wearing the authority of a finding |
| `non_ai_considered` | AI assumed rather than chosen — the specific bias of a tool built to encourage AI adoption |
| `no_build_considered` | Action assumed to beat inaction, when inaction is frequently correct |
| `overconfident` | Support level exceeding what the evidence carries |
| `what_could_make_it_wrong` | A recommendation with no falsifier |
| `what_to_test` | A commitment with no cheaper prior step |

`preference_as_evidence` produces the most useful single output of the stage: a `ClaimReclassification` moving a claim from `fact` to `stakeholder_opinion`, applied before validation runs. `non_ai_considered` and `no_build_considered` are the two that are counted rather than judged, and the override preserves the model's own text underneath so a reader can see both what it said and why it was overruled.

**The asymmetry is the point.** The challenger can lower confidence and cannot raise it. This is not caution for its own sake — it is a structural guarantee that adding a reviewing stage cannot make a brief more confident than the evidence supports, whatever the reviewer says. An attempted raise is discarded *and reported*, so the attempt itself is visible.

**Measured behaviour, honestly.** Across eleven evaluation cases, DecisionLens overstated support 0 times against the baseline's 1, and understated it on 6 of 11 against the baseline's 1. Read together, that is not a system that judges confidence well; it is a system biased low, which happens to be the safer direction. On `checkout_error_rate` — built so that `strong` support is genuinely earned — both arms said `moderate`. A decision-support tool that always hedges transfers the judgment straight back to the reader. §04 records this as a finding against the design, not for it.

---

# 10. Validation and guardrails

**[Built]** — the full table is in §1.7.

The governance argument for this layer is one sentence: **the checks are deterministic and separate from the model, so a reviewer can verify a brief without trusting the thing that produced it.**

That separation is enforced structurally, not by intention:

- **Citation spans are checked programmatically** against retrieved source text by string containment. No model is asked whether a citation is good.
- **Required sections, the non-AI alternative, and the no-build alternative are enum and set checks**, not prompt instructions. They are also enforced twice — once inside the `alternatives` skill, which re-prompts and then fails, and once over the finished brief, because the skill's check is skipped when the stage failed and the brief is the thing a person acts on. A real run recommended `ALT-03` out of a set of no alternatives at all; `dangling_alternative` exists because of it.
- **Assumption/fact separation** reduces to a checkable rule: a claim typed `fact` with no citation is an assumption that has been promoted. The label is the whole difference between weighing a finding and weighing a guess, so it is an error rather than a note.
- **`validate` is pure.** Running it twice on the same brief returns the same issues and changes nothing. The single mutating function is called explicitly by the orchestrator and writes its reason into the brief.

**What this layer cannot do.** It checks that a brief is internally honest about its evidence. It cannot check that the evidence is true, that the corpus was complete, or that the question was the right one. Traceability over an incomplete corpus still yields confident, well-cited, badly scoped conclusions — the missing-evidence stage makes gaps visible and partially compensates, but does not solve it.

**[Design]** The enterprise additions are policy checks of the same deterministic shape: data classification permitted for this output, retention window still open, jurisdiction constraints satisfied, mandatory review triggered for named decision categories. They join `validate()` rather than wrapping it, so they produce the same `ValidationIssue` type, appear in the same list, and block presentation by the same rule.

---

# 11. Audit trace

**[Built]** — contents in §1.10. This section states what must be reconstructable and what currently is not.

For a decision that turns out badly, the questions a reviewer will actually ask:

| Question | Answerable today? |
|---|---|
| What was asked? | **Yes** — the full `DecisionRequest` is embedded in the brief |
| What evidence was used? | **Yes** — every retrieved record, verbatim, with source reference and retrieval timestamp |
| Which model produced each stage, from which provider, under which prompt version? | **Yes** — per `RunStage` |
| Was any stage replayed rather than called? | **Yes** — the stage reports `provider = cached-demo` and `model = recorded-replay`, plus a warning naming the model and date the response was recorded from. (`ModelResponse.is_cached` is not itself copied into `RunStage`; the provider identity and the warning are what carry it.) |
| Which stages failed, and why? | **Yes** — `error` per stage, surfaced as a `stage_failed` issue |
| What was corrected mechanically along the way? | **Yes** — citation repairs, id resolutions and verdict overrides all become warnings |
| Which checks failed on the finished brief? | **Yes** — `validation_issues`, with stable codes |
| Was confidence lowered, and on what grounds? | **Yes** — `support_reduced`, plus the reason written into `support_basis` |
| What did the PM actually decide? | **Yes**, if recorded — `PMDecision`, separate object |
| Exactly which prompt *text* ran? | **Yes** — `RunStage.prompt_fingerprint` records the content hash of the prompt, not only its version (§1.9) |
| What did the connector skip or filter out? | **No** — diagnostics exist and are not surfaced (§1.11) |
| Who was the requester, and under whose permissions? | **No** — there is no identity (§5) |
| What did previous runs of this question produce? | **No** — there is no persistence (§14) |

The four "no" rows are the honest boundary of the current audit story. Three of them are small pieces of wiring; the fourth is a whole subsystem.

**[Design]** In an enterprise the trace is written to durable, append-only storage alongside an evidence manifest (ids, source references, retrieval timestamps and content hashes rather than full text, so the record stays smaller than the corpus and does not itself become a data-classification problem), the rendered brief, and the PM's decision. Retention follows §14.

---

# 12. Identity and access

**[Design]** — the prototype has none of this. See §1.11 and §5.

To be unambiguous: DecisionLens today authenticates nobody, authorizes nothing, and has no concept of a session. `record_pm_decision` is called by the local interface with `decided_by="pm-local"`, a hardcoded string. Every statement below is a specification.

## 12.1 Three identities, kept distinct

| Identity | Used for | Never used for |
|---|---|---|
| **User (delegated)** | All evidence retrieval, on behalf of the requesting PM | Platform operations |
| **Service** | Connector health checks, schema discovery, rate-limit management, telemetry | Retrieving evidence into a brief |
| **Administrative** | Connection configuration, credential rotation, scope definition | Anything in a PM's request path |

The rule that matters: **no evidence reaches a brief through a service identity.** The moment retrieval runs as a privileged account, correctness depends on a downstream filter being right every time, and its failure is silent (§5.2).

## 12.2 Authentication and authorization

Authentication is enterprise SSO with an on-behalf-of token exchange per connector. DecisionLens holds no long-lived user credentials and no per-PM secrets. Tokens are scoped per source and per request, and are never written to the trace, the brief, or a log — the existing prototype discipline around the API key (excluded from `repr` and `model_dump`, only ever shown as four characters) is the pattern to extend, not to replace.

Authorization has two layers with different owners. **Source-system authorization** is delegated entirely to the source and is not mirrored. **Product authorization** — who may run DecisionLens, against which product areas, and who may see which briefs — is DecisionLens's own, and is the smaller of the two by design.

## 12.3 The aggregation problem

Worth naming separately because it is the risk that is specific to this class of product. Every individual retrieval can be correctly authorized and the resulting brief can still be an over-share: a synthesis of ten permitted documents can expose a conclusion none of them stated, to an audience broader than any of them. Delegated identity solves *retrieval*. It does not solve *distribution*. §5.3 and §13 carry the consequences.

---

# 13. Data classification and PII

**[Design]** — nothing here is implemented. There is no classification, no detection, and no redaction anywhere in the prototype. The bundled corpus is synthetic and fictional, which is why no such control was needed to ship it, and is not an argument that one is unnecessary.

## 13.1 Handling by classification

| Classification | Retrieval | Appears in brief | Brief handling |
|---|---|---|---|
| Public | Permitted | Verbatim | Unrestricted |
| Internal | Permitted under delegated identity | Verbatim | Brief inherits Internal |
| Confidential | Permitted under delegated identity | Verbatim, flagged | Brief inherits Confidential; sharing controlled |
| Restricted / regulated | Blocked by default; explicit per-source enablement | Not quoted | Referenced by existence only, never by content |

The brief inherits the highest classification of anything it quotes. Verbatim citation is the mechanism that makes the brief verifiable and is therefore also the mechanism that makes it a copy; the two cannot be separated, so the classification must travel.

## 13.2 PII

The sources most valuable for product decisions are the ones most likely to contain PII: customer feedback, support tickets, and session records. A verbatim quote from a support ticket is exactly the artifact that carries a customer's name, address, order number, or phone number into a document that will be pasted into a planning deck.

Three rules follow:

1. **Redaction happens in the connector, before normalization.** If PII reaches an `EvidenceRecord`, it has already reached the prompt, the provider, the trace, and the brief. There is no later point at which removing it is meaningful.
2. **Redaction must be visible and stable.** A redacted span is replaced with a marked placeholder, not deleted. Silent removal changes the meaning of a quote — *"the customer said the driver left it at [REDACTED]"* is honest; the same sentence with the location quietly dropped is not. Stability matters because citation resolution is string containment: the text a skill quotes must be the text in the record, so redaction must occur before any quote is taken and must be deterministic across runs.
3. **What was redacted is recorded, not the values.** A count and category per record, in the trace, so a reader knows a passage was altered.

**Interaction with citation repair (§1.6).** Repair snaps a near-verbatim quote onto the *record's* text. Because redaction is applied to the record before any skill sees it, repair can only ever produce redacted text. If redaction were applied later, repair would become a mechanism for reconstructing redacted values from the original — which is a good reason for the ordering to be enforced at the connector boundary rather than left to convention.

## 13.3 What goes to the model provider

Every retrieved record's full content is placed into skill prompts. That is inherent to the design: verifiability requires the model to see the actual text, not a summary. So the provider boundary is a data-egress boundary, and it needs the corresponding controls — zero-retention terms, no training on submitted data, regional processing where required, and classification limits enforced *before* the request is built rather than by trusting a vendor setting. The vendor-neutral provider abstraction is what makes an enterprise gateway substitutable here without touching a single skill.

---

# 14. Lineage, freshness, and retention

**[Built]** — lineage and freshness, partially. **[Design]** — retention entirely.

## 14.1 Lineage

Traceable today, end to end: a statement in a brief carries a `Citation` (evidence id, verbatim quote, locator); the id resolves to an `EvidenceRecord` carrying `source_system`, `source_id`, `source_reference` and `retrieved_at`; the quote is verified by string containment against that record's content; and the id itself is a hash of path, locator and content, so edited source text produces a different id and old citations correctly stop resolving rather than silently pointing at changed text.

That last property is the one people underestimate. **A citation that resolves against changed text is worse than a citation that fails**, because it reads as verified.

## 14.2 Freshness

`created_at` and `updated_at` come from the source. Age is computed against an injected `as_of` date, never estimated by the model — the prompt explicitly forbids guessing at it, because a model writing "about a year old" is inventing a number that a subtraction already answers. A record at or beyond 365 days is marked stale, its derived support level is capped at `low`, and the count of stale sources is reported as a note on the brief.

The threshold is a policy judgment, not a discovered fact: a year covers a full planning cycle, so anything beyond it predates the current set of assumptions. **[Design]** In an enterprise it belongs in configuration and should differ by source type — a governance policy ages very differently from a weekly metric.

## 14.3 Retention

**Nothing is retained.** Briefs are written to `out/` and that directory is gitignored. There is no store, no index, no run history.

**[Design]** Three artifacts with three different retention classes:

| Artifact | Retention driver | Note |
|---|---|---|
| Run trace | Audit obligation | Metadata and hashes, not evidence content — keeps the audit record outside the classification perimeter of the evidence |
| Decision brief | Business record; inherits classification of what it quotes | Contains verbatim source text and is therefore a copy, subject to the source's own retention |
| PM decision | Business record; longest of the three | The accountability artifact, and the one whose value grows with age |

The awkward case is deliberate to name: a brief quoting a record whose retention window has since closed is now a copy of data that should have been deleted. Either briefs inherit the shortest retention of anything they quote — which destroys the audit trail for exactly the decisions most worth auditing — or evidence content is stored only as hashes and the brief becomes unverifiable after source deletion. There is no free answer. The position taken here is the second, with the trace retaining hashes and references so that *"this claim cited a record that no longer exists"* remains provable even when the text does not.

---

# 15. Prompt and model versioning

**[Built]** — see §1.9 for the mechanism, D14 for the incident.

The governance claim is narrow and worth stating precisely: **a brief is reproducible only if the prompt version and model version are pinned and recorded, and a version label is only trustworthy if something derived from the content checks it.**

The second half of that sentence was learned rather than designed. Two prompts were edited without their versions being bumped; every subsequent run replayed answers to wording that no longer existed; two of eight shipped stages were stale and nothing said so. The fix was not a stricter process — it was a fingerprint, because a hash of the text cannot be forgotten the way a version bump can.

What is pinned per stage: provider, model, prompt version, **prompt fingerprint**, token usage, latency, whether the answer was replayed, and any warning the provider raised about how it was obtained. What is not pinned: temperature, which is 0.0 by default and is not currently recorded — a real if minor reproducibility gap, and the only one remaining here.

**[Design]** Enterprise requirements on top: a model version pinned per prompt version rather than per deployment, since a silently upgraded model invalidates every comparison made against outputs from the previous one; a deprecation window during which both versions remain callable; and a rule that evaluation results are quoted only alongside the model and prompt versions they were measured against. `evals/frozen/prompts_at_case_design.json` is the prototype's version of that discipline: the prompts as they stood when the held-out cases were written, frozen so the claim "ten of eleven cases post-date the prompts" is checkable rather than asserted.

---

# 16. Human approval

**[Built]** — this is the one governance boundary the prototype actually implements.

The product's position: **the PM decides, and the PM's decision is recorded separately from the recommendation.**

Implemented as follows:

- `DecisionLens.run` returns a `DecisionBrief` containing a `Recommendation`. It records no decision, and there is no code path by which it could.
- `record_pm_decision` is a **separate function**, called by a person afterwards, producing a separate `PMDecision` object. The separation is the mechanism: keeping the two apart is what makes disagreement between them *measurable* instead of invisible.
- `PMDecision` requires `decision` and `decided_by`, and a model validator **refuses to construct** a decision that disagrees with the recommendation without an `override_reason`. The disagreement is the signal worth capturing, so recording it without its reason is not permitted.
- `DECISION_OWNER_NOTICE` is a field on every brief with a default, rendered on every output: *"DecisionLens supports the decision process. The product manager remains accountable for the final decision."*
- The interface presents this as a form asking *"What did you decide?"*, *"Why?"*, and *"Does this match the recommendation?"* — **not an accept button.** An accept button would collapse the distinction the whole design rests on.

## 16.1 What DecisionLens may never do autonomously

Commit roadmap or budget. Change priority in a system of record. Write to any source system — the connector contract has no write path at all, which is a structural guarantee rather than a policy. Approve an investment. Close a decision. Record a decision on a PM's behalf. Present a brief carrying blocking validation errors as though it were clean — the CLI exits 2 precisely so that a script cannot mistake one for the other.

## 16.2 The gaps

`decided_by` is a hardcoded `"pm-local"` string, because there is no identity (§12). The decision is rendered into a downloadable copy of the brief and **is not persisted anywhere**. A decision that is not stored cannot be aggregated, which is why §21 is a design section rather than a built one. This is the largest gap between the position stated here and the mechanism supporting it, and it is a persistence gap rather than a design gap.

---

# 17. Cost controls

**[Built]** — the measurements and the opt-in boundary. **[Design]** — every control.

## 17.1 The measured cost of the workflow

A seven-stage workflow re-sends the evidence corpus to each stage. That is the price of stage isolation and it is not small. Measured across the eleven evaluation cases, from the recorded runs in `evals/recordings/`:

| | DecisionLens (7 stages) | Baseline (1 call) | Ratio |
|---|---|---|---|
| Input tokens | 1,420,887 | 208,007 | 6.8× |
| Output tokens | 906,659 | 513,731 | 1.8× |
| **Total** | **2,327,546** | **721,738** | **3.2×** |
| Per case, mean | ≈211,600 | ≈65,600 | 3.2× |

These are token counts reported by the provider and recorded per stage; no price is quoted here because rates change and a stale figure in a governance document is worse than none.

**This is the honest cost of the design.** The input multiple is where it lives: the corpus is re-sent seven times. What 3.2× buys, measured over the same eleven cases: 1,451 resolving citations against 969, 134 options against 79, and zero overstatements of support against one. Whether that is worth it is a real question, and §04 does not resolve it — the measured advantages are restraint on a case built to induce overclaiming, more options, and more citations, against a citation-validity difference of 100% versus 99.8% that is not a difference at all.

## 17.2 What exists

- **The default provider is free.** Replay costs nothing and reaches no network.
- **Going live requires two explicit settings.** A key in the environment is not consent to spend money.
- **Call count is bounded by construction.** Seven stages, at most one retry each.
- **Every stage reports its usage** into the trace, which is why the table above could be computed at all.

## 17.3 What does not exist

No per-run budget. No per-user or per-org budget. No spend telemetry. No pre-flight cost estimate enforced as a limit (the recorder computes a size preview, but it is a preview, not a gate). No prompt caching of the repeated evidence block. Nothing stops a large corpus from producing an expensive run.

## 17.4 The design, and the constraint on it

**[Design]** Per-run ceilings that fail the run rather than truncating the evidence, because a silently shortened corpus produces a brief whose gaps nobody can see. Per-user and per-team budgets at the gateway. Prompt caching of the evidence block, which is the single highest-leverage change available given a 6.8× input multiple. Stage-level opt-out for cheap re-runs, with the skipped stages reported as `stage_failed`-equivalent absences rather than silently omitted.

And one control that must **not** be built: caching *retrieved evidence* across users. It is the obvious saving and it is a permission-bypass channel (§5.3). Cost pressure is exactly the force that makes that mistake attractive.

---

# 18. Observability

**[Built]** — per-run introspection. **[Design]** — everything operational.

## 18.1 What a run tells you today

Per stage: provider, model, prompt version, input and output tokens, latency, error, and warnings. Per brief: every validation issue with a stable code and severity, every mechanical repair, every stage note. The rendered Markdown prints the trace as a table and the provider warnings as sentences beneath it, because *"the prompt has changed since this response was recorded"* is a sentence, and squeezing it into a table cell is how it stops being read.

Stable `ValidationCode` values exist specifically so failures can be counted by kind rather than by prose.

Two caveats. Latency is meaningless in replay mode — sub-millisecond stages round to zero, so a cached run reports 0 ms total. And **connector diagnostics do not reach the brief** (§1.11): the connector counts skipped and filtered records and nobody ever sees them.

## 18.2 What is missing

**[Design]** There is no logging framework, no metrics emission, no health checking, and no telemetry of any kind. A production deployment would need:

| Signal | Why |
|---|---|
| Validation-issue rate by code | The primary quality signal. A rising `citation_span_missing` rate is a model or prompt regression; a rising `stage_failed` is an availability problem |
| Challenger verdict distribution | A collapse in `fails`/`concern` rates means the challenger has stopped challenging, which looks identical to improvement |
| Support-level distribution against ceilings | The measured bias is toward understating (§9); drift in either direction matters |
| Stage failure rate and latency, by stage | Degradation is per-stage, so telemetry must be too |
| Cache-drift warnings | The D14 class of defect, now detected — and worth alerting on rather than only printing |
| Connector health, coverage, and permission-denial rate | A connector silently returning less is the most dangerous connector failure, because the brief still looks complete |
| Per-run and per-user cost | §17 |
| Override rate | §21 |

**Never logged:** credentials, tokens, or retrieved evidence content. The prototype's existing discipline — the API key excluded from `repr` and `model_dump`, shown only as four characters — is the standard to extend.

**Evaluation telemetry in production** is the harder half. The offline harness scores against authored ground truth, which does not exist in production. What can be measured live: deterministic checks (they need no ground truth), override rate and reason, and — the strongest available signal — whether decisions made on briefs held up, which is only observable months later and only if PM decisions are stored (§16.2, §21).

---

# 19. Incident handling

**[Design]** — no incident process exists; nothing has been run in production.

Three incident classes, because they have genuinely different shapes.

## 19.1 A connector returns evidence the requester was not entitled to see

The most severe class, because the leak is durable — it is already quoted verbatim in a brief a person has read.

Containment: disable the connector, not the product; DecisionLens degrades to the remaining sources with a visible note, which is the behaviour the orchestrator already has for a dead source. Assessment: the trace names every record retrieved and every run that touched the affected source, so the blast radius is enumerable rather than estimated — **this is what the audit trace is for**. Remediation must cover the derived artifacts, not just the source: every brief quoting an affected record, and everywhere those briefs were shared. Recovery requires a permission-enforcement fix at the connector plus a regression test with a fixture user who must not see a fixture record.

## 19.2 A model degrades

Rarely a hard failure; usually a quality drift. The detectable signature is a shift in the observability signals in §18.2 — validation-issue rates, challenger verdict distribution, support-level distribution — against a pinned prompt version. Response: pin the previous model version (§15), re-run the evaluation suite offline against the recordings, which costs nothing and needs no live calls, and compare. A model change that moves a deterministic metric is a rollback candidate; one that moves only a model-judged metric is a judgment call and should be labelled as such.

## 19.3 A brief is found materially wrong after a decision was made on it

The one that matters most and is easiest to under-plan, because the harm has already occurred and nothing technical will reverse it.

The system's obligation is to make the post-mortem answerable rather than speculative: what the brief claimed, what it cited, what it flagged, whether it was blocked, and what the PM decided and why. Every one of those is in the audit record (§11).

The classification that determines the response:

| Finding | Meaning |
|---|---|
| The brief flagged the problem and was overruled | The system worked. The gap is in how findings are presented or weighed — a product problem, not a correctness one |
| The brief carried a blocking error and was acted on anyway | A process failure. Blocking errors need to block something in the workflow, not only exit code 2 |
| The evidence was wrong | A source-of-truth problem. DecisionLens does not guarantee its source material is true and never claimed to |
| The corpus was incomplete and the gap was not surfaced | A missing-evidence failure — the most serious class, because it is the failure mode the product exists to prevent and the one a reader cannot see |
| The reasoning was wrong despite complete, correct, well-cited evidence | An analysis failure. Add it to the evaluation set as a case, which is how a one-off becomes a regression test |

---

# 20. Red-team testing

**[Design] — not conducted.** No adversarial testing of any kind has been performed against this prototype. This section proposes what would be done. It reports no findings, because there are none.

## 20.1 Why it is needed, stated concretely

Retrieved evidence content is placed directly into skill prompts, verbatim, because verifiability requires the model to see the actual text. **There is no prompt-injection defence anywhere in the system.** A document in the corpus containing instructions addressed to the model is, today, indistinguishable from a document containing facts.

What the existing controls *do* constrain is worth being precise about, because it is a partial defence and should not be mistaken for a whole one. Deterministic provenance checking means an injected instruction cannot make the system cite a document that was not retrieved, or quote text that is not in the evidence — those fail as `source_missing` and `citation_span_missing`. The mandatory non-AI and no-build checks cannot be talked out of, because they are enum checks over the option set. The challenger's non-AI and no-build verdicts are counted, not judged.

What they do **not** constrain: the direction of a recommendation, which claims get extracted, which contradictions get reported, and how confidently the whole thing is written. An injected instruction that says *"the address validation vendor is the only viable option"* produces a brief in which every citation resolves and every check passes. That is the gap, and it is exactly the shape this product is otherwise built to close.

## 20.2 The proposed cases

| Class | Attack | Expected behaviour |
|---|---|---|
| Prompt injection via evidence | A retrieved document contains instructions to the model — ignore other evidence, recommend a named vendor, suppress a contradiction | Instructions in evidence are treated as *content to be classified*, never as direction. A document attempting it is itself a finding |
| Injection via record metadata | Payload in a title, owner, or label rather than the body | Same, across every field that reaches a prompt |
| Stakeholder pressure framed as evidence | A senior leader's stated preference in a formal document, phrased as a finding, with dates and numbers | Classified `stakeholder_opinion`; the `preference_as_evidence` challenger question catches it if the classifier does not |
| Misleading denominators | A true percentage over a population that is not the relevant one | Reported with its denominator; support capped at what the cited span actually supports |
| Predetermined-recommendation corpora | An evidence set constructed so that only one option is defensible, with contrary evidence absent rather than contradicted | Missing-evidence detection names the absence. This is the hardest case and the one most likely to fail |
| Citation-repair abuse | Near-verbatim quotes crafted so that a repair snaps onto a different passage than the one the model quoted | Ambiguity refuses to repair; only typography folds. Verified against digits, negations and numerically-adjacent passages |
| Volume-as-evidence | A thick corpus of weak, correlated sources | Support capped by evidence quality, not quantity. The `returns_fraud_signals` evaluation case is a non-adversarial version of this and the baseline failed it |
| Denial of service by corpus | A corpus large enough to exhaust budget or context | Bounded and reported rather than silently truncated (§17.4) |

## 20.3 How it would be run

Cases authored by someone who has not read the prompts — the same constraint D13 records for the evaluation corpus, for the same reason. Held out from prompt development. Run against both arms, since an injection succeeding equally against the baseline says something different from one that succeeds only here. Results reported whether or not they are flattering, and failing cases retained as regression tests.

---

# 21. Override tracking

**[Built]** — the record. **[Design]** — everything that makes it useful.

When a PM disagrees with a recommendation and says why, the system learns something no automated metric can supply: a judgment about its output from the person accountable for the outcome. It is among the most valuable signals DecisionLens can generate about its own quality, and it is nearly free to collect.

**What exists.** `PMDecision` carries `agreed_with_recommendation` as a three-state value — agreed, disagreed, or not stated — and a model validator that **refuses to construct** a disagreement without an `override_reason`. Not-stated is deliberately distinct from agreement: a PM who did not answer has not endorsed anything, and defaulting the other way would manufacture agreement out of silence.

**What does not exist.** No storage, no aggregation, no analysis. A recorded decision is rendered into a downloadable copy of the brief and then it is gone. Nothing counts overrides, correlates them with anything, or feeds them anywhere.

**[Design]** With persistence, the questions this data answers:

| Signal | What it indicates |
|---|---|
| Override rate over time | A falling rate is ambiguous — improving quality, or growing deference. It must be read against the *reasons*, never alone |
| Override reason, categorised | The actionable field. Missing context, wrong classification, unacceptable option, evidence the PM knew and the system could not reach, or a judgment the PM simply made differently |
| "Evidence I have and the system does not" | A **connector coverage gap**, reported by the person best placed to notice it. Arguably the highest-value item in this table, and it is routed to platform work, not to prompt work |
| Overrides concentrated on one skill | A skill quality problem, localisable because stages are separate |
| Overrides concentrated in one product area | A configuration or corpus problem, not a model problem |
| Agreement with a later-wrong decision | Agreement is not correctness. A brief that was agreed with and turned out wrong is more diagnostic than either signal alone |

**Two cautions.** A high override rate is not a failure; a tool that is never overridden has either become invisible or has stopped being challenged, and the second is what this product is built to prevent. And override data must not be used to evaluate the PM — the moment it is, the reasons stop being honest, and the honest reasons were the whole value.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [02 — Ecosystem and Adoption](02-ecosystem-and-adoption.md)
- [04 — Evaluation](04-evaluation.md)
- [05 — Decision Log](05-decision-log.md)

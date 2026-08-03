# 02 — Ecosystem and Adoption

> **STATUS: design document.**
> **Nothing described here is built except DecisionLens itself.** The gateway, the connectors,
> the skill registry as an organisational institution, the configuration layers, the curriculum,
> the support model and the measurement programme are **designs**. Where something would have to
> be built, this document says so in place rather than in a footnote.
>
> No adoption statistic, cost figure, or timeline appears here. None has been measured. No access
> to any Walmart system was used at any point and no observation about any real organisation's
> internal behaviour is asserted. Claims about how organisations behave are labelled
> **[Product judgment]** or **[Assumption]** in the convention of
> [01 — Product Strategy](01-product-strategy.md).

**Purpose.** Describe how an organization moves product managers from little or no AI use to effective, responsible adoption — the tools, agents, reusable skills, data, knowledge, governance, training, and measurement that surround DecisionLens. DecisionLens is one component of that ecosystem, not the ecosystem itself.

---

## What exists, and what is proposed

| | |
|---|---|
| **Built and runnable** | DecisionLens: one orchestrator, seven analysis stages with versioned and fingerprinted prompts, one connector over synthetic local files, deterministic validation, a strong single-call baseline, an evaluation harness with eleven cases. See [README](../README.md) and [04 — Evaluation](04-evaluation.md). |
| **Designed, not built** | Everything else in this document. |

The distinction matters more than it looks. Three of the mechanisms this document uses to argue
the organisational case — versioned prompts with content fingerprints, a retrieval-only connector
contract, and a run trace that pins prompt and model version — are implemented in the prototype at
single-process scale. That is not the same as an enterprise capability, but it does mean the
organisational argument rests on a mechanism that has been made to work rather than on an
assertion that it could be. Where that is the case, this document says which file carries it.

---

## The argument in brief

1. Adoption stalls at the boundary of consequence because verifying consequential AI output is
   expensive (01). An ecosystem that only distributes tools and teaches prompting does not touch
   that cost.
2. So the ecosystem's job is to make verification cheap and to make the artefacts of verification
   **shared and durable** — skills, connectors, evidence, and decision records that outlive the
   PM who created them.
3. That forces centralisation in three specific places — model access, connectors, and analysis
   skills — and forces decentralisation in one: the product knowledge that makes a query
   meaningful.
4. It forces a training programme aimed at **evidence interrogation, not prompt technique**.
5. And it forces a measurement programme that refuses raw usage volume as its headline number.

---

## 1. AI-native maturity stages

A stage model is only useful if a stage can be assigned from artefacts rather than from
self-report. Each stage below is defined by **what you would see a PM do**, and by the artefact
that would show it. Adjectives like "confident" or "fluent" are deliberately absent: they are not
observable and they are what makes maturity models unfalsifiable. **[Product judgment]**

| Stage | Observable behaviour | Artefact you could inspect | Blocker holding them here | What moves them up |
|---|---|---|---|---|
| **S0 — No use** | AI is not open during working hours. Analysis is done by reading source documents directly, or not at all. | Absence: no AI output in any deliverable. | Access, policy uncertainty, or a belief that use is discouraged. Rarely skill. | Provisioned access with a *written* permitted-use statement. Silence on policy reads as prohibition. **[Product judgment]** |
| **S1 — Assisted drafting** | Pastes a draft PRD, an email, or a set of notes into a chat window. Rewrites the output by hand. Never cites it in a review. Uses AI for tasks where they already know the answer and would notice an error. | A PRD whose prose changed style between revisions; no AI artefact retained. | Nothing is blocking this stage — it is *stable*. Errors are cheap, the author is the checker, and there is no reason to progress. | Not exhortation. A task where the verification cost is genuinely lower with AI than without. That is the product problem (01), not a training problem. |
| **S2 — Structured analysis** | Re-uses a saved approach rather than improvising each time: a shared skill, a template, a standard question set. Output has a consistent shape across PMs. Still pastes evidence in by hand. | Two PMs' analyses of different problems that share a structure neither invented. | No shared skills to reuse (§4), so every PM re-derives their own approach and quality tracks individual craft. | A skill catalogue with versioned, tested entries — and connectors, so evidence stops being pasted. |
| **S3 — Evidence-grounded decision support** | Brings a brief to a decision review in which every material claim resolves to a source someone else can open. Opens the missing-evidence list first. Argues with the tool: rejects a recommendation and records why. Asks for the no-build option to be taken seriously. | A decision brief with resolving citations, a recorded PM decision distinct from the recommendation, and a written override reason. | Evidence access and permission fidelity (§5, §6). Also the honest one: the PM must be willing to have their reasoning inspected. **[Assumption]** | Connectors, an area configuration that makes retrieval relevant (§8), and a review culture in which citing a source beats citing seniority. |
| **S4 — Measured decision improvement** | Decisions carry a stated confidence, a named basis, and an exit condition — and someone actually returns on the exit condition. Retrospectives cite the brief rather than reconstructing from memory. Reversals are separated into "right on the evidence then available" and "poorly reasoned at the time". | A scheduled review that references the decision record and compares outcome to the pre-registered expectation. | The organisation has no habit of returning to a decision, and no store of prior decisions to return to (§6). This is a management-practice gap, not a tooling gap. **[Product judgment]** | Decision records as a first-class retrievable source, and a leadership expectation that exit conditions get reviewed. §15. |

Three things this model is not:

- **Not a ladder everyone must climb.** Most product work is correctly served at S1. A PM who
  drafts with AI and never uses it for an investment decision is not failing; they may have no
  decision that warrants S3. Pushing the whole population upward is how a programme generates
  volume without value (§14).
- **Not a per-person score.** Stage is a property of a *decision*, assigned per artefact. The same
  PM will be at S1 on a launch email and S3 on a portfolio call in the same week.
- **Not a claim about how any real population is distributed.** No distribution is asserted here
  because none has been measured.

---

## 2. Tooling layer

The design decision that governs this section: **DecisionLens is not, and must not become, a
general-purpose PM copilot.** [01](01-product-strategy.md) rules it out of scope and D1 in
[05](05-decision-log.md) records why the original broad-assistant concept was rejected. The
ecosystem consequence is that the tooling layer is deliberately plural — PMs use several tools,
each narrow, rather than one that claims everything.

| Layer | What a PM does with it | Status | Why not DecisionLens |
|---|---|---|---|
| General assistant (chat) | Drafting, summarising, rewriting, brainstorming, learning a domain | Assumed already procured; not part of this design | These are low-verification tasks. A second chat window competing for them adds nothing and splits attention. |
| Enterprise search | Finding a document whose existence you suspect | Assumed procured or a platform dependency | Solves retrieval, not interpretation. It returns documents; it does not say which claims are load-bearing. |
| Document / spreadsheet copilots | Faster production of the deliverable | Assumed procured | Optimises drafting speed, which is exactly the S1 plateau. |
| BI and analytics | Answering a well-formed quantitative question | Existing platform | DecisionLens reads *from* these as evidence; it does not replace them. |
| **DecisionLens** | Producing a challengeable, source-resolved brief for one consequential decision | **Built** (prototype, synthetic evidence) | — |
| Model gateway | Nothing directly — it is infrastructure PMs never see | **Design.** §3 | — |

**Where DecisionLens sits.** It is invoked rarely and deliberately, for a decision that is worth a
brief. If a PM is running it weekly on routine calls, either the definition of "consequential" has
drifted or the tool is being used as a document generator — both are §14 signals worth watching.

**Entry point, and a design commitment.** The tool should be reachable from where the decision
already lives — the review document, the planning ticket, the portfolio meeting — rather than
being a new destination a PM must remember to visit. That integration is **not built**; the
prototype exposes a CLI and a Streamlit UI. It is listed here because an ecosystem design that
ignores the entry point tends to produce a well-built tool nobody opens. **[Product judgment]**

---

## 3. Model gateway

**Design, not built.** The prototype has a single-process analogue that establishes the shape: a
vendor-neutral provider boundary (`src/decision_lens/llm/`), explicit provider selection where a
stray API key in the environment is *not* a trigger, and a credential excluded from `repr` and
`model_dump` so it cannot reach a log line or a brief (`src/decision_lens/config.py`). A gateway
is those three properties enforced for an organisation instead of for one process.

**The case for centralising, concretely.**

| Property | What it buys | What its absence costs |
|---|---|---|
| **Vendor neutrality** | One adapter boundary. Adding or switching a provider is a change in one place, not in every team's code. The prototype's `ProviderChoice` deliberately omits providers for which no adapter exists — offering a choice that resolves to nothing is worse than not offering it. | Provider choice becomes an accident of whichever team integrated first, and switching cost is paid N times. |
| **Cost control** | Per-run and per-org budget ceilings, cost attribution by team and by skill, and the ability to see that a multi-stage workflow costs more than a single call — which it does, and which [03 §17](03-architecture-and-governance.md) treats as a first-class trade. | No attribution, so no one can answer whether the workflow is worth its own cost. That question is central to this product's thesis. |
| **Version pinning** | A brief is reproducible only if the prompt version *and* the model version are recorded and pinnable. The run trace records both today. A gateway extends that to "this model version remains callable until a stated deprecation date." | A silently upgraded model invalidates every recorded evaluation and every reproducible brief, without anyone being told. |
| **Rate limits and quotas** | A shared, managed budget rather than a per-team scramble. | One team's backfill exhausts another team's quota. |
| **Logging and audit** | One place where every consequential call is recorded, with the identity that made it, and never with secrets. | Audit becomes a survey of teams, which is not audit. |
| **Egress and classification enforcement** | Data-classification rules applied at the boundary, so a restricted-class record cannot be sent to a provider that policy does not permit. | Enforcement lives in each caller's good intentions, and an instruction that can be ignored is not a control. |

**Why individual teams should not hold provider credentials.** A key held by a team is an
unmanaged egress path with no attribution, no revocation inventory, and no way to retire a model
version. It also makes the two governance questions unanswerable: *who called this model with what
data*, and *can we stop them*. **[Product judgment]**

**The honest counter-argument.** A gateway is a single point of failure and it will lag provider
features. Two mitigations belong in the design: pass-through of provider-specific parameters so
the gateway does not become a lowest-common-denominator API, and a published deprecation window so
version pinning does not turn into version freezing. A gateway that makes teams route around it
has failed at its actual job.

---

## 4. Reusable skills

This is the section where the prototype's mechanism carries the organisational argument, so the
mechanism first.

**What the repository already does.** An analysis skill is not a prompt. It is:

- a **typed output model**, so a stage that returns the wrong shape fails rather than degrades;
- a **versioned prompt** with a **content fingerprint** derived from the text
  (`src/decision_lens/prompts/__init__.py`);
- a set of **deterministic requirements** the skill enforces itself in code via `violations()`,
  on the principle that anything checkable in code belongs there rather than in the prompt —
  an instruction can be ignored, a check cannot (`src/decision_lens/skills/base.py`);
- a **hard boundary**: a skill never reaches a data source and never calls another skill. That is
  what keeps each stage separately runnable and separately testable;
- a **registry** that refuses to register two prompts under the same name and version, because
  that would make a run trace ambiguous about which one ran.

**And what the repository learned the hard way.** D14 in [05](05-decision-log.md) records that two
prompts were edited after being recorded and their version labels were left alone, so eight
shipped stages replayed answers to wording that no longer existed. The fix was not discipline. It
was to decide reuse on the **content fingerprint** rather than on the human-declared version,
because a fingerprint is derived from the text and cannot be forgotten — and to route the
resulting warning to a place a human actually reads. *A check whose output nobody receives is
indistinguishable from no check.*

**The organisational argument follows directly.** A prompt pasted between teams in a Slack message
has no version, no fingerprint, no owner, no typed output, no deterministic requirements, and no
test. It therefore cannot be improved — only re-forked. Nobody can tell whether two teams are
running the same analysis, whether a fix propagated, or whether a result was produced by the
wording currently in the document. Every failure mode D14 records happens at organisational scale,
permanently, and with no build to fail. **[Product judgment]**

So skills are proposed as **shared organisational assets on the same terms the code already
enforces**: named, versioned, fingerprinted, typed, tested, owned, and retired deliberately.

### Skill lifecycle

**Design.** The registry mechanism exists; the review institution does not.

| Stage | Who acts | Bar to pass |
|---|---|---|
| **Propose** | Any PM, usually via a champion (§11) | A decision question the existing skills answer badly, and an example where they do. |
| **Design** | Author + platform | Typed output. Deterministic `violations()` for every requirement expressible in code. No data-source access. |
| **Evaluate** | Skill review board (§17) | Scored on cases in the shared harness, against the existing skill or against a single strong call. A skill that does not beat a strong single call is not adopted — the same bar the product holds itself to (D10). |
| **Hold-out check** | Review board | **At least one evaluation case authored after the prompt is frozen, by someone who has not read it.** D13 records that the repository's own bundled case fails this bar; it is the single most important quality gate in the lifecycle and the one an organisation will be most tempted to skip. |
| **Register** | Platform | Explicit name + version. Registration refuses to overwrite. |
| **Deploy** | Platform | Run trace records prompt version and fingerprint on every call. |
| **Monitor** | Platform + enablement | Override reasons, validation failures, and fingerprint-drift warnings routed to the owner (§16). |
| **Revise** | Owner | **A change is a new version, never an in-place edit.** New text ⇒ new fingerprint ⇒ recorded outputs re-recorded. |
| **Deprecate** | Review board | Announced with a window. Existing briefs remain reproducible because the old version stays resolvable. |
| **Retire** | Platform | Removed from the catalogue; kept resolvable for audit. A brief whose skill version cannot be resolved is no longer verifiable, which defeats the purpose of having produced it. |

**Anti-pattern to name explicitly:** a skill catalogue that grows monotonically. If nothing is ever
retired, the catalogue becomes a search problem and PMs revert to improvising. Retirement is a
funded activity, not a tidy-up. **[Product judgment]**

---

## 5. Shared connectors

**Design, not built.** The prototype implements exactly one connector, `LocalFileEvidenceSource`,
over synthetic files. Enterprise connectors are specified in
[03](03-architecture-and-governance.md) and deliberately not stubbed — D9 records that a written
contract is more honest than classes that raise `NotImplementedError`. No access to any real
system is claimed anywhere in this repository.

**One connector per source system, never one per PM.** The alternative — each team or each PM
wiring their own access — fails on five counts, all of which are organisational rather than
technical:

| Failure | Consequence |
|---|---|
| Credential sprawl | Every PM becomes a credential holder and an integrator. Revocation becomes an inventory problem nobody owns. |
| No permission fidelity review | The single hardest property in the connector design — *a PM must never see through DecisionLens what they could not see in the source system* — has to be proved once, per source. Proving it per PM is proving it never. |
| No health monitoring | A source that starts returning empty results silently produces briefs with invisible gaps. §13 treats this as the highest-severity incident class. |
| No shared rate budget | Each integration negotiates its own limits with the source system, badly. |
| No normalisation | Ten teams produce ten evidence shapes and citations stop being comparable across briefs. |

**The retrieval-only boundary is enforced by the signature, not by convention.** The contract in
`src/decision_lens/connectors/base.py` takes an `EvidenceRequest` and returns `EvidenceRecord`s.
There is no channel through which a connector can return a conclusion, a ranking, or a judgment
about quality. That is a deliberate structural choice with an organisational payoff: connectors
can be owned by a platform team that has no product context, because they are never asked to
exercise product judgment. Interpretation stays in skills (§4), which are owned by people who do
have that context.

**Scale is configuration, not multiplication.** [03 §4](03-architecture-and-governance.md) works
the Jira example: one connection maps to one Jira site, and project keys are configuration inside
that shared connection rather than separate connectors. Multiple sites mean multiple centrally
managed connections. PMs select scope; they never handle credentials.

**Retrieval runs under the requesting PM's own delegated identity**, not a service account with
broad read access. A service account is easier to build and it makes the permission-fidelity
property unachievable in principle. [03 §5](03-architecture-and-governance.md) specifies the model.

---

## 6. Data and knowledge

DecisionLens is only as good as the evidence it can reach, and traceability over an incomplete
corpus produces confident, well-cited, badly scoped conclusions — worse than obvious ignorance,
because harder to spot (01). This section is therefore about **which sources, with what known
weaknesses**, not about maximising coverage.

**Design.** None of these connections exists. Freshness expectations below are proposed
requirements, not measurements.

| Source class | Evidences well | Characteristic failure mode | Freshness expectation |
|---|---|---|---|
| Customer feedback (surveys, reviews, interviews) | Reach, sentiment, articulated need | Self-selected. Volume tracks who is willing to write, not who is affected. | Continuous; item date carried on every record |
| Product metrics / analytics | Usage, funnels, magnitude | Definition drift. The same metric name means different things across quarters and nobody records when it changed. | Daily; definition version required alongside the value |
| Support tickets | Failure modes, operational cost | Over-represents the broken and the vocal; under-represents silent abandonment. | Continuous |
| Jira / delivery systems | Effort, dependencies, delivery history | Estimates are estimates. Closed-ticket counts measure activity, not outcome. | Continuous |
| Confluence / PRDs / research decks | Strategic intent, prior reasoning, qualitative insight | Ageing without a signal. A four-year-old strategy page looks identical to last week's. | Staleness computed from dates and reported, not assumed |
| OKRs and strategy documents | Alignment | Written to be agreed with, so nearly everything can be argued to align with something. | Per planning cycle |
| Experiment results | Causal claims — the strongest evidence available | Underpowered or unregistered experiments presented with the authority of registered ones. | Per experiment; pre-registration status carried as metadata |
| Finance | Revenue, cost, spend | An estimate with no stated method reads exactly like a measurement. The evaluation's `returns_fraud_signals` case is built on precisely this. | Per close |
| Governance / policy / compliance | Constraints | Constraints are not comparison items. They bound the allocation before comparison begins (01). | On change |
| **Prior decisions and their outcomes** | What was decided, on what basis, and what happened | **Does not exist in most organisations as a retrievable source.** | Per decision |

**Two gaps worth naming rather than burying.**

*The innovation horizon has no data, by construction.* 01 argues that a method reading absence of
evidence as evidence of low value will systematically defund innovation. No amount of connector
work fixes this, because the evidence has not happened yet. The ecosystem's answer is
missing-evidence detection — naming the unknown so an unevidenced option stays in the conversation
on honest terms — not more sources.

*Nothing records why something was **not** built.* The rejected alternative, the deferral, the
no-build option and its tripwire are the highest-value evidence for a future portfolio decision
and no system of record captures them. This is the one source the ecosystem must **create** rather
than connect, and DecisionLens's own briefs and recorded PM decisions are the natural seed: the
brief already stores alternatives, confidence with its basis, and the PM's final decision
separately from the recommendation. Making that store retrievable is a small addition with a
disproportionate payoff, and it is the dependency S4 (§1) sits on. **[Product judgment]**

---

## 7. Enterprise configuration

**Design.** Centrally managed by the platform team. A PM never sees any of it.

| Setting | Why it must be central |
|---|---|
| System URLs and tenant identifiers | One authoritative source per system; otherwise briefs cite different tenants and nobody notices |
| Authentication and OAuth app registration | Credential custody, revocation inventory, delegated-identity setup (§5) |
| API setup and client configuration | Rate-limit negotiation with the source system happens once |
| Schema mapping into the normalized evidence shape | Citations are only comparable across sources if the shape is |
| Rate limits and quotas | Shared budget, not per-team scramble |
| Data classification and PII redaction rules | Legal exposure; enforcement belongs at the boundary, not in each caller |
| Retention for briefs and run traces | A brief that has been deleted cannot be audited; one kept forever is a liability. Both are policy calls |
| Audit logging | Must be uniform to be usable |
| Connector health thresholds and alerting | §13 |
| Model gateway defaults, pinned versions, budget ceilings | §3 |

The design rule for this layer: **if a setting requires a credential, a legal judgment, or a
security review, it belongs here.** Nothing in this layer requires product knowledge, which is
exactly why it can be owned by a team that has none.

---

## 8. Team / product-area configuration

**Design.** Owned by product leads and champions, administered by platform admins.

| Setting | Example | Why not central, why not per-PM |
|---|---|---|
| Relevant projects and spaces | Which Jira project keys and Confluence spaces belong to this area | Central has no way to know; per-PM produces a different corpus for every colleague |
| Dashboards and metric sources | Which analytics views are authoritative | Same |
| Feedback sources | Which survey and review streams cover this product | Same |
| Default metrics | The three or four measures this area is actually run on | Encodes what "impact" means here |
| Labels and taxonomy | Which tags mark an exception, a defect, a churn signal | Retrieval quality depends on it |
| Product terminology | A glossary: what "exception", "attempt", "unit" mean in this domain | The single highest-leverage entry in this table. A model reasoning over a corpus whose vocabulary it has misread produces fluent, wrong, well-cited output **[Product judgment]** |
| Governance requirements applicable to the area | Payments, identity, and health data carry constraints that general policy states generically | Must be specific to be enforceable |
| Default time windows | What "recent" means for this product | Differs by cycle length |

This layer exists because it is the only configuration that requires **product knowledge and no
credentials**. Give it to the platform team and it goes stale; give it to individual PMs and every
PM's brief is drawn from a different corpus, which destroys comparability across a portfolio.
**[Product judgment]**

Its quality is a named champion accountability (§11), and its staleness is a §14 adoption signal:
an area whose configuration has not been touched in a planning cycle is probably not being used.

---

## 9. PM runtime context

**Partly built.** The prototype takes a structured decision request — question, desired outcome,
scope — and takes no credentials of any kind. The identity, permission and inference elements
below are design.

| Input | Source | Notes |
|---|---|---|
| Identity | SSO | Never entered. Determines permissions (§5) |
| Product area | Inferred from identity; overridable | Selects the area configuration (§8) |
| **Decision question** | **The PM** | The one input that cannot be inferred or delegated |
| Desired outcome | The PM | What a good result looks like, independent of solution |
| Time period | Default from area config; overridable | |
| Segment | The PM, optional | Segment scope is a recurring hazard: support that holds for one segment asserted of all |
| Scope filters | The PM, optional | Which projects, spaces, sources to include |
| Permissions | Delegated from identity | Never entered, never configurable by the PM |

**PMs never configure credentials or APIs.** If a design ever asks a PM for an API token, that
design has failed — it has moved a platform responsibility onto a person who cannot discharge it
and cannot be held accountable for it.

**The decision question is the hard part, and it is the training target.** D6 and D7 in
[05](05-decision-log.md) record the difference between *"should we build an AI assistant for
delivery exceptions?"* and *"which intervention should the team prioritize to reduce delivery
exceptions?"* The first has already decided the answer; the second admits process change,
data-quality work, rules-based automation, further research, deferral, and no change. A
solution-first question cannot be rescued by a good tool, and a tool built to encourage AI
adoption that is fed solution-first questions will reliably recommend AI — at which point PMs
correctly stop trusting it. Question framing is the single most consequential thing a PM
contributes at runtime and §10 puts it first.

---

## 10. Training

**Design.** No curriculum has been built or delivered.

### The position: PMs should not have to learn prompt technique

This is a deliberate and slightly contrarian call, and it is the strongest thing this section has
to say. **[Product judgment]**

1. **Prompt technique depreciates.** It is a property of a model generation. A curriculum built on
   it needs rewriting each time the models move, and the organisation carries that cost forever.
2. **Better prompting produces better-*sounding* output, not more checkable output.** 01 makes
   this argument against prompt literacy as the binding constraint: raising fluency faster than
   reliability makes verification *harder*, because fluency hides the seams. A training programme
   that succeeds on its own terms can therefore make the selected problem worse.
3. **It makes adoption depend on individual craft.** If output quality tracks prompt skill, the
   organisation gets a distribution of quality it cannot manage, and enablement becomes a permanent
   remedial function.
4. **The skills layer exists precisely to remove the need.** §4's whole argument is that analysis
   approaches should be versioned, tested, shared assets. If PMs must still hand-craft prompts,
   the skills layer has failed and no amount of training compensates.

The corollary is an obligation, not a free pass: **if PMs are not to learn prompt technique, the
skill catalogue must be good enough that they never need it.** That is a platform commitment.

### What PMs should learn instead: evidence interrogation

| Capability | What it looks like when learned |
|---|---|
| **Problem-first question framing** | Can restate a solution-first request as a problem-first one and explain what the first version had already decided (§9) |
| **Measurement vs. recall vs. preference** | Recognises a stakeholder's remembered figure, and an executive's preference, as neither being findings |
| **Denominator and segment discipline** | Asks what the base was and who was in it, before reacting to a rate |
| **Method behind an estimate** | Treats a finance estimate with no stated method as an assumption, however precise the number looks |
| **Reading a citation to the source** | Opens the cited record rather than trusting the quote. The habit the product's entire traceability mechanism is built to reward |
| **Reading a missing-evidence list as an action list** | Sees a named gap as work to commission, not a caveat to note and move past |
| **Reading confidence as a qualitative judgment** | Knows that a support label is not a probability, and knows the tool's own bias (§12) |
| **Calibrating scrutiny to reversibility** | Spends verification effort where the decision is expensive to reverse, and stops spending it where it is not |

### Format

Not a course to be completed. Practice on cases with **planted hazards and a published answer
key** — a PM works the case, then sees what was planted and what they missed.

This is unusually cheap to build here, because the evaluation corpus is already exactly that
shape: eleven cases with authored ground truth, containing stale figures quoted in prose, a
'largest cause' claim true only of one segment, a pilot that could not measure its own effect, a
blank field that reads as zero, and a thick corpus with almost no load-bearing evidence in it. The
same material that measures the system can teach the reader. It would need repackaging for human
use; that repackaging is **not built**.

**Definition of done for a trainee:** finds a planted overstatement in a brief without being told
one is there. Not "has completed the module."

---

## 11. Office hours, champions, and communities of practice

**Design.** No such programme exists.

| Role | Accountable for | Explicitly not accountable for |
|---|---|---|
| **Central enablement** | Curriculum (§10), chairing the skill review board (§4), the measurement programme (§14–15), responsible-use guidance (§12) | Platform incidents; area configuration; individual decisions |
| **Embedded champion** — a practising PM in the product area, with time formally allocated | Quality and freshness of the area configuration (§8), including the glossary; proposing and co-authoring skills; first-line triage (§13); carrying real cases into the community | Being an unpaid support desk; connector health; policy interpretation |
| **Community of practice** | Case sharing, including failures; surfacing recurring gaps for §16 | Decisions, standards, or approvals — it has no authority and should not pretend to |

**Champion versus central, and why both.** Central enablement can build a curriculum and a review
board but cannot know what "exception" means in a delivery product, which projects are
authoritative, or which decisions in an area are actually consequential. That knowledge is local
and it decays without a local owner. Conversely, a champion network with no central function
produces N incompatible local practices and no shared assets — the exact failure §4 exists to
prevent. **[Product judgment]**

**The failure mode to design against:** the champion role as an unfunded volunteer commitment. It
converts to a support desk, the champion's day job reclaims the time, and area configuration goes
stale — which then shows up as poor retrieval, which gets attributed to the tool. If the time is
not formally allocated, the role should not be created. **[Product judgment]**

**Assumption, flagged.** That an embedded-champion model outperforms central-only rollout is a
**[Assumption]** carried from general enablement practice. Nothing in this repository measures it,
and §14 should be designed to test it rather than to assume it.

---

## 12. Responsible-use guidance

**Design**, except where it describes behaviour the prototype already has.

### Where AI decision support is and is not appropriate

| Situation | Position |
|---|---|
| Consequential, reversible product decisions with fragmented evidence | The target case. Use it, and challenge it |
| Irreversible or externally committed decisions | Use it, with proportionally more verification. The brief is an input to a human process, never the process |
| Security, compliance, contractual, and critical reliability obligations | **Not comparison items.** They constrain the allocation before comparison begins (01). A compliance obligation that can lose a weighted comparison to a growth bet has been modelled wrong |
| Anything requiring legal or regulatory sign-off | The brief informs; it does not substitute for the sign-off |
| Decisions about individuals — performance, hiring, discipline | **Out of scope. Not a use case, at any maturity stage** |
| Evidence confidential to a party who did not consent to this use | Out of scope. Permission fidelity (§5) is a floor, not the whole test |
| Any autonomous action | Never. DecisionLens recommends; the PM decides and is accountable |

### A recommendation is to be challenged, not accepted

This is the product's own position and it is enforced mechanically rather than by exhortation:
every brief must contain a non-AI alternative and a no-build/defer/research alternative, both
checked deterministically; a challenger puts fixed questions to the draft before a human sees it
and **can only lower confidence, never raise it**; the PM's final decision is recorded separately
from the recommendation. The bundled demo currently ships a brief blocked by its own challenger
for overstating what three feedback rows supported, and that block is left standing.

The reading protocol that follows: **open the missing-evidence list and the contradictions before
the recommendation.** A PM who reads the recommendation first has already anchored, and the rest
of the brief becomes confirmation.

### How to read this tool's confidence — including its known bias

[04](04-evaluation.md) measured something PMs must be told explicitly rather than discover:

- DecisionLens **never overstated** support: 0 of 11 cases, against 1 of 11 for the baseline. The
  baseline's single failure is diagnostic — on a case built so a thick corpus contains almost no
  load-bearing evidence, it read the volume and said `moderate` where `low` was the defensible
  ceiling.
- But DecisionLens **understated** support on 6 of 11 cases, against 1 for the baseline. On a case
  built so that `strong` support is genuinely earned — a pre-registered randomised experiment with
  n=412,905, corroborated by an independent metrics series — **both arms said `moderate`**.

So the tool is **not well calibrated; it is biased low**, in the safer direction. Three practical
consequences for a PM:

1. **A `moderate` is not evidence that the case is weak.** It is at least as likely to be the
   tool's caution. Check upward as well as downward.
2. **The tool must not become the reason not to commit.** A decision-support system that always
   hedges transfers the judgment straight back to the reader; that is a limitation, not modesty.
3. **Support labels are qualitative judgments, not calibrated probabilities**, and must never be
   averaged, weighted, or fed into a scoring formula.

Read with the caveats §15 places on the evaluation itself: eleven cases, one run each, synthetic
evidence, single author, no variance measurement.

### Overrides are expected

A PM disagreeing with a recommendation and recording why is the system working. §14 treats a
near-zero override rate as a warning sign of rubber-stamping, not as a success metric.

---

## 13. Support model

**Design.** No support function exists.

| Tier | Handles | Owner |
|---|---|---|
| 0 — Self-serve | Documentation, worked examples, the answer keys from §10 | Enablement |
| 1 — Champion | "The evidence looks wrong / thin / irrelevant for my area" — usually an area-configuration problem (§8) | Champion |
| 2 — Enablement | Skill behaviour, interpretation questions, responsible-use questions, training gaps | Enablement |
| 3 — Platform on-call | Connector failures, gateway failures, permission defects, cost incidents | Platform |
| Governance escalation | Suspected unauthorized evidence exposure; a brief found materially wrong after a decision was made on it | Security / risk, per [03 §19](03-architecture-and-governance.md) |

**The severity rule that matters.** A connector returning *fewer* results is more dangerous than a
connector returning *none*, because a total failure is visible and a partial one is not: the brief
still renders, still cites everything it used, and is silently scoped wrong. This is the case D14's
lesson generalises to — the detection is rarely missing, the path from detection to a human reading
it is. Two design requirements follow:

- **Partial retrieval failure must appear in the brief itself**, not only in a log or a dashboard.
  The prototype already routes provider warnings into the run trace and the rendered brief; the
  same treatment must extend to every connector.
- **Connector health must be monitored against expected volume**, not just against uptime. A source
  that answers quickly and returns nothing is up.

---

## 14. Adoption measurement

### Why raw usage volume is a poor primary metric

Five reasons, and they compound. **[Product judgment]** throughout.

1. **It is maximised by exactly the behaviour the strategy is trying to move past.** Drafting,
   summarising and rewriting are frequent; consequential portfolio decisions are rare. Any
   volume-based metric is dominated by S1 activity (§1) and will look excellent in an organisation
   that has changed nothing about how it decides.
2. **Consequential decisions are rare by nature, so a good year is a small number.** A metric whose
   healthy value is small and whose unhealthy value is large is the wrong shape for a headline.
3. **Repeat runs are ambiguous, and plausibly a defect signal.** A PM running the same case five
   times may be iterating productively — or may have got nothing usable four times. Volume cannot
   tell those apart, and it scores the second one higher.
4. **It is trivially gamed, and it will be gamed the moment it is a target.** Every input is under
   the measured population's control and none of them requires the output to be read.
5. **It rises with headcount and mandate.** Growth in usage is confounded with growth in seats and
   with a leadership instruction to use the tool, neither of which is adoption.

The deeper objection: usage measures whether a tool was opened. The hypothesis (01) is about
whether AI is used **for decisions that matter**. Those are different questions and only one of
them is worth a programme.

### Leading indicators of adoption

**Design.** No baseline exists, so **no target values are proposed** — setting a target without a
baseline manufactures a number.

| Indicator | What it indicates | How observed | Failure mode if used alone |
|---|---|---|---|
| **Depth**: share of decisions meeting a pre-agreed consequentiality threshold that have a brief | Whether AI reached the work that matters | Decision records vs. brief records | Threshold gaming: relabelling routine calls as consequential |
| **Voluntary return**: a PM using it for a *second* consequential decision unprompted | The only honest signal of perceived value | Per-identity, per-decision | Slow to accumulate |
| **Override rate** with a recorded reason | Engagement with the recommendation. **Near-zero is a warning, not a win** — it indicates rubber-stamping | Recorded PM decision vs. recommendation | Encourages performative disagreement if targeted |
| **Gap closure**: share of named missing-evidence items someone actually went and got | Whether the highest-value output changes behaviour | Follow-up on brief items | Requires manual attribution |
| **Evidence-cited challenge**: reviews where an objection cites the brief's sources rather than seniority | S3 behaviour, and the cultural change that matters most | Observed in review artefacts; qualitative | Not cleanly countable |
| **Blocked-brief respect**: share of briefs carrying blocking validation errors that were *not* acted on | Whether guardrails are honoured or routed around | Validation output vs. decision records | — |
| **Skill reuse breadth**: teams using catalogue skills vs. locally forked prompts | Whether §4 is working as an institution | Registry telemetry | — |
| **Configuration freshness**: area configurations touched within a planning cycle | Whether champions are real (§11) | Config metadata | — |
| **Stage distribution** (§1), assigned from artefacts | Where the population actually is | Sampled artefact review | Expensive; sample, don't census |

**Two rules for the panel.** Report it as a panel — any single number here becomes a target and
then stops measuring. And **sample artefacts rather than surveying people**: self-reported AI
usage measures enthusiasm and social expectation, not behaviour. **[Product judgment]**

---

## 15. Outcome measurement

Adoption (§14) tells you the tool is being used on the right work. It does not tell you whether the
decisions got better. Two horizons, and they must not be reported as though they were one.

### Leading indicators — measurable in a short study

| Measure | Status |
|---|---|
| Citation validity and citation-span resolution | **Measured** (04): 1451/1451 (100%) for DecisionLens, 967/969 (99.8%) for the baseline |
| Uncited claims | **Measured**: 0/534 and 0/236 |
| Contradiction recall | **Measured**: 36/50 (72%) vs. 32/50 (64%) |
| Overstated support | **Measured**: 0/11 vs. 1/11 |
| Understated support | **Measured**: 6/11 vs. 1/11 — the finding that cuts against the product |
| Alternative coverage | **Measured**: 134 options vs. 79; mandatory non-AI and no-build present in 11/11 both arms |
| Verification time, total completion time, decision-quality rating, trust, willingness to use, actionability, whether the PM changed the decision | **Designed, not conducted.** Requires the real-PM study in [04 §11](04-evaluation.md) |

**What those measured figures do and do not license.** Eleven cases, one live run per arm per case,
so there is no variance measurement and no error bar. Eight percentage points on contradiction
recall is four graded items out of fifty and cannot be distinguished from run-to-run noise. The
evidence is synthetic and one person wrote both the corpus and the ground truth, and the bundled
case is in-sample (D13). The honest summary is that DecisionLens **did not lose**, led on a small
sample by a margin not shown to be reproducible, and demonstrated one specific mechanism —
restraint on a case designed to induce overclaiming — that survives a small sample better than an
average does. **An ecosystem investment should be justified on that mechanism and on the
verification argument, not on the size of that margin.**

### Lagging outcome measures — proposed, and not demonstrable here

**These cannot be demonstrated within this take-home. Nothing in this repository measures any of
them, and no figure for any of them appears anywhere.**

- Customer outcomes
- Revenue impact
- Cost avoidance from investments not made
- Retention
- Portfolio return

**Why not, specifically:**

1. **The lag exceeds the exercise.** A portfolio allocation resolves over multiple planning cycles.
2. **Execution, market timing, and luck sit between decision quality and business results.** A good
   decision executed poorly and a poor decision rescued by market movement are indistinguishable
   from the outcome alone.
3. **There is no counterfactual.** The value of an investment *not* made is unobservable by
   construction, and cost avoidance is therefore the hardest measure in the list.
4. **Attribution to a decision-support tool is confounded** by everything else that changes in an
   organisation over the same period.

**A design that would make them measurable later.** Not conducted; recorded so the pilot is not
designed from scratch:

- **Pre-register at decision time.** The brief already carries a stated confidence with its basis
  and the condition that would change it. Record alongside it the expected outcome and the
  measurement that would confirm or refute it. A decision without a pre-registered expectation
  cannot be evaluated afterwards without hindsight bias — this is the mechanism that makes any
  lagging measurement possible at all.
- **Give the no-build alternative a named tripwire**, so cost avoidance has something observable
  attached to it rather than being asserted retrospectively.
- **Review on the exit condition, on a schedule**, and record the review whether or not the news is
  good. That review is itself the S4 behaviour in §1.
- **Compare paired decisions** within an area rather than across the organisation, because
  cross-area comparison imports every confound above.
- **Report the reversal split**: decisions that were right on the evidence then available versus
  decisions that were poorly reasoned at the time. Only the second class is a decision-quality
  failure, and conflating them punishes correct risk-taking — which is how an organisation
  quietly stops funding the innovation horizon (01).

---

## 16. Feedback loops

**Design.** The signals below are largely generated by the prototype already; the routing and the
institutions that would act on them are not built.

| Signal | Generated by | Routes to | What changes |
|---|---|---|---|
| PM override + recorded reason | Recorded PM decision vs. recommendation | Skill owner, review board | Prompt revision **as a new version**, plus a new evaluation case capturing the disagreement |
| A brief found materially wrong after the fact | Incident escalation (§13) | Review board + governance | Regression case in the harness; answer-key correction; [03 §19](03-architecture-and-governance.md) |
| Unresolvable or repaired citations | Provenance checking; citation repair already reports every correction rather than applying it silently | Skill owner | Prompt or quoting-rule change; connector normalisation if the source is at fault |
| Fingerprint drift warning | Cached-provider fingerprint comparison (D14) | Platform | Re-record; the build fails rather than the cache surviving |
| Missing-evidence items naming the same absent source repeatedly | Missing-evidence skill, aggregated | Data/knowledge backlog (§6) | A new connector, or an acknowledged permanent gap |
| Blocked briefs | Deterministic validation | Skill owner + champion | Either the check is wrong or the corpus is thin — both actionable, and telling them apart is the point |
| Evaluation results | The harness | Review board | Skill adoption, revision, or retirement (§4) |
| Recurring "this evidence is irrelevant to my area" | Champion triage (§13) | Area config owner | Area configuration and glossary (§8) |

**Two disciplines, without which this table is decoration.**

- **Every loop terminates in a named owner and a versioned artefact.** A signal that ends in a
  dashboard nobody owns is the D14 failure again: the detection was never missing, the path from
  detection to a human reading it was.
- **Every change made in response to feedback adds a held-out case** — authored after the change is
  frozen, by someone who did not make it. Otherwise the system is optimised against its own
  history and its evaluation slowly stops measuring anything. D13 records this repository failing
  that bar and choosing to record the failure rather than paper over it.

---

## 17. Ownership model

**Design.** None of these functions is staffed.

| What | Accountable | Contributes | Explicitly not |
|---|---|---|---|
| Model gateway (§3) | AI platform engineering | Security (egress, classification), Finance (budgets) | Not enablement — it is infrastructure |
| Connectors (§5) | AI platform engineering | Source-system owners; Security for permission fidelity | Not individual PMs or product teams |
| Permission fidelity | AI platform engineering **jointly with** Security | — | Not delegated to a connector author's judgment |
| Skill catalogue (§4) | **Skill review board**, chaired by enablement | Platform provides registry, harness and hold-out discipline; practising PMs author skills | Not platform alone — skills encode product judgment |
| Enterprise configuration (§7) | Platform admins | Security, Legal, Data governance | Not product leads |
| Area configuration (§8) | **Product lead for the area**, operated by the champion | Platform admins | Not central enablement, which cannot know the domain |
| Data and knowledge coverage (§6) | Data platform / knowledge management | Product areas name the gaps | — |
| Decision-record store (§6) | Product operations or PM leadership | Platform builds the retrieval | Nobody owns this today, which is why it does not exist |
| Governance and responsible use (§12) | Risk / Legal / Security **define**; Platform **enforces**; Enablement **teaches** | — | No single owner. Splitting definition from enforcement is deliberate |
| Training (§10) | Central enablement | Champions supply real cases | — |
| Support (§13) | Tiered per §13 | — | Champions are not the on-call rota |
| **Adoption outcome (§14–15)** | **PM leadership** | Enablement measures and reports; platform instruments | **Not the enablement team** |
| **Each individual decision** | **The PM who made it** | The brief is an input | Never the tool, never the platform, never the recommendation |

**The two rows that decide whether this works.**

*Adoption is owned by PM leadership, not by enablement.* An enablement team can build a gateway, a
catalogue, a curriculum and a measurement panel, and can make none of it matter. Adoption requires
that the leaders whose PMs must change how they decide are accountable for whether that change
happens. Where adoption is owned by the team supplying the tools, it stays a tool rollout with a
usage dashboard — and §14 explains why that dashboard will look fine either way. **[Product
judgment]**

*Decision accountability never moves.* The tool recommends; the PM decides and is accountable. This
is a structural property of the design — the recommendation and the PM's final decision are stored
separately — and it is what makes the rest of the model safe to build. An ecosystem that blurred
it would be optimising for the failure the whole product exists to prevent.

---

## Related documents

- [01 — Product Strategy](01-product-strategy.md)
- [03 — Architecture and Governance](03-architecture-and-governance.md)
- [04 — Evaluation](04-evaluation.md)
- [05 — Decision Log](05-decision-log.md)

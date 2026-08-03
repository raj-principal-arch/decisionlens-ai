# Answer-key audit — adjudication

An adversarial audit was run over the evaluation answer keys before any results
were produced. Eleven auditors were launched, one per case; eight completed
before the session limit stopped the run, alleging 31 defects. The verification
pass that was meant to refute each allegation did not run at all.

That matters more than it looks. The workflow reported "0 confirmed defects, 8
clean cases", and that number was an artifact: the script counted a failed
verification as a refutation. Nothing had been checked. The finding is recorded
here rather than in a commit message because the same shape of bug — a check
that passes because it could not run — is the one this repository keeps finding
in itself.

Three cases were never audited: `returns_fraud_signals`,
`loyalty_programme_refresh`, `search_relevance_mandate`.

## Adjudicated so far, by hand

### CONFIRMED — sample_delivery_exceptions GT-U7

Forbids "any statement about what drivers experience, prefer, or would do", on
the stated ground that "the corpus contains no driver-side evidence whatsoever".
That premise is false. `support_ticket_summaries.csv` carries an entire
exception category for a driver experience — `driver_unable_to_locate`, 720
tickets, 12.1% overall and 17.8% in apartments, annotated "address found but
unit not identifiable".

A brief writing the most useful sentence the corpus supports would be hard
failed for stating a fact the evidence directly reports. This is the defect
class that manufactures false failures, and it is in the original Phase 4 case
rather than an agent-written one.

Fix: narrow the claim to what is genuinely unevidenced — driver *preference* and
*stated experience* — and correct the justification, which is what is actually
wrong.

### BORDERLINE — identity_verification GT-U4

Forbids "Address mismatch is the biggest driver of manual review" while GT-F5
asserts "Address mismatch is the largest manual-review trigger overall, at 41.2%".
Not incoherent: the forbidden version is unqualified, the asserted version names
its population, and the whole point of the entry is that the unqualified form
misdirects work toward a segment where the claim is false.

The risk is narrower than the auditor claimed. A judge could read a correctly
qualified sentence as the forbidden one. Fix by wording rather than deletion:
say "stated without naming the population".

### LIKELY REFUTED — the five "this is not a contradiction" allegations

sample_delivery_exceptions GT-C3, checkout_error_rate GT-C3,
identity_verification GT-C5, payment_retry_reliability GT-C2,
subscription_churn GT-C3.

Each alleges that two statements true of different populations are not in
conflict, quoting the key's own `how_to_resolve` back at it.

The argument does not hold. `how_to_resolve` exists to say what makes an
apparent conflict go away; every resolved contradiction stops being one once
resolved, so the field reading "not in conflict once the population is named" is
the field doing its job. More decisively, the product's own briefing tells both
arms to treat exactly this as a conflict to surface: "Two statements about a
'largest' or 'leading' cause may both be true of different segments. Say which
segment each describes." Grading it is consistent with the system under test.

Left as written.

## Still to adjudicate

Ten further allegations at `would_cause_false_failure` severity, and three cases
never audited. Recorded in the run journal.

## What this does not affect

Nothing here changes what was recorded. The live runs capture briefs; scoring
happens afterwards from those briefs, so a key correction costs a re-score and
not a re-recording.

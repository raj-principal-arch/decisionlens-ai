# Governance Requirements — Customer Support Systems

> **Synthetic document.** Fictional policy for a fictional organisation. No real Walmart data.
> Owner: legal-privacy. Created 2025-09-01. Last updated: 2026-05-18.

## Scope

This policy covers any system, rule-based or learned, that makes or influences a decision about a customer support ticket. It applies to the existing rules engine and to anything that replaces or supplements it.

## Automated customer-facing text

No system may send generated text to a customer without human review before dispatch. This applies regardless of the system's stated confidence and has no volume exemption.

Internal classification that produces no customer-facing text is out of scope for this requirement. Routing a ticket to a queue is internal classification.

## Human override

Every automated assignment decision must be reversible by the assigned agent in a single action, and no system may prevent or delay an agent from reassigning a ticket. Override must not require supervisor approval.

The reassignment control in the support platform already satisfies this requirement for the rules engine, and would satisfy it unchanged for a replacement router.

## Audit trail

Every automated assignment decision must record the deciding system, its version, the inputs it acted on, and its confidence where the system produces one. Records are retained for 24 months and must be queryable by ticket id.

The `routing_decision_log` table already meets this requirement and is the required destination for any replacement router.

## Model change control

Any learned model that affects customer outcomes requires, before production use: a named accountable owner, a documented offline evaluation on data the model was not trained on, a documented rollback procedure, and re-evaluation at least quarterly thereafter.

Models must not use customer demographic attributes, account tier or spend history as features.

Failing a quarterly re-evaluation requires either a documented remediation plan or reversion to the previous router.

## Personal data in ticket text

Ticket text may contain personal data. It must be stored and processed within its region of origin. Training or inference outside the region of origin is not permitted.

## Third-party processing

Any third party processing ticket text requires a completed data protection assessment before any data is shared with it, including for evaluation or trial purposes. Assessments currently take six to eight weeks.

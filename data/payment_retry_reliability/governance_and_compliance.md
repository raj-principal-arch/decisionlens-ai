# Governance and Compliance Requirements — Payments

> **Synthetic document.** Fictional policy for a fictional organisation. No real Walmart data.
> Owner: risk-and-compliance. Last updated: 2026-06-05.

## Security finding remediation

Findings raised by an external assessment carry a contractual remediation window measured from the disclosure date: 120 days for High, 180 days for Medium, 270 days for Low. The windows are set by Schedule 4 of the Fenwold Payments Master Services Agreement and are not discretionary.

Remediation of a finding with a contractual deadline is a compliance obligation, not a candidate initiative. It is scheduled against its deadline and is not scored, ranked, or traded against product work. Missing a deadline is a reportable breach and permits the payments partner to place the account into enhanced monitoring at Larkmere's cost.

A finding may be recorded as remediated only when the assessor has retested it. Partial remediation does not close a finding and does not stop the clock.

## PCI DSS scope

The Retry Orchestrator, its retry queue, and the payment instrument log stream are inside the cardholder data environment. The annual attestation is due 2026-10-31.

An open High-severity finding inside the cardholder data environment must be closed before attestation, or covered by a compensating control that the qualified security assessor has reviewed and accepted in writing. No compensating control has been proposed for PT-2026-014.

Any change to a component inside the cardholder data environment requires a change-control review with a ten business day lead time, and only one change to a given in-scope component may be in flight at a time.

## Logging and access

Payment instrument identifiers are restricted data. Retention in any log store is capped at 30 days and access must be limited to a named role. Platform log access is currently granted to all 84 engineers, which does not meet the named-role requirement.

## Direct debit scheme rules

A failed mandate collection may be re-presented no more than twice. Re-presentations must be at least three business days apart, and the buyer must be notified at least three working days before each one. Any change to collection retry frequency must be certified against the scheme rules before it is enabled.

## Customer messaging

A notice telling a buyer that a payment failed is transactional and does not require consent. A message that recommends a different payment method is classified as marketing under the current policy and requires recorded marketing consent from that buyer.

## Peak trading change freeze

No payments change may be deployed between 2026-11-10 and 2027-01-05. Security remediation with a contractual deadline is exempt from the freeze; discretionary product work is not.

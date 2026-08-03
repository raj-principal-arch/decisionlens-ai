# Experiment Report — Inline Authorisation Recovery (EXP-2026-04)

> **Synthetic document.** Fictional experiment, fictional organisation, fictional numbers. No real Walmart data.
> Owner: experimentation. Pre-registered 2026-04-27. Report finalised 2026-07-21.

## What was changed

When a card authorisation is declined or errors, the current web checkout returns the customer to the cart and clears the payment form. The treatment keeps the customer on the payment step, states the reason returned by the gateway in plain language, and re-presents the form from the tokenised card reference so that only the failing field has to be corrected.

## Design

Randomisation was at session level, 50/50, assigned on entry to the payment authorisation step. Both arms ran concurrently for the whole window.

- Window: 2026-05-04 to 2026-06-14, six weeks.
- Eligibility: web storefront, card payments, all three regions. App sessions and stored-wallet payments were excluded, as were colleague and automated test accounts.
- Enrolled sessions: 412,905. Control 206,338, treatment 206,567.
- Sample-ratio mismatch check: p = 0.72. No imbalance detected.
- The primary metric was registered before launch and was not changed during the window.

## Primary result

Payment authorisation step completion rate:

- Control: 91.2%, 188,180 of 206,338 sessions.
- Treatment: 94.6%, 195,412 of 206,567 sessions.
- Absolute difference +3.4 percentage points, 95% confidence interval [+3.2, +3.6], p < 0.001.

The effect did not decay over the window. Weeks 1 and 2 showed +3.3 points and weeks 5 and 6 showed +3.5 points, so this is not a novelty effect.

The window contained the May bank-holiday campaign. Because both arms ran concurrently under session-level randomisation, promotional traffic was allocated to the arms in the same proportion, and no calendar effect can produce a difference between them.

## Guardrails

- Chargeback rate on orders originating in enrolled sessions: control 0.11%, treatment 0.11%. Difference +0.00 points, 95% confidence interval [-0.02, +0.02].
- Refund rate: control 1.83%, treatment 1.86%. The interval includes zero.
- Support contacts per 1,000 orders: control 14.2, treatment 13.1. This metric was not registered and is reported for context only.

Chargebacks were counted to 30 days after order. Scheme rules permit a dispute up to 120 days after the transaction, so the chargeback reading is partial and the series is still being collected.

## What this experiment does not report

Order completion per enrolled session was recorded but was not a registered metric and has not been analysed. The effect of the treatment on completed orders, on basket value, or on the end-to-end checkout failure rate is not a result of this experiment.

The treatment was never shown to an app session or to a stored-wallet payment. Nothing here describes those flows.

## Prior work: slot picker refresh, February 2026

A redesigned slot picker was released to all web customers on 2026-02-09 with no holdout group.

Slot-step completion was 89.1% in the four weeks before release and 89.4% in the four weeks after. Two additional depots came online on 2026-02-23, adding slot capacity in the North and Central regions. The interface change and the capacity increase cannot be separated, and the release had no design capable of measuring its own effect.

## Not attempted

No experiment has tested a change to the slot selection step in isolation. No experiment has run on the app checkout, which does not emit the step-level events an experiment would need.

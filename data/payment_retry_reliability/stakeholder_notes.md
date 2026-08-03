# Stakeholder Notes — Payments Reliability Review

> **Synthetic document.** Fictional people, fictional quotations. No real Walmart data.
> Owner: payments-product. Meeting held 2026-07-27. Last updated: 2026-07-29.
>
> The statements below are recorded opinions from a review meeting. They are what people said, not what has been established.

## How the meeting opened

The deck opened with a single number: payment authorisation success, 96.9%, against the 96.0% floor in the partner agreement. No payment-method breakdown was shown and none was requested.

## Director of Payments — Iwan Prescott

"Every quarter we do not ship adaptive retries is money on the floor."

"Put the pen-test fix on the same backlog as everything else and let the scores decide. If it wins, it wins."

## Commercial Director — Naia Ostrand

"The pen test finding is a paperwork item. Nobody has actually exploited it."

## Head of Trade Sales — Bertie Halloran

"Our trade buyers keep telling me the bank transfer thing is broken. I hear it every week."

Asked how many buyers, how often, and over what period, no figure was available.

## Security Lead — Marisol Quaye

"The finding is open. The queue payload still carries the identifier and 84 engineers can read the logs. Shipping a logging patch is not the same as closing it."

## Engineering Manager — Delyth Rowan

"Only one change to the orchestrator can be in flight under change control. Whatever else we choose, it queues behind the remediation."

## Vendor briefing

A vendor product circulated by the Director of Payments claims a 2.4 percentage point uplift in authorisation success.

The material states no baseline, no sample size, no comparison method, and no merchant category. No independent evaluation was provided.

## Open question raised and not answered

Someone asked what happens to a buyer whose payment fails, and whether the order comes back later by another route. Nobody present had the number.

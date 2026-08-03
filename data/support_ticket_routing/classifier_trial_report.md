# Ticket Routing Classifier — Offline Trial Report

> **Synthetic document.** Fictional experiment, fictional results. No real Walmart data.
> Owner: data-platform. Trial ran 2026-03-02 to 2026-05-22. Report dated 2026-06-12.
> Reviewed by support-engineering and support-analytics.

## Purpose

To establish whether a text classifier trained on historical tickets assigns queues more accurately than the production rules engine, measured on data the classifier never saw.

## Labelled corpus

24,000 tickets created between 2024-10-01 and 2026-03-31. The label is the queue the ticket was resolved in, after any reassignment.

Labels were audited by support operations on a random subsample of 1,200 tickets. Two reviewers independently judged whether the resolving queue was the queue the ticket should have been routed to. They agreed with the label on 1,152 of 1,200 tickets (96.0%) and with each other on 1,171 of 1,200 (97.6%).

The 48 tickets where both reviewers disagreed with the label were tickets resolved by whichever queue happened to pick them up rather than by the queue that owned the problem. The resolving queue is a proxy for the correct queue and is not the same thing.

## Split

The held-out set is every labelled ticket created between 2026-01-01 and 2026-03-31: 4,800 tickets. None of them, and no ticket from that window, was used in training. Training used the remaining 19,200 tickets, created between 2024-10-01 and 2025-12-31.

The split is by time rather than at random, so the trial measures how the model performs on tickets written after the ones it learned from. A random split would have been easier to pass and would have told us less.

## Results on the held-out set

The production rules engine was replayed against the same 4,800 tickets at the engine version live during the period.

| Queue | Held-out tickets | Rules correct | Rules accuracy | Classifier correct | Classifier accuracy |
|---|---|---|---|---|---|
| Orders & Delivery | 1,560 | 1,180 | 75.6% | 1,437 | 92.1% |
| Returns & Refunds | 1,200 | 852 | 71.0% | 1,098 | 91.5% |
| Technical Faults | 1,010 | 624 | 61.8% | 837 | 82.9% |
| Billing & Payments | 620 | 525 | 84.7% | 519 | 83.7% |
| Account & Access | 410 | 237 | 57.8% | 357 | 87.1% |
| All queues | 4,800 | 3,418 | 71.2% | 4,248 | 88.5% |

Overall the classifier routed 88.5% of held-out tickets to the correct queue against the rules engine's 71.2%. Misroutes fall from 1,382 to 552, a reduction of 60.1%.

The replayed rules figure of 71.2% matches the production figure for 2026-Q1 exactly. That is the expected result and is our check that the replay is faithful.

**The classifier does not beat the rules engine everywhere.** In Billing & Payments the rules engine is more accurate: 84.7% against 83.7%. Billing tickets carry payment identifiers and card-decline phrasing that a keyword rule matches exactly, and the classifier gains nothing on them.

## Misroute structure

Under the rules engine the three largest misroute pairs are:

- Technical Faults routed to Orders & Delivery: 214 of 1,382 misroutes (15.5%)
- Returns & Refunds routed to Orders & Delivery: 191 of 1,382 misroutes (13.8%)
- Account & Access routed to Billing & Payments: 138 of 1,382 misroutes (10.0%)

A further 61 Billing & Payments tickets were routed to Account & Access. Confusion between those two queues in either direction therefore accounts for 199 of 1,382 rules-engine misroutes, or 14.4%.

## Model and serving

A linear text classifier over character and word n-grams of the ticket subject and body, plus the product category of the referenced order. Trained model size is 340 MB. Median inference time on the trial hardware was 41 ms per ticket, CPU only, with a 99th percentile of 118 ms.

Features are ticket text and product category. No customer demographic attribute, account tier, region or spend history was used as a feature.

Every trial prediction was written to the existing `routing_decision_log` table with the model version, the predicted queue and the model's confidence, in the same schema the rules engine writes to. No change to that table was required.

The trial never assigned a ticket. Every held-out prediction was compared against the label offline; production routing was unaffected throughout.

## Limitations

This trial measured routing accuracy offline. It did not measure time-to-resolution, because no ticket was routed by the classifier in production and no customer was affected. Any statement about the effect on resolution time is an inference from the accuracy result, not a measurement of it.

The held-out period is January to March. Ticket mix in that window is shaped by the post-holiday returns peak. Whether accuracy holds across the rest of the year is untested.

We have not estimated the cost of running or retraining this model in production. The trial ran on shared batch capacity that was not metered against us.

We did not measure what agents do with a routing decision they disagree with, because the trial never showed a prediction to an agent.

## Recommendation from the trial team

A shadow period before any traffic is switched: run the classifier alongside the rules engine on live tickets, apply the rules engine's decision, log both, and measure accuracy and time-to-resolution against the same tickets. The platform already supports this.

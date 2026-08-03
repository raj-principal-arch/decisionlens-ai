# Prior Experiments — Support Responsiveness

> **Synthetic document.** Fictional experiments, fictional results. No real Walmart data.
> Owner: support-analytics. Last updated: 2026-03-04.

## Intake form redesign A/B test (September 2025)

The ticket submission form was changed from a flat category dropdown to a guided picker that asks two questions before offering categories. Randomised at the customer level over three weeks: 8,412 tickets in the treatment arm and 8,390 in the control arm.

The share of tickets where the customer-selected category matched the resolving queue rose from 57.1% to 64.3%. That difference is significant at the 95% level and holds in every queue.

Queue-level routing accuracy was 72.0% in the treatment arm against 71.3% in the control arm. That difference is not statistically meaningful.

Median time-to-resolution was 20.8 hours in the treatment arm against 21.1 hours in the control arm. Also not statistically meaningful.

The guided picker shipped to all customers on 2025-10-02. It improved the category customers select and did not measurably improve routing, because the rules engine consults the customer-selected category for only two of the five queues.

## Manual triage desk pilot (February 2026)

For two weeks one senior agent hand-routed every ticket arriving in the Technical Faults intake stream before it reached a queue. 1,340 tickets were routed by hand.

Routing accuracy in the hand-routed stream was 94.0%, against 61.8% for the rules engine on comparable tickets.

The pilot used one agent, who knew the pilot was being measured, over two weeks. It establishes roughly what a knowledgeable human achieves on this ticket type. It does not establish what a triage desk staffed at volume would achieve, and it says nothing about the other four queues.

Throughput was 1,340 tickets in ten working days, or 134 tickets a day for one agent. At that rate, covering every intake stream at current arrival volume would take about five full-time routers.

## Not attempted

No intervention has been tested with time-to-resolution as its primary measure. The intake A/B measured it and found nothing; every other measurement in this corpus is of routing accuracy.

No test of reducing the reopen rate has been run, and no analysis of why tickets are reopened exists.

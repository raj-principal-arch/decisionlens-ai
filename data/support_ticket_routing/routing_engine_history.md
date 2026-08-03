# Routing Engine — Version History and Tuning Log

> **Synthetic document.** Fictional systems, fictional numbers. No real Walmart data.
> Owner: support-engineering. Created 2023-06-02. Last updated: 2026-06-30.

## What the routing engine is

Keyword and pattern rules evaluated against the ticket subject, the ticket body, the customer-selected category, and the product category of the order the ticket references. The first matching rule wins. There are 404 rules in production.

## Version history

| Version | Date | Change | Queue-level accuracy after |
|---|---|---|---|
| v1 | 2023-06-14 | First rules-based router, 61 rules | not measured at queue level |
| v2 | 2024-03-05 | Product-category rules added, 148 rules | not measured at queue level |
| v3 | 2024-11-19 | Rules rewritten as an ordered decision list, 236 rules | 70.8% (2025-Q2) |
| v3.1 | 2025-06-11 | Expansion pass, 74 rules added for Technical Faults | 71.5% (2025-Q3) |
| v3.2 | 2025-11-27 | Expansion pass, 58 rules added for Account & Access | 71.9% (2025-Q4) |
| v3.3 | 2026-03-16 | Expansion pass, 44 rules added and 8 retired | 71.4% (2026-Q2) |

## Assessment, 2026-06-30

Three expansion passes since v3 have moved queue-level accuracy from 70.8% to 71.4%, a gain of 0.6 percentage points across twelve months and 176 added rules. The most recent pass moved accuracy by +0.2 points against the preceding quarter, which is inside normal quarter-to-quarter variation.

Rule count is now the limiting factor. Each new rule must be checked against the rules already in the ordered list for conflicts, and review time for a single rule change has grown from under an hour in 2024 to roughly a working day. Two of the three passes above introduced ordering regressions that had to be patched within a fortnight of deployment.

Our assessment is that keyword rules have reached their ceiling on this ticket mix. The tickets that are misrouted today are misrouted because the words the customer used do not identify the queue, not because a rule is missing. We do not expect a fourth expansion pass to behave differently from the three before it.

## Rule change process

Rule changes are reviewed by two support engineers and deployed behind a flag. The decision made by every rule evaluation is written to `routing_decision_log` with the rule id, the engine version, and the inputs it matched on. Retention on that table is 24 months.

Shadow evaluation is supported: the engine can run alongside a second router, with both decisions logged and only one applied. This was used for the v3 rollout in November 2024.

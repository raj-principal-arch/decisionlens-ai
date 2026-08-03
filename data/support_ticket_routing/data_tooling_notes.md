# Data and Tooling Notes — Support Analytics

> **Synthetic document.** Fictional systems, fictional numbers. No real Walmart data.
> Owner: support-analytics. Created 2026-02-10. Last updated: 2026-07-06.
>
> How the support datasets are produced, and what they can and cannot be used for. Read this before quoting a number out of the exports.

## Reopen behaviour in the volume export

The Relay 5.2 release, on 2025-10-14, changed how reopened tickets are stored. When a customer replies to a ticket that has already been closed, and does so within 14 days of closure, Relay no longer reopens the original record. It creates a new record with a new ticket id and a `reopened_from` reference back to the closed one.

The volume export counts records. A reopened issue therefore appears twice: once as the original closed record and once as the clone. `exported_rows` is not a count of distinct customer issues, and `reopen_rows_included` is the number of clone records sitting inside it.

To count distinct customer issues, subtract `reopen_rows_included` from `exported_rows`. For 2026-Q1 that gives 36,310 distinct issues from 41,070 exported rows.

No clone records exist for any period before 2025-10-14. A year-over-year comparison that uses `exported_rows` across that date is comparing two different things and will overstate growth.

Time-to-resolution is also computed per record. A reopened issue contributes two resolution times, each shorter than the elapsed time the customer actually waited.

## Routing accuracy definition change

Routing accuracy was redefined on 2025-04-01. Under the old definition a ticket counted as correctly routed if it reached the correct department, of which there were three. Under the current definition it counts as correctly routed only if it reached the correct queue, of which there are five.

Figures published before 2025-04-01 are department-level and are not comparable with anything published since. The 78% figure that still circulates in planning documents is the 2025-Q1 department-level number, and it is carried in `routing_metrics.csv` under a separate metric name for exactly that reason.

## Analytics lag

Ticket events reach the analytics warehouse with a lag of up to 26 hours. Same-day measurement of any intervention is not possible; the earliest reliable read on a change is the following day.

## What is not in these datasets

There is no field recording why a ticket was reopened. The `reopened_from` reference identifies the original record but carries no reason code, and no free-text reason is captured anywhere.

There is no complexity or effort score on tickets. Comparisons between misrouted and correctly-routed tickets therefore cannot control for how hard the ticket was.

Agent actions are logged as state transitions only. There is no record of an agent disagreeing with a routing decision, only of the reassignment itself.

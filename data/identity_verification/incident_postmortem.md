# Incident Postmortem — INC-2025-0604 Bureau Connector Outage

> **Synthetic document.** Fictional incident, fictional numbers. No real Walmart data.
> Owner: platform-reliability. Last updated: 2025-07-02.

## Summary

Between 2025-06-04 and 2025-06-15 the Ridgemark Data Bureau connector returned errors for the majority of identity verification requests. A retail campaign drove application volume past the contractual limit of 12 requests per second and the connector shed load rather than queuing.

Verification could not complete automatically for 18,400 applications across the twelve affected days. Every one of them was pushed into the manual review queue.

## Impact

The manual review queue reached a depth of 11 days on 2025-06-12. It was not cleared until 2025-07-09.

Contact volume to the support line tripled during the outage week. Complaints referencing "no response" were the largest category.

## Measurement

Application-event telemetry depended on the same connector callback and was unavailable for nine of the twelve affected days. No funnel metrics exist for the outage period.

The onboarding funnel series in the warehouse begins at 2025-07. Figures for June 2025 and earlier were not backfilled.

## Actions

- Rate limiting added ahead of the connector. Completed 2025-06-20.
- Campaign volume forecast shared with platform before launch. Completed 2025-08-01.
- Backfill of the June 2025 funnel metrics. Not completed. Owner unassigned.

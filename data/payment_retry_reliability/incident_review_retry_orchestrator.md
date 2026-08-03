# Incident Review — Retry Orchestrator Dropped Retries (INC-4471)

> **Synthetic document.** Fictional incident, fictional systems, fictional numbers. No real Walmart data.
> Owner: payments-platform. Opened 2026-06-24. Review published 2026-07-09. Last updated: 2026-07-20.

## Summary

Between 2026-05-30 and 2026-06-24 the Retry Orchestrator stopped re-attempting a substantial share of eligible payment failures. The behaviour is intermittent: it appears in bursts lasting between forty minutes and six hours and clears without intervention.

## What was measured

Retries actually issued per eligible failure fell from 3.1 in 2025-Q4 to 1.3 in 2026-Q2. The configured policy is up to four attempts over 24 hours.

Card retry recovery, the share of eligible card failures that a later retry converts, fell from 41.8% in 2026-Q1 to 34.2% in 2026-Q2.

By count, card declines are the majority of failed payment attempts. Cards account for 19,369 of the 25,908 failed authorisation attempts in 2026-Q2.

## What is suspected and not established

The leading hypothesis is queue lease expiry: a retry job whose 15-minute lease expires before a worker collects it is dropped, and the drop emits no alert. This is consistent with the burst pattern and with the load profile, but it has not been demonstrated.

The defect has not been reproduced outside production. No non-production environment carries live issuer traffic, and the failure has never appeared under synthetic load.

## What was ruled out

Issuer-side outages were checked against the payments partner status feed for each burst window. Three of the eleven bursts coincided with a partner-reported degradation; eight did not.

A deployment correlation was tested and not found. Six of the eleven bursts occurred on days with no payments deployment.

## Not covered by this review

This review covers card and wallet authorisations only. Bank mandate collections are submitted in a nightly batch and are not routed through the Retry Orchestrator, so they were out of scope for the incident.

No estimate exists of how much of the failed value is eventually recovered when a buyer whose payment failed returns and completes the order by another route.

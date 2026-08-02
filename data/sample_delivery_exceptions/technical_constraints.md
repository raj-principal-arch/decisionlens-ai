# Technical Constraints — Delivery Platform

> **Synthetic document.** Fictional systems and limits. No real Walmart data.
> Owner: engineering. Last updated: 2026-06-20.

## Driver application

The driver application release train is locked until Q3 2026. No change to driver-facing screens can ship before the lock lifts.

## Address validation service

The address validation vendor contract was renegotiated in March 2026. Lookups are now bundled at no marginal cost per call, subject to a hard cap of 50 requests per second.

Integration effort has not been estimated. The service has never been called from the order path.

## Carrier integration

We hold read-only access to the carrier tracking system. Real-time writes are not available, so exception status cannot be updated from our side.

## Outbound messaging

Delivery SMS is routed through the marketing messaging platform and shares a rate limit with promotional sends. At peak promotional volume, delivery messages queue behind marketing traffic.

## Data platform

Delivery exception events land in the warehouse with a lag of up to 24 hours. Same-day measurement of any intervention is not currently possible.

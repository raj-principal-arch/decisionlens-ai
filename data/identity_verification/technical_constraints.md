# Technical Constraints — Onboarding Platform

> **Synthetic document.** Fictional systems and limits. No real Walmart data.
> Owner: engineering. Last updated: 2026-07-14.

## Core banking platform

A change freeze applies to the core banking platform from 2026-10-01 to 2027-01-15. Nothing that writes to account records ships inside that window.

## Bureau connector

The Ridgemark Data Bureau connector is contractually limited to 12 requests per second. Exceeding the limit returns errors rather than queuing. This limit was the direct cause of the June 2025 outage.

## Decision path today

No application is declined automatically today. Every decline is issued by a human reviewer working the manual review queue. Automatic outcomes are approvals only; anything the rules cannot clear is routed to a person.

## Risk score integration

The Veriphex risk score is returned as a single integer between 0 and 999. No contributing factors, reason codes, or feature attributions are returned with it. Veriphex has confirmed in writing that the model internals are proprietary and will not be exposed to customers of the service.

## Document store

The document store was migrated in February 2026 and now accepts up to four documents per application. The previous single-document limit no longer applies.

Stored documents are written to the regulated records vault. The vault has no deletion API; records leave it only on the scheduled retention cycle.

## Event pipeline

Verification funnel events land in the warehouse with a lag of up to 36 hours. Same-day measurement of any change is not possible.

## Liveness capture

Liveness capture runs in the mobile application only. The web application has no camera capture path and no work is scheduled to add one. Roughly 44% of applications are started on the web.

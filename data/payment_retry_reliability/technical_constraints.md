# Technical Constraints — Payments Platform

> **Synthetic document.** Fictional systems and limits. No real Walmart data.
> Owner: engineering. Last updated: 2026-06-30.

## Retry Orchestrator

Retry jobs are leased from the queue for 15 minutes. A job whose lease expires before a worker collects it is dropped, and the drop is not alerted. Extending the lease requires a broker upgrade that is not scheduled.

No non-production environment carries live issuer traffic. Changes to retry behaviour cannot be validated before release except by shadow traffic, which the orchestrator does not currently support.

## Bank mandate collections

Mandate collections are assembled in a nightly batch and submitted to the scheme directly. They do not pass through the Retry Orchestrator, and no change to orchestrator retry policy affects them.

The scheme return file is loaded nightly. Its reason codes are stored as raw strings and are not parsed, so no failure-reason breakdown exists for mandate collections.

## Tokenisation

The token vault is operated by Fenwold Payments. Token lifetime, refresh cadence, and account-updater participation are set by the partner and cannot be changed by Larkmere.

## Logging

The change deployed on 2026-06-12 removed the payment instrument identifier from newly written application logs. The identifier no longer appears in application logs, so from an engineering standpoint the exposure described in PT-2026-014 was closed on 2026-06-12.

## Data platform

From 2026-Q1 the authorisation success denominator excludes checkout sessions abandoned by the buyer before the issuer responded. The change raised the reported rate by approximately 0.9 percentage points. The earlier series has not been restated, so figures either side of 2026-Q1 are not directly comparable.

Payment events land in the warehouse with a lag of up to four hours.
